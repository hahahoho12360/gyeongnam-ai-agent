"""Monthly original-API repair with Firebase checkpoints and official total gates."""
import argparse
import json
import sys
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.probe_population_repair import OUT, save
from scripts.repair_population_latest import main as repair_month
from scripts.population_repair_core import population_reconciliation
from backend.db import get_store, FirestoreStore, utcnow_iso
from backend.metrics import compute_derived
from backend.indexes import compute_index_rows, methodology_payload
from scripts.pipeline import month_shift
from scripts.probe_configured_api import SPECS
from scripts.collect.data_go_kr import DataGoKrClient
from scripts.probe_population_repair import query
from scripts.population_repair_core import validate_rows

def prefetch(months, base):
    """The same APIs were live-tested with a three-month range; split by statsYm."""
    targets={r['id'] for r in json.loads((ROOT/'data/boundaries/changwon_missing_regions_202609.json').read_text())}
    master=json.loads((ROOT/'data/current_changwon_codes_verified20261010.json').read_text())
    targets.update(str(r['region_cd']) for r in master if str(r.get('locallow_nm','')).endswith(('읍','면')) and str(r['region_cd'])[-2:]=='00')
    codes=sorted({code for rid in targets for code in base['regions'][rid]['children']})
    tasks=[]
    originals={}
    for source,(ue,qe) in [(s,SPECS[s]) for s in ['population','age_population','single_household']]:
        originals[qe]=os.environ[qe]
        template=json.loads(originals[qe]);template['srchFrYm']=months[0].replace('-','');template['srchToYm']=months[-1].replace('-','')
        os.environ[qe]=json.dumps(template)
        for code in codes:
            if not all((OUT/f'{source}_{code}_{month}.json').exists() for month in months):tasks.append((source,code))
    def collect(task):
        source,code=task
        rows=query(DataGoKrClient(),source,code,months[-1])
        captures={month:[] for month in months}
        for row in rows:
            period=str(row.get('statsYm',''));month=period[:4]+'-'+period[4:6]
            if month not in captures:raise ValueError('Unexpected range period')
            captures[month].append(row)
        for month,items in captures.items():
            clean=validate_rows(items,code,month)
            if not clean:raise ValueError('Historical range missing a required month')
            # Save API rows, not benchmark values. Preserve range query provenance.
            save(f'{source}_{code}_{month}.json',{'source':source,'requested_code':code,'month':month,'rows':clean,
                  'requested_range':months,'collection_method':'original_api_three_month_range'})
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            for future in as_completed([executor.submit(collect,t) for t in tasks]):future.result()
    finally:
        for qe,value in originals.items():os.environ[qe]=value

def reference_for(month, base, totals):
    # Independent historical benchmark is city/district totals, not per-dong CSV.
    # Detailed latest-month CSV values must NEVER be copied into older months.
    regions={code:{'name':row['name'],'children':row['children'],'population_total':None}
             for code,row in base['regions'].items()}
    verified_empty = []
    if month == '2022-10' and '4812311700' in regions:
        for source in ['population', 'age_population', 'single_household']:
            evidence = json.loads((ROOT / 'data/population_empty_evidence' / f'{source}_4812311700_2022-10.json').read_text())
            expected_params = {'stdgCd':'4812311700','srchFrYm':'202210','srchToYm':'202210','lv':'7','regSeCd':'1','type':'JSON'}
            if not (evidence['source'] == source and evidence['requested_code'] == '4812311700'
                    and evidence['month'] == month and evidence['params'] == expected_params
                    and evidence['rows'] == [] and evidence['row_count'] == 0
                    and evidence['total_counts'] == [0] and evidence['pages'] == 1):
                raise ValueError('Invalid historical empty-response evidence')
        verified_empty.append('4812311700')
    return {'month':month,'regions':regions,'totals':totals,
            'verified_empty_api_codes': verified_empty,
            'reference_kind':'official_historical_city_district_totals_only'}

