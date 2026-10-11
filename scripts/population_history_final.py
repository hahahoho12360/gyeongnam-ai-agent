"""Full-scope, read-only-first population audit followed by per-month atomic repair.

Only original API values are stored. Parent response meanings are resolved by
independent official district totals; ambiguous combinations never get applied.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from scripts.bootstrap_regions import _is_gyeongnam_eup_myeon_dong
from scripts.population_repair_core import ADAPTERS, validate_rows, validate_bundle, nonnegative_int
from scripts.probe_population_repair import OUT, ROOT, query, save
from scripts.probe_configured_api import SPECS
from scripts.collect.data_go_kr import DataGoKrClient
from scripts.repair_population_latest import master_doc
from backend.db import FirestoreStore, get_store, utcnow_iso
from scripts.pipeline import month_end

VERSION = '3.7.1-final'
KEYS = ('population_total', 'population_male', 'population_female', 'households')
SOURCES = tuple(ADAPTERS)


class UnresolvedMonth(ValueError):
    pass


def inventory(code_rows):
    master = {str(r['region_cd']): master_doc(r) for r in code_rows
              if str(r['region_cd']).startswith('4812') and _is_gyeongnam_eup_myeon_dong(r)}
    if len(master) != 204:
        raise ValueError('Verified Changwon master must contain 204 regions')
    children = {}
    for rid, doc in master.items():
        children[rid] = sorted(str(r['region_cd']) for r in code_rows
                               if str(r['region_cd']).startswith(rid[:7])
                               and str(r['region_cd'])[-2:] != '00') if doc['region_type'] == 'eup_myeon' else []
        if doc['region_type'] == 'eup_myeon' and not children[rid]:
            raise ValueError('Legal ri inventory missing for an eup/myeon')
    codes = sorted(set(master) | {c for values in children.values() for c in values})
    if len(codes) != len(set(codes)) or any(len(c) != 10 for c in codes):
        raise ValueError('Invalid legal code inventory')
    return master, children, codes


def check_totals(rows, totals):
    """Sex and household totals are checked as well as total population."""
    problems = []
    seen=set()
    for row in rows:
        rid=row['region_id'];metrics=row.get('metrics',{})
        if rid in seen: problems.append({'region':rid,'reason':'duplicate_region'})
        seen.add(rid)
        if metrics.get('population_total') is not None:
            if any(not nonnegative_int(metrics.get(k)) for k in KEYS):
                problems.append({'region':rid,'reason':'incomplete_or_invalid_population_metrics'})
            elif metrics['population_male']+metrics['population_female']!=metrics['population_total']:
                problems.append({'region':rid,'reason':'population_sex_mismatch'})
    for sig, official in totals.items():
        for key in KEYS:
            if key not in official:
                raise ValueError('Official benchmark missing a required metric')
            actual = sum((r.get('metrics', {}).get(key) if nonnegative_int(r.get('metrics', {}).get(key)) else 0) for r in rows
                         if sig == '48120' or str(r['region_id']).startswith(sig))
            if actual != official[key]:
                problems.append({'district': sig, 'metric': key, 'stored': actual, 'official': official[key]})
    return {'status': 'passed' if not problems else 'failed', 'problems': problems}


def metric_signature(bundle):
    # Row counts/provenance differ even when the numeric candidate is identical.
    return json.dumps({s: {k: v for k, v in patch.items() if not k.endswith('_rows')}
                       for s, patch in bundle.items()}, sort_keys=True)


def bundle_from(rows_by_source, master, rid):
    bundle = {s: ADAPTERS[s](rows_by_source[s], [master[rid]], rid[:5]).get(rid, {}) for s in SOURCES}
    pop = bundle['population']
    if not pop:
        if any(rows_by_source[s] for s in SOURCES):
            raise UnresolvedMonth('Sources disagree on population presence')
        return None
    if any(not nonnegative_int(pop.get(k)) for k in KEYS):
        raise UnresolvedMonth('Incomplete numeric population metrics')
    if pop['population_male'] + pop['population_female'] != pop['population_total']:
        raise UnresolvedMonth('Population sex totals disagree')
    age = bundle['age_population']
    age_keys = [f'age_{i}_{i+9}' for i in range(0, 100, 10)] + ['age_100_plus']
    if not age or any(not nonnegative_int(age.get(k)) for k in age_keys):
        raise UnresolvedMonth('Required age response missing')
    if sum(age[k] for k in age_keys) != pop['population_total']:
        raise UnresolvedMonth('Age total disagrees with population')
    single = bundle['single_household']
    if single:
        validate_bundle(bundle)
    # A successful empty one-person response remains unknown, never guessed as 0.
    return bundle


def candidates(rid, master, children, captures):
    parent = {s: captures[s, rid] for s in SOURCES}
    variants = [('legal_dong', parent)]
    if children[rid]:
        child = {s: [r for c in children[rid] for r in captures[s, c]] for s in SOURCES}
        variants = [('ri_only', child), ('parent_only', parent),
                    ('ri_plus_parent', {s: child[s] + parent[s] for s in SOURCES})]
    out = {}
    for mode, rows in variants:
        try:
            bundle = bundle_from(rows, master, rid)
        except ValueError:
            continue
        if bundle is None:
            continue
        signature = metric_signature(bundle)
        if signature not in out:
            out[signature] = {'bundle': bundle, 'modes': [mode],
                              'source_rows': {s: len(rows[s]) for s in SOURCES}}
        else:
            out[signature]['modes'].append(mode)
    if not out and any(captures[s, c] for s in SOURCES for c in [rid] + children[rid]):
        raise UnresolvedMonth(f'No internally consistent API candidate: {rid}')
    return list(out.values())


def resolve_month(month, master, children, captures, totals, validation_policy='totals_first'):
    options = {rid: candidates(rid, master, children, captures) for rid in master}
    selected = {}; unknown = []; modes = {}
    for sig in sorted(k for k in totals if k != '48120'):
        fixed = []; variable = []; fixed_sum = {k: 0 for k in KEYS}
        for rid in sorted(r for r in master if r.startswith(sig)):
            choices = options[rid]
            if not choices:
                unknown.append(rid)
                continue
            if len(choices) == 1:
                fixed.append((rid, choices[0]))
                for k in KEYS: fixed_sum[k] += choices[0]['bundle']['population'][k]
            else:
                variable.append((rid, choices))
        matches = []
        for values in itertools.product(*(choices for _, choices in variable)):
            actual = {k: fixed_sum[k] + sum(v['bundle']['population'][k] for v in values) for k in KEYS}
            if all(actual[k] == totals[sig][k] for k in KEYS):
                matches.append(values)
                if len(matches) > 1:
                    break
        if len(matches) != 1:
            raise UnresolvedMonth(f'District {sig}: {len(matches)} valid parent/ri assignments; no writes')
        for rid, choice in fixed + [(rid, choice) for (rid, _), choice in zip(variable, matches[0])]:
            selected[rid] = choice
            if children[rid]:
                modes[rid] = {'modes': choice['modes'], 'source_rows': choice['source_rows'],
                              'population': choice['bundle']['population'], 'child_count': len(children[rid])}
    single_unknown=[rid for rid, choice in selected.items() if not choice['bundle']['single_household']]
    if validation_policy == 'strict' and (unknown or single_unknown):
        raise UnresolvedMonth('Strict policy rejects successful empty regional/source responses')
    patches = {}
    for rid in master:
        choice = selected.get(rid)
        if choice:
            metrics = {k: v for patch in choice['bundle'].values() for k, v in patch.items()}
            if not choice['bundle']['single_household']:
                metrics.update({k: None for k in single_keys()})
            patches[rid] = {'metrics': metrics, 'sources': {
                s: {'source_as_of': month_end(month), 'fetched_at': utcnow_iso(),
                    'status': 'ok' if choice['source_rows'][s] else 'no_data',
                    'source_row_count': choice['source_rows'][s], 'collection_method': VERSION,
                    'data_confidence': 'unknown', 'is_provisional': False,
                    'aggregation_modes': choice['modes']} for s in SOURCES}}
        else:
            patches[rid] = {'metrics': {k: None for k in population_keys()}, 'sources': {
                s: {'source_as_of': month_end(month), 'fetched_at': utcnow_iso(), 'status': 'no_data',
                    'source_row_count': 0, 'collection_method': VERSION, 'data_confidence': 'unknown',
                    'is_provisional': False} for s in SOURCES}}
    check = check_totals([{'region_id': rid, 'metrics': patch['metrics']} for rid, patch in patches.items()], totals)
    if check['status'] != 'passed':
        raise UnresolvedMonth('City/district benchmark failed after resolving API candidates')
    check.update({'validation_policy': validation_policy, 'population_coverage': {
        'known': len(master)-len(unknown), 'master': len(master)}, 'warnings': [
        {'code': c, 'reason': 'Successful empty original API responses; null retained'} for c in unknown] + [
        {'code':c,'source':'single_household','reason':'Successful empty response; one-person counts remain null'} for c in single_unknown]})
    return {'month': month, 'patches': patches, 'reconciliation': check, 'parent_modes': modes,
            'method_version': VERSION, 'prepared_at': utcnow_iso()}


def single_keys():
    return ['single_households', 'one_person_households', 'single_male_households', 'single_female_households',
            'single_age_20_39', 'single_age_60_plus', 'single_age_100_plus'] + [f'single_age_{i}_{i+9}' for i in range(0,100,10)]


def population_keys():
    return list(KEYS) + ['persons_per_household','sex_ratio','age_20_39','age_60_plus','age_100_plus'] + [
        f'age_{i}_{i+9}' for i in range(0,100,10)] + single_keys()


def prefetch_window(months, codes, workers=6):
    tasks=[]; originals={}; errors=[]
    for s in SOURCES:
        _, qe = SPECS[s]; originals[qe] = os.environ[qe]
        template = json.loads(originals[qe]); template.update(srchFrYm=months[0].replace('-',''), srchToYm=months[-1].replace('-',''))
        os.environ[qe] = json.dumps(template)
        for code in codes:
            valid=True
            for month in months:
                path=OUT/f'{s}_{code}_{month}.json'
                if not path.exists(): valid=False; break
                try:
                    cached=json.loads(path.read_text())
                    if (cached.get('audit_version') != VERSION or cached.get('month') != month
                            or cached.get('requested_code') != code or not cached.get('successful_request')):
                        valid=False; break
                    validate_rows(cached['rows'], code, month)
                except (ValueError, KeyError, TypeError):
                    path.unlink(missing_ok=True); valid=False; break
            if not valid: tasks.append((s,code))
    def collect(task):
        s,code=task
        def capture(window, template=None):
            client=DataGoKrClient(timeout=45,max_retries=2)
            rows=query(client,s,code,window[-1],**({'template_override':template} if template is not None else {}))
            groups={m:[] for m in window}
            for row in rows:
                period=str(row.get('statsYm','')); m=period[:4]+'-'+period[4:6]
                if m not in groups: raise ValueError('Unexpected range period')
                groups[m].append(row)
            for m,items in groups.items():
                clean=validate_rows(items,code,m)
                save(f'{s}_{code}_{m}.json',{'source':s,'requested_code':code,'month':m,'rows':clean,
                    'requested_range':window,'collection_method':'original_api_range_or_single_month',
                    'audit_version':VERSION,'successful_request':True})
        try:
            capture(months)
            return []
        except Exception as exc:
            for m in months: (OUT/f'{s}_{code}_{m}.json').unlink(missing_ok=True)
            if len(months)==1:
                return [{'source':s,'code':code,'months':months,'exception_type':type(exc).__name__}]
        failures=[]
        # A rejected/failed range is retried one month at a time without mutating
        # shared environment variables in worker threads.
        for m in months:
            template=json.loads(originals[SPECS[s][1]])
            template.update(srchFrYm=m.replace('-',''),srchToYm=m.replace('-',''))
            try: capture([m],template)
            except Exception as exc:
                (OUT/f'{s}_{code}_{m}.json').unlink(missing_ok=True)
                failures.append({'source':s,'code':code,'months':[m],'exception_type':type(exc).__name__})
        return failures
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for future in as_completed([ex.submit(collect,t) for t in tasks]):
                error=future.result()
                if error: errors.extend(error)
    finally:
        for qe,value in originals.items(): os.environ[qe]=value
    save('request_errors_'+months[0]+'.json',errors)
    return errors


def commit_batch(batch):
    from google.api_core.exceptions import ServiceUnavailable, DeadlineExceeded, Aborted, InternalServerError
    for attempt in range(3):
        try:
            return batch.commit()
        except (ServiceUnavailable, DeadlineExceeded, Aborted, InternalServerError):
            if attempt==2: raise
            time.sleep(2**attempt)


def apply_plan(store, plan):
    """Update metric/source fields, preserving concurrently collected other sources."""
    month=plan['month']; current={r['region_id']:r for r in store.filter_eq('monthly_data','month',month)
                                if str(r.get('region_id','')).startswith('4812')}
    save(f'firestore_before_{month}.json',{'month':month,'monthly_data':current})
    batch=store.client.batch()
    for rid,patch in plan['patches'].items():
        ref=store.client.collection('monthly_data').document(f'{rid}_{month}')
        fields={f'metrics.{k}':v for k,v in patch['metrics'].items()}
        fields.update({f'freshness.sources.{s}':v for s,v in patch['sources'].items()})
        fields.update({'freshness.fetched_at':utcnow_iso(),'freshness.is_demo':False,
                       'index_meta.requires_recompute':True,'indexes_need_recompute':True})
        if rid in current:
            batch.update(ref,fields)
        else:
            batch.set(ref,{'region_id':rid,'month':month,'metrics':patch['metrics'],
                          'freshness':{'sources':patch['sources'],'fetched_at':utcnow_iso(),'is_demo':False},
                          'index_meta':{'requires_recompute':True},'indexes_need_recompute':True})
        if month=='2026-09':
            # Merge only this population patch; retain other source fields.
            batch.set(store.client.collection('region_latest').document(rid),
                      {'region_id':rid,'month':month,'metrics':patch['metrics'],
                       'freshness':{'sources':patch['sources']},'index_meta':{'requires_recompute':True},
                       'indexes_need_recompute':True},merge=True)
    batch.set(store.client.collection('rollout_reports').document(f'changwon_population_repair_v37_{month}'),
              {'month':month,'method_version':VERSION,'reconciliation':plan['reconciliation'],
               'parent_modes':plan['parent_modes'],'status':'applied_pending_index_recompute','updated_at':utcnow_iso()},merge=True)
    commit_batch(batch)


def compact_status(status):
    """Keep the Firestore progress document bounded during a provider outage.

    Complete diagnostics remain in Actions artifacts, never in one huge DB doc.
    """
    summary={**status,'issues':[]}
    for issue in status.get('issues',[]):
        item={k:v for k,v in issue.items() if k!='errors'}
        if 'errors' in issue:
            item.update(error_count=len(issue['errors']),errors=issue['errors'][:10])
        summary['issues'].append(item)
    return summary


def run(max_months=48,max_minutes=260,validation_policy='totals_first',workers=6):
    save('history_status.json',{'status':'initializing','method_version':VERSION,'validation_policy':validation_policy})
    store=get_store()
    if not isinstance(store,FirestoreStore): raise ValueError('Actual Firestore is required')
    code_rows=json.loads((ROOT/'data/current_changwon_codes_verified20261010.json').read_text())
    master,children,codes=inventory(code_rows)
    totals=json.loads((ROOT/'data/population_official_history_totals.json').read_text())['months']
    if len(totals)!=48 or min(totals)!='2022-10' or max(totals)!='2026-09':
        raise ValueError('Expected all 48 independent official monthly benchmarks')
    all_rows=[r for r in store.list('monthly_data') if r.get('region_id') in master and r.get('month') in totals]
    grouped={m:[] for m in totals}
    for row in all_rows: grouped[row['month']].append(row)
    remaining=[]; persisted_checks={}
    for month in sorted(totals):
        check=check_totals(grouped[month],totals[month]); persisted_checks[month]=check
        # Check current values, not an old success flag alone.
        if check['status']!='passed': remaining.append(month)
    inventory_report={'version':VERSION,'master_count':len(master),'query_code_count':len(codes),
        'eup_myeon_children':children,'remaining_months':remaining,'persisted_checks':persisted_checks,
        'scope':'All 204 Changwon regions, all legal ri, all 8 parent eup/myeon codes'}
    save('preflight_inventory.json',inventory_report)
    store.set('rollout_reports','changwon_population_history_final_preflight',
              {'version':VERSION,'remaining_months':remaining,'master_count':len(master),
               'query_code_count':len(codes),'updated_at':utcnow_iso()},merge=False)
    save('history_status.json',{'status':'preflight_running','validation_policy':validation_policy,
                              'remaining_months':len(remaining),'method_version':VERSION})
    if not 1 <= workers <= 6: raise ValueError('Workers must be between 1 and 6')
    started=time.monotonic(); plans=[]; issues=[]; examined=[]
    for offset in range(0,min(max_months,len(remaining)),3):
        # Leave time for the next bounded API window and writes/final verification.
        if time.monotonic()-started > max(0,max_minutes-35)*60: break
        months=remaining[offset:min(offset+3,max_months)]
        errors=prefetch_window(months,codes,workers)
        for month in months:
            examined.append(month)
            month_errors=[e for e in errors if month in e['months']]
            if month_errors:
                issues.append({'month':month,'reason':'original_api_request_failed','errors':month_errors})
                continue
            captures={(s,c):json.loads((OUT/f'{s}_{c}_{month}.json').read_text())['rows'] for s in SOURCES for c in codes}
            try:
                plan=resolve_month(month,master,children,captures,totals[month],validation_policy)
                save(f'staged_validation_{month}.json',{'reconciliation':plan['reconciliation'],
                    'parent_modes':plan['parent_modes'],'method_version':VERSION,'apply_requested':True})
                save(f'prepared_plan_{month}.json',plan); plans.append(plan)
                print('Preflight passed:',month,'all 204 regions, 8 parent codes and every legal ri',flush=True)
            except Exception as exc:
                issues.append({'month':month,'reason':'unresolved_validation','exception_type':type(exc).__name__,
                               'safe_detail':str(exc) if isinstance(exc,UnresolvedMonth) else 'Inspect API captures'})
            save('history_status.json',{'status':'preflight_running','validation_policy':validation_policy,
                'method_version':VERSION,'examined_months':examined,'prepared_months':[p['month'] for p in plans],
                'issues':issues,'remaining_months':len(remaining)-len(examined)})
    # No monthly population writes occur until every scheduled window is examined.
    save('preflight_issues.json',issues)
    applied=[]
    for plan in plans:
        try:
            apply_plan(store,plan)
            after=[r for r in store.filter_eq('monthly_data','month',plan['month']) if r.get('region_id') in master]
            check=check_totals(after,totals[plan['month']]);save(f"after_write_{plan['month']}.json",check)
            if check['status']!='passed': raise UnresolvedMonth('Post-write verification failed')
            applied.append(plan['month']);print('Applied and verified:',plan['month'],flush=True)
        except Exception as exc:
            issues.append({'month':plan['month'],'reason':'apply_or_postwrite_failed','exception_type':type(exc).__name__})
    left=[m for m in remaining if m not in applied]; pending=[m for m in remaining if m not in examined]
    status={'method_version':VERSION,'validation_policy':validation_policy,'applied_this_run':len(applied),
            'applied_months':applied,'examined_months':examined,'prepared_months':[p['month'] for p in plans],'remaining_months':len(left),'pending_months':pending,'issues':issues,
            'updated_at':utcnow_iso(),'status':'needs_continue' if pending and not issues else 'partial' if left else 'verifying'}
    save('history_status.json',status)
    if left:
        store.set('rollout_reports','changwon_population_history_v37',compact_status(status),merge=False)
        print('Repair finished with retained unresolved months; see history_status.json',flush=True)
        return status
    # Read the actual persisted records again before recomputing indexes.
    all_rows=[r for r in store.list('monthly_data') if r.get('region_id') in master and r.get('month') in totals]
    checks={m:check_totals([r for r in all_rows if r['month']==m],totals[m]) for m in totals}
    bad={m:c for m,c in checks.items() if c['status']!='passed'}
    save('final_persisted_validation.json',checks)
    if bad:
        status.update(status='partial',remaining_months=len(bad),issues=[{'month':m,'reason':'final_persisted_validation_failed'} for m in bad])
    else:
        from scripts.repair_population_history import reindex_all
        try:
            reindex_all(store,totals,validation_policy)
            status.update(status='complete',verified_months=48,totals_verified_months=48,
                          historical_validation='Original APIs and independent city/district population, sex and household totals; empty regional responses remain null')
        except Exception as exc:
            status.update(status='needs_continue',population_totals_verified_months=48,pending_reindex=True,
                          issues=[{'reason':'reindex_pending','exception_type':type(exc).__name__}])
    save('history_status.json',status)
    store.set('rollout_reports','changwon_population_history_v37',compact_status(status),merge=False)
    return status
