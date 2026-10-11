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

def reference_for(month, base, totals, validation_policy="strict"):
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
    return {'month':month,'regions':regions,'totals':totals,'validation_policy':validation_policy,
            'verified_empty_api_codes': verified_empty,
            'reference_kind':'official_historical_city_district_totals_only'}

def reindex_all(store, totals, validation_policy="strict"):
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
            rid=row['region_id'];meta={'method_version':'3.7.1-final','comparison_scope':'changwon','comparison_month':month,
                                      'comparison_region_count':len(rows),'official_statistic':False,'computed_at':utcnow_iso(),'requires_recompute':False,'validation_policy':validation_policy,
                                      'population_missing':row.get('metrics',{}).get('population_total') is None}
            patch={'derived':row['derived'],'indexes':indexes.get(rid,{}),'index_meta':meta,'indexes_need_recompute':False}
            batch.update(store.client.collection('monthly_data').document(row['id']),patch)
            if month==max(totals):batch.set(store.client.collection('region_latest').document(rid),patch,merge=True)
        from scripts.population_history_final import commit_batch
        commit_batch(batch)
        print('Historical derived/index recomputation:',month,len(rows),flush=True)

def main(max_months=48,max_minutes=260,validation_policy="totals_first",workers=6):
    from scripts.population_history_final import run
    return run(max_months,max_minutes,validation_policy,workers)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--max-months',type=int,default=48);p.add_argument('--max-minutes',type=int,default=260);p.add_argument('--validation-policy',choices=['strict','totals_first'],default='totals_first');p.add_argument('--workers',type=int,default=6);a=p.parse_args()
    try:main(a.max_months,a.max_minutes,a.validation_policy,a.workers)
    except Exception as exc:
        prior=json.loads((OUT/'history_status.json').read_text()) if (OUT/'history_status.json').exists() else {}
        save('history_status.json',{**prior,'status':'blocked','exception_type':type(exc).__name__,
                                  'instruction':'Inspect checkpoint and artifacts; no immediate automatic retry on failure.'})
        print('History repair blocked:',type(exc).__name__,flush=True);sys.exit(2)
