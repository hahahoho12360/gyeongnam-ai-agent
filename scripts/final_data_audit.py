"""Read-only live Firestore audit; no collection or private-record access."""
import sys,json,math
from pathlib import Path
from collections import Counter
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.db import get_store,FirestoreStore,utcnow_iso
from backend.metrics import compute_derived
from backend.indexes import compute_index_rows
from scripts import repair_nonpopulation as nonpop
from scripts.population_history_final import check_totals
from scripts.population_one_month import original_sources_verified

def main():
 store=get_store()
 if not isinstance(store,FirestoreStore):raise RuntimeError('Actual Firestore required')
 regions,children=nonpop.scope(store);ids={r['id'] for r in regions}
 totals=json.loads((ROOT/'data/population_official_history_totals.json').read_text())['months']
 latest={r['id']:r for r in store.list('region_latest') if r['id'] in ids}
 rows=[r for r in store.list('monthly_data') if r.get('region_id') in ids and r.get('month') in totals]
 groups={m:[] for m in totals}
 for row in rows:groups[row['month']].append(row)
 lookup={(r['region_id'],r['month']):r for r in rows};issues=[];coverage=[];warnings=[]
 for m,items in sorted(groups.items()):
  checks=check_totals(items,totals[m]);counts=Counter(r['region_id'] for r in items)
  if len(counts)!=204 or any(v!=1 for v in counts.values()):issues.append({'month':m,'kind':'region_inventory'})
  if checks['status']!='passed':issues.append({'month':m,'kind':'population_totals','problems':checks['problems']})
  if not original_sources_verified(items,ids):warnings.append({'month':m,'kind':'original_population_sources'})
  expected=[]
  for row in items:
   rid=row['region_id'];prior=lookup.get((rid,nonpop.p.month_shift(m,-1)),{});year=lookup.get((rid,nonpop.p.month_shift(m,-12)),{})
   derived=compute_derived(row.get('metrics',{}),prior.get('metrics'),year.get('metrics'))
   if row.get('derived',{})!=derived:issues.append({'month':m,'region_id':rid,'kind':'derived_mismatch'})
   expected.append({**row,'derived':derived})
   meta=row.get('index_meta',{})
   if meta.get('comparison_scope')!='changwon' or meta.get('comparison_month')!=m or meta.get('official_statistic') is not False:
    issues.append({'month':m,'region_id':rid,'kind':'index_metadata'})
   if row.get('indexes_need_recompute'):issues.append({'month':m,'region_id':rid,'kind':'dirty_index'})
  ix=compute_index_rows(expected)
  for row in items:
   if row.get('indexes',{})!=ix[row['region_id']]:issues.append({'month':m,'region_id':row['region_id'],'kind':'index_mismatch'})
  if m==max(totals):
   for row in items:
    if latest.get(row['region_id'],{}).get('metrics')!=row.get('metrics') or latest.get(row['region_id'],{}).get('freshness',{}).get('sources')!=row.get('freshness',{}).get('sources'):
     issues.append({'month':m,'region_id':row['region_id'],'kind':'latest_projection_mismatch'})
  mark=store.get('rollout_reports','changwon_nonpopulation_index_'+m) or {}
  if mark.get('version')!='3.9.2' or mark.get('verified') is not True:issues.append({'month':m,'kind':'index_checkpoint'})
  coverage.append({'month':m,'regions':len(items),'population_totals':checks['status'],'index_counts':{k:sum(isinstance(r.get('indexes',{}).get(k),(int,float)) for r in items) for k in nonpop.compute_index_rows(expected).get(items[0]['region_id'],{})} if items else {}})
 sources=nonpop.audit(store,regions,sorted(totals),'2026-09')['summary']
 if sources.get('unqueried') or sources.get('conflict') or sources.get('legacy_unverified'):issues.append({'kind':'source_incomplete','counts':sources})
 selected=['4812112400','4812725000','4812912400','4812311700']
 public={rid:[r for r in rows if r['region_id']==rid] for rid in selected}
 out=ROOT/'artifacts/final_audit';out.mkdir(parents=True,exist_ok=True)
 report={'created_at':utcnow_iso(),'status':'passed' if not issues else 'needs_fix','region_count':len(ids),'months':len(totals),'monthly_documents':len(rows),'firebase_project':store.client.project,'source_counts':sources,'warnings':warnings,'issue_counts':dict(Counter(x['kind'] for x in issues)),'issues':issues,'coverage':coverage,'limitations':['Current apartment/building/commerce snapshots are not historical inventory series.','Missing source responses remain null, not inferred zeros.']}
 (out/'data_index_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 (out/'representative_public_rows.json').write_text(json.dumps(public,ensure_ascii=False))
 print(json.dumps({k:v for k,v in report.items() if k not in ('issues','coverage')},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
