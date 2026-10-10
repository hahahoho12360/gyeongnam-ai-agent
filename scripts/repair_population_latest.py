"""Stage original API data, reconcile official totals, then atomically repair Firestore."""
from __future__ import annotations
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.probe_population_repair import OUT, query, save
from scripts.population_repair_core import ADAPTERS, validate_rows, validate_bundle, population_reconciliation
from scripts.bootstrap_regions import _is_gyeongnam_eup_myeon_dong
from scripts.collect.data_go_kr import DataGoKrClient
from backend.db import get_store, FirestoreStore, utcnow_iso
from backend.metrics import compute_derived
from scripts.pipeline import month_shift, month_end

def master_doc(row):
    code=str(row['region_cd']); name=str(row['locallow_nm']); full=str(row['locatadd_nm'])
    return {'id':code,'bjd_code':code,'name':name,'full_name':full,'sido':'경상남도',
            'sigungu':' '.join(full.split()[1:-1]),'region_type':'eup_myeon' if name.endswith(('읍','면')) else 'legal_dong',
            'peer_group':'rural' if name.endswith(('읍','면')) else 'urban','valid_from':row.get('adpt_de'),
            'source':'MOIS StanReginCd','is_demo':False}

def main(apply=False, reference=None):
    ref=json.loads(Path(reference or ROOT/'data/population_reference_202609.json').read_text())
    month=ref['month']
    code_path=OUT/'current_changwon_codes.json'
    if not code_path.exists():code_path=ROOT/'data/current_changwon_codes_verified20261010.json'
    codes=json.loads(code_path.read_text())
    master={str(r['region_cd']):master_doc(r) for r in codes if _is_gyeongnam_eup_myeon_dong(r)}
    absent=json.loads((ROOT/'data/boundaries/changwon_missing_regions_202609.json').read_text())
    ids={r['id'] for r in absent}
    ids.update(code for code,r in master.items() if r['region_type']=='eup_myeon')
    if len(ids)!=31 or len(master)!=204 or not ids.issubset(master):
        raise ValueError('Current code master differs from the verified repair scope')
    store=get_store()
    if apply and not isinstance(store,FirestoreStore):
        raise ValueError('Apply requires actual Firestore')
    current_regions=[r for r in store.list('regions') if str(r.get('id','')).startswith('4812') and not r.get('is_demo')]
    current_rows=[r for r in store.filter_eq('monthly_data','month',month) if str(r.get('region_id','')).startswith('4812')]
    tasks=[]
    for rid in sorted(ids):
        if rid not in ref['regions']:
            raise ValueError('Repair region absent from official reference')
        for child in ref['regions'][rid]['children']:
            if child not in {str(r['region_cd']) for r in codes}:
                raise ValueError('Ri code is not confirmed by current code API')
            for source in ADAPTERS:
                tasks.append((source,child,rid))
    grouped={rid:{s:[] for s in ADAPTERS} for rid in ids}
    def collect(task):
        source,child,rid=task
        f=OUT/f'{source}_{child}_{month}.json'
        if f.exists():
            capture=json.loads(f.read_text())
            if capture['month']!=month or capture['requested_code']!=child:
                raise ValueError('Cache scope mismatch')
            rows=capture['rows']
        else:
            rows=query(DataGoKrClient(),source,child,month)
        rows=validate_rows(rows,child,month)
        if not rows:
            raise ValueError(f'Empty required API result: {source} {child}')
        return source,rid,rows
    with ThreadPoolExecutor(max_workers=3) as executor:
        for future in as_completed([executor.submit(collect,t) for t in tasks]):
            source,rid,rows=future.result()
            grouped[rid][source].extend(rows)
    staged={}
    for rid,source_rows in grouped.items():
        bundle={s:ADAPTERS[s](rows,[master[rid]],rid[:5]).get(rid,{}) for s,rows in source_rows.items()}
        validate_bundle(bundle)
        pop=bundle['population']; official=ref['regions'][rid]
        if official.get('population_total') is not None and any(pop[k]!=official[k] for k in ['population_total','population_male','population_female']):
            raise ValueError('API population disagrees with official CSV')
        if any(bundle['age_population'].get(k)!=v for k,v in official.get('age',{}).items()):
            raise ValueError('API age buckets disagree with official CSV')
        if 'single_households' in official and bundle['single_household']['single_households']!=official['single_households']:
            raise ValueError('API one-person households disagree with official CSV')
        staged[rid]=bundle
    rows={r['region_id']:r for r in current_rows}
    for rid,bundle in staged.items():
        row=dict(rows.get(rid,{'region_id':rid,'month':month}))
        row['metrics']={**row.get('metrics',{}),**{k:v for patch in bundle.values() for k,v in patch.items()}}
        rows[rid]=row
    reconciliation=population_reconciliation(list(master.values()),list(rows.values()),ref)
    households={sig:sum((r.get('metrics',{}).get('households') or 0) for code,r in rows.items() if code.startswith(sig))
                for sig in ref['totals'] if sig!='48120'}
    for sig,actual in households.items():
        if actual!=ref['totals'][sig]['households']:
            reconciliation['status']='failed'
            reconciliation['problems'].append({'district':sig,'metric':'households','stored':actual,'official':ref['totals'][sig]['households']})
    for sig,total in ref['totals'].items():
        for metric in ['population_male','population_female']:
            if metric not in total:continue
            actual=sum((r.get('metrics',{}).get(metric) or 0) for code,r in rows.items() if sig=='48120' or code.startswith(sig))
            if actual!=total[metric]:
                reconciliation['status']='failed'
                reconciliation['problems'].append({'district':sig,'metric':metric,'stored':actual,'official':total[metric]})
    save(f'staged_validation_{month}.json',{'apply_requested':apply,'reconciliation':reconciliation,'target_regions':sorted(ids),'household_sums':households,'reference_kind':ref.get('reference_kind','official_code_values')})
    if reconciliation['status']!='passed':
        raise ValueError('Staged full-city reconciliation failed; no writes made')
    if not apply:
        print('Staged API data verified; dry-run only',flush=True)
        return
    # All API requests and reconciliation pass before any Firebase mutation.
    backup={'month':month,'regions':{rid:store.get('regions',rid) for rid in ids},
            'monthly_data':{rid:store.get('monthly_data',f'{rid}_{month}') for rid in ids},
            'region_latest':{rid:store.get('region_latest',rid) for rid in ids}}
    save(f'firestore_before_{month}.json',backup)
    batch=store.client.batch(); now=utcnow_iso()
    for rid,bundle in staged.items():
        before=backup['monthly_data'][rid] or {}
        row={**before,**rows[rid]};row.pop('id',None)
        sources=dict((before.get('freshness') or {}).get('sources') or {})
        for source,patch in bundle.items():
            sources[source]={'source_as_of':month_end(month),'fetched_at':now,'is_provisional':False,
                             'data_confidence':'unknown','sample_size':None,'status':'ok',
                             'collection_method':'original_api_legal_ri_rollup' if master[rid]['region_type']=='eup_myeon' else 'original_api_legal_dong',
                             'source_row_count':len(grouped[rid][source])}
        freshness=dict(before.get('freshness') or {})
        freshness.update({'sources':sources,'fetched_at':now,'source_as_of':max(str(s.get('source_as_of') or '') for s in sources.values()),'is_demo':False})
        row['freshness']=freshness
        prev=store.get('monthly_data',f'{rid}_{month_shift(month,-1)}') or {}
        year=store.get('monthly_data',f'{rid}_{month_shift(month,-12)}') or {}
        row['derived']=compute_derived(row['metrics'],prev.get('metrics',{}),year.get('metrics',{}))
        row['index_meta']={**row.get('index_meta',{}),'requires_recompute':True}
        batch.set(store.client.collection('monthly_data').document(f'{rid}_{month}'),row)
        latest=backup['region_latest'][rid]
        if not latest or str(latest.get('month',''))<=month:
            batch.set(store.client.collection('region_latest').document(rid),row)
        doc=master[rid]
        if doc['region_type']=='eup_myeon':
            doc={**doc,'population_query_codes':ref['regions'][rid]['children'],
                 'population_query_hierarchy_source':'MOIS StanReginCd verified against official monthly code inventory'}
        if not backup['regions'][rid]:doc={**doc,'neighbors':[]}
        batch.set(store.client.collection('regions').document(rid),doc,merge=True)
    batch.set(store.client.collection('rollout_reports').document(f'changwon_population_repair_v37_{month}'),
              {'month':month,'status':'applied_pending_index_recompute','reconciliation':reconciliation,'updated_at':now})
    batch.commit()
    after=[r for r in store.filter_eq('monthly_data','month',month) if str(r.get('region_id','')).startswith('4812')]
    result=population_reconciliation(list(master.values()),after,ref)
    save(f'after_write_{month}.json',result)
    if result['status']!='passed':raise RuntimeError('Post-write verification failed')
    print(f'Month {month} applied atomically; population {result["population_sum"]} verified',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--reference',type=Path);args=parser.parse_args()
    try:main(args.apply,args.reference)
    except Exception as exc:
        save('repair_failure.json',{'status':'blocked','exception_type':type(exc).__name__,'stage':'inspect artifacts before assuming apply succeeded'})
        print('Repair blocked:',type(exc).__name__,flush=True);sys.exit(2)
