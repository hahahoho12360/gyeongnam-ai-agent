"""Compare suspect small-area values to the same-month original API, read-only."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.population_one_month import configure,BoundedClient,Budget
from scripts.probe_population_repair import query
from scripts.population_repair_core import validate_rows,ADAPTERS
from scripts.collect.redaction import redact
from backend.db import get_store
from backend.dashboard import value

configure();BoundedClient.budget=Budget(900,threshold=6,max_recoveries=1)
out=ROOT/'artifacts/small_population';out.mkdir(parents=True,exist_ok=True)
store=get_store();month='2026-09';results=[]
for rid in ['4812310700','4812311400','4812311700','4812912500','4812915300','4812110800','4812111400','4812312200','4812310100','4812311200','4812311300','4812311500','4812314100']:
 region=store.get('regions',rid);stored=store.get('monthly_data',f'{rid}_{month}') or {};patches={};raw={};errors=[]
 for source in ['population','age_population']:
  try:
   rows=query(BoundedClient(),source,rid,month);raw[source]=rows
   checked=validate_rows(rows,rid,month)
   patches[source]=ADAPTERS[source](checked,[region],rid[:5]).get(rid,{})
  except Exception as exc:errors.append({'source':source,'type':type(exc).__name__})
 api_pop=patches.get('population',{}).get('population_total');api_young=patches.get('age_population',{}).get('age_20_39')
 item={'region_id':rid,'region_name':region.get('full_name'),'month':month,'raw_rows':raw,'errors':errors,
       'original_population':api_pop,'original_young_20_39':api_young,
       'stored_population':stored.get('metrics',{}).get('population_total'),'stored_young_20_39':stored.get('metrics',{}).get('age_20_39'),
       'dashboard_population':value(stored,'population_total'),'dashboard_young_share':value(stored,'young_population_share')}
 item['matches']=not errors and api_pop==item['stored_population'] and api_young==item['stored_young_20_39']
 results.append(item);(out/'original_comparison.json').write_text(json.dumps(redact(results),ensure_ascii=False,indent=2))
 print(json.dumps({k:v for k,v in item.items() if k!='raw_rows'},ensure_ascii=False),flush=True)