def reindex_all(store, totals):
    regions=[r for r in store.list('regions') if str(r.get('id','')).startswith('4812') and not r.get('is_demo')]
    ids={r['id'] for r in regions}
    all_rows=[r for r in store.list('monthly_data') if r.get('region_id') in ids and r.get('month') in totals]
    by_id={r['id']:r for r in all_rows}; grouped={month:[] for month in totals}
    for row in all_rows:grouped[row['month']].append(row)
    for month,rows in sorted(grouped.items()):
        for row in rows:
            rid=row['region_id'];prev=by_id.get(f'{rid}_{month_shift(month,-1)}',{});year=by_id.get(f'{rid}_{month_shift(month,-12)}',{})
            row['derived']=compute_derived(row.get('metrics',{}),prev.get('metrics',{}),year.get('metrics',{}))
        indexes=compute_index_rows(rows);batch=store.client.batch()
        for row in rows:
            rid=row['region_id'];meta={'method_version':'3.7','comparison_scope':'changwon','comparison_month':month,
                                      'comparison_region_count':len(rows),'official_statistic':False,'computed_at':utcnow_iso(),'requires_recompute':False}
            patch={'derived':row['derived'],'indexes':indexes.get(rid,{}),'index_meta':meta}
            batch.update(store.client.collection('monthly_data').document(row['id']),patch)
            if month==max(totals):batch.set(store.client.collection('region_latest').document(rid),patch,merge=True)
        batch.commit()
        print('Historical derived/index recomputation:',month,len(rows),flush=True)

def main(max_months=6,max_minutes=180):
    store=get_store()
    if not isinstance(store,FirestoreStore):raise ValueError('History repair requires Firestore')
    latest=store.get('rollout_reports','changwon_population_repair_v37_2026-09') or store.get('rollout_reports','changwon_population_repair_v37')
    if not latest or latest.get('reconciliation',{}).get('status')!='passed':
        raise RuntimeError('Verified latest-month repair must finish first')
    base=json.loads((ROOT/'data/population_reference_202609.json').read_text())
    totals=json.loads((ROOT/'data/population_official_history_totals.json').read_text())['months']
    begun=time.monotonic();applied=0;remaining=[]
    for month in sorted(totals):
        if month=='2026-09':continue
        checkpoint=store.get('rollout_reports',f'changwon_population_repair_v37_{month}')
        if checkpoint and checkpoint.get('reconciliation',{}).get('status')=='passed':continue
        remaining.append(month)
    for month in remaining:
        if applied>=max_months or time.monotonic()-begun>max_minutes*60:break
        window=remaining[applied:min(applied+3,max_months)]
        if applied%3==0:prefetch(window,base)
        path=OUT/f'historical_reference_{month}.json';OUT.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(reference_for(month,base,totals[month]),ensure_ascii=False))
        repair_month(True,path)
        applied+=1
        save('history_status.json',{'status':'running','applied_this_run':applied,'remaining_months':len(remaining)-applied})
    left=len(remaining)-applied
    if left:
        save('history_status.json',{'status':'needs_continue','applied_this_run':applied,'remaining_months':left})
        return
    # Reconcile every persisted month against independent official totals before reindexing.
    regions=[r for r in store.list('regions') if str(r.get('id','')).startswith('4812') and not r.get('is_demo')]
    for month in sorted(totals):
        rows=[r for r in store.filter_eq('monthly_data','month',month) if str(r.get('region_id','')).startswith('4812')]
        check=population_reconciliation(regions,rows,reference_for(month,base,totals[month]))
        if check['status']!='passed':raise RuntimeError('Persisted historical total validation failed')
    reindex_all(store,totals)
    status={'status':'complete','verified_months':len(totals),'updated_at':utcnow_iso(),
            'historical_validation':'official_city_district_totals_and_API_internal_consistency; independent per-dong history not checked'}
    store.set('rollout_reports','changwon_population_history_v37',status,merge=False)
    save('history_status.json',status)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--max-months',type=int,default=6);p.add_argument('--max-minutes',type=int,default=180);a=p.parse_args()
    try:main(a.max_months,a.max_minutes)
    except Exception as exc:
        save('history_status.json',{'status':'blocked','exception_type':type(exc).__name__,
                                  'instruction':'Inspect checkpoint and artifacts; no immediate automatic retry on failure.'})
        print('History repair blocked:',type(exc).__name__,flush=True);sys.exit(2)
