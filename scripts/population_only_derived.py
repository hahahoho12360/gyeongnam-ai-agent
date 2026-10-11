"""Population-only recalculation; preserve other derived values and all indexes."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.db import get_store, FirestoreStore, utcnow_iso
from backend.metrics import share, pct_change
from scripts.pipeline import month_shift
from scripts import population_history_final as core
from scripts.probe_population_repair import OUT, save

VERSION='3.7.3'

def population_derived(metrics,previous=None,year_ago=None):
    previous=previous or {};year_ago=year_ago or {}
    total=metrics.get('population_total');households=metrics.get('households')
    single=metrics.get('single_households')
    older=metrics.get('age_65_plus');basis='65_plus';proxy=False
    if older is None:
        older=metrics.get('age_60_plus');basis='60_plus_proxy' if older is not None else 'unavailable';proxy=True
    single_older=metrics.get('single_age_65_plus')
    if single_older is None:single_older=metrics.get('single_age_60_plus')
    one=metrics.get('one_person_households');two=metrics.get('two_person_households')
    return {
        'population_mom_pct':pct_change(total,previous.get('population_total')),
        'population_yoy_pct':pct_change(total,year_ago.get('population_total')),
        'households_mom_pct':pct_change(households,previous.get('households')),
        'households_yoy_pct':pct_change(households,year_ago.get('households')),
        'young_population_share':share(metrics.get('age_20_39'),total),
        'older_population_share':share(older,total),
        'older_population_basis':basis,'older_population_is_proxy':proxy,
        'single_household_share':share(single,households),
        'young_single_household_share':share(metrics.get('single_age_20_39'),single),
        'older_single_household_share':share(single_older,single),
        'small_household_share':share(one+two,households) if one is not None and two is not None else None,
    }

def load_snapshot(store):
    master,_,_=core.inventory(json.loads((ROOT/'data/current_changwon_codes_verified20261010.json').read_text()))
    totals=json.loads((ROOT/'data/population_official_history_totals.json').read_text())['months']
    rows=[r for r in store.list('monthly_data') if r.get('region_id') in master and r.get('month') in totals]
    grouped={m:[] for m in totals}
    for r in rows:grouped[r['month']].append(r)
    checks={m:core.check_totals(rs,totals[m]) for m,rs in grouped.items()}
    return master,totals,rows,checks

def plans(rows,checks,months):
    by_id={(r['region_id'],r['month']):r for r in rows}
    patches=[]
    for row in rows:
        month=row['month'];rid=row['region_id']
        if month not in months or checks[month]['status']!='passed':continue
        previous_month=month_shift(month,-1);year_month=month_shift(month,-12)
        previous=by_id.get((rid,previous_month),{}).get('metrics',{}) if checks.get(previous_month,{}).get('status')=='passed' else {}
        year=by_id.get((rid,year_month),{}).get('metrics',{}) if checks.get(year_month,{}).get('status')=='passed' else {}
        values=population_derived(row.get('metrics',{}),previous,year)
        patches.append({'id':row['id'],'region_id':rid,'month':month,'values':values,
            'meta':{'method_version':VERSION,'computed_at':utcnow_iso(),'population_only':True,
                'previous_month_verified':checks.get(previous_month,{}).get('status')=='passed',
                'year_ago_verified':checks.get(year_month,{}).get('status')=='passed',
                'missing_values_preserved':True}})
    return patches

def write_and_verify(store,patches):
    latest={r.get('region_id',r['id']):r for r in store.list('region_latest')}
    for offset in range(0,len(patches),200):
        batch=store.client.batch()
        for patch in patches[offset:offset+200]:
            fields={f'derived.{k}':v for k,v in patch['values'].items()}
            fields['population_derived_meta']=patch['meta']
            batch.update(store.client.collection('monthly_data').document(patch['id']),fields)
            if latest.get(patch['region_id'],{}).get('month')==patch['month']:
                batch.update(store.client.collection('region_latest').document(patch['region_id']),fields)
        core.commit_batch(batch)
    reread={r['id']:r for r in store.list('monthly_data')}
    mismatches=[]
    for patch in patches:
        row=reread.get(patch['id'],{})
        for key,value in patch['values'].items():
            if key not in row.get('derived',{}) or row['derived'][key]!=value:
                mismatches.append({'id':patch['id'],'metric':key})
    # Also verify any public latest snapshot that was updated.
    reread_latest={r['id']:r for r in store.list('region_latest')}
    for patch in patches:
        if latest.get(patch['region_id'],{}).get('month')==patch['month']:
            row=reread_latest.get(patch['region_id'],{})
            for key,value in patch['values'].items():
                if key not in row.get('derived',{}) or row['derived'][key]!=value:
                    mismatches.append({'latest_region':patch['region_id'],'metric':key})
    return mismatches

def run(month=None,final=False):
    store=get_store()
    if not isinstance(store,FirestoreStore):raise ValueError('Actual Firestore required')
    master,totals,rows,checks=load_snapshot(store)
    targets=set(totals) if final else {month,month_shift(month,1),month_shift(month,12)} & set(totals)
    patches=plans(rows,checks,targets)
    mismatches=write_and_verify(store,patches)
    verified=sorted(m for m,c in checks.items() if c['status']=='passed')
    remaining=sorted(set(totals)-set(verified))
    status={'method_version':VERSION,'status':'failed' if mismatches else 'needs_continue' if final and remaining else 'complete',
        'population_only':True,'updated_rows':len(patches),'updated_months':sorted({p['month'] for p in patches}),
        'verified_population_months':verified,'remaining_months':remaining,'mismatches':mismatches,
        'composite_indexes_recomputed':False,'nonpopulation_derived_recomputed':False,
        'month_coverage':{m:{'stored_regions':sum(r['month']==m for r in rows),
            'known_population_regions':sum(r['month']==m and r.get('metrics',{}).get('population_total') is not None for r in rows),
            'master_regions':len(master)} for m in sorted(targets)},'updated_at':utcnow_iso()}
    save('population_derived_final.json' if final else f'population_derived_{month}.json',status)
    store.set('rollout_reports','changwon_population_derived_v373',status,merge=False)
    print(json.dumps(status,ensure_ascii=False),flush=True)
    return status

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--month');p.add_argument('--final',action='store_true');a=p.parse_args()
    if not a.final and not a.month:p.error('--month or --final required')
    try:
        result=run(a.month,a.final)
        sys.exit(0 if result['status']=='complete' else 2)
    except Exception as exc:
        save('population_derived_error.json',{'status':'blocked','exception_type':type(exc).__name__,'month':a.month})
        print('Population recalculation blocked:',type(exc).__name__,flush=True)
        sys.exit(2)
