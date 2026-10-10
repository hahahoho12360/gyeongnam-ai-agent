"""Changwon-only, resumable five-source repair. Never calls population APIs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.db import get_store, FirestoreStore, utcnow_iso
from backend.metrics import compute_derived
from backend.indexes import compute_index_rows
from scripts import pipeline as p
from scripts.collect import adapters as a
from scripts.collect.data_go_kr import DataGoKrClient
from scripts.bootstrap_regions import _is_gyeongnam_eup_myeon_dong
from scripts.repair_population_latest import master_doc

FIELDS = {
 'apt_sale': ['sale_count','sale_total_amount','sale_median_price','sale_price_per_m2','sale_mean_area_m2'],
 'apt_rent': ['rent_count','jeonse_count','monthly_rent_count','jeonse_price','jeonse_price_per_m2','monthly_rent_median','monthly_deposit_median'],
 'apartment_basic': ['apartment_complex_count','apartment_units','apartment_building_count','apartment_total_area_m2'],
 'building_register': ['building_count','old_buildings_30y','building_total_area_m2','residential_building_area_m2','apartment_like_building_count','building_register_household_units'],
 'commerce': ['business_count','business_category_counts','health_business_count','education_business_count','restaurant_count','cafe_count','convenience_store_count'],
}
CATALOG = [
 ('공동주택 단지 목록','apartment_basic','list then detail'),('아파트 매매 실거래가','apt_sale','alternative; never added to detailed trades'),
 ('행정표준 법정동코드','regions','verified master'),('상가(상권)정보','commerce','current snapshot'),
 ('아파트 전월세','apt_rent','monthly'),('아파트 매매 상세','apt_sale','primary monthly'),
 ('건축물대장','building_register','current snapshot'),('공동주택 기본정보','apartment_basic','list then detail'),
 ('성·연령별 1인세대','single_household','audit only'),('성·연령별 인구','age_population','audit only'),
 ('인구·세대','population','audit only'),
]

class CheckedClient(DataGoKrClient):
    def get(self, *args, **kwargs):
        payload = super().get(*args, **kwargs)
        error = self.error_message(payload)
        if error and self.is_no_data_error(error):
            return {'body': {'items': [], 'totalCount': 0}}
        root = payload.get('response', payload.get('Response', payload)) if isinstance(payload, dict) else {}
        body = root.get('body', root) if isinstance(root, dict) else {}
        if not isinstance(body, dict) or not any(k in body for k in ('items','item','totalCount')):
            raise ValueError('Unrecognized API envelope; not confirmed no_data')
        return payload
    def get_all(self, url, params=None, *, page_size=1000, max_pages=1000, json_hint=True):
        out=[]; fingerprints=set(); expected=None
        for page in range(1, max_pages+1):
            payload=self.get(url,{**(params or {}),'pageNo':page,'numOfRows':page_size},json_hint=json_hint)
            rows=self.items(payload); total=self.total_count(payload)
            if total is not None:
                if total < 0 or (expected is not None and total != expected):
                    raise ValueError('Pagination total changed')
                expected=total
            if rows:
                digest=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                if digest in fingerprints: raise ValueError('Repeated API page')
                fingerprints.add(digest)
            out.extend(rows)
            if expected is not None and len(out)>expected: raise ValueError('Pagination exceeds total')
            if expected is not None and len(out)==expected: return out
            if not rows:
                if expected is not None and len(out)!=expected: raise ValueError('Incomplete API pages')
                return out
            if expected is None and len(rows)<page_size: return out
        raise ValueError('Pagination limit reached')

def state(row, source):
    meta=((row or {}).get('freshness',{}).get('sources',{})).get(source) or {}
    metrics=(row or {}).get('metrics',{})
    present=any(metrics.get(k) is not None for k in FIELDS.get(source, []))
    if meta.get('status')=='no_data': return 'conflict' if present else 'no_data'
    if meta and present: return 'stored'
    if present: return 'legacy_unverified'
    return 'unqueried'

def scope(store):
    codes=json.loads((ROOT/'data/current_changwon_codes_verified20261010.json').read_text())
    expected={str(r['region_cd']):master_doc(r) for r in codes if _is_gyeongnam_eup_myeon_dong(r) and str(r['region_cd']).startswith('4812')}
    actual={str(r['id']):r for r in store.list('regions') if str(r.get('id','')).startswith('4812') and not r.get('is_demo')}
    if len(expected)!=204 or set(actual)!=set(expected): raise ValueError('Firebase master differs from verified Changwon 204 codes')
    for rid in actual:
        if str(actual[rid].get('bjd_code',rid))!=rid: raise ValueError('Firebase legal-code mismatch')
    # Population benchmarks omit some legal regions; never use them as the
    # inventory for building/commerce/K-APT collection.
    children={}
    valid_codes={str(r['region_cd']) for r in codes}
    for rid, region in expected.items():
        if region['region_type']=='eup_myeon':
            descendants=sorted(c for c in valid_codes if len(c)==10 and c[:8]==rid[:8] and c!=rid and c[-2:]!='00')
            if not descendants: raise ValueError('Official code master has no ri for eup/myeon')
        else:
            descendants=[rid]
        children[rid]={'children':descendants}
    return list(actual.values()), children

def normalized(row):
    row=dict(row)
    code=row.get('bjdongCd') or row.get('bjdCode')
    if code and len(str(code))==10: row['stdgCd']=str(code)
    return row

def mapped(rows, regions, gu, month=None):
    out=[]
    for raw in rows:
        row=normalized(raw)
        if month:
            y=row.get('dealYear'); m=row.get('dealMonth')
            if y and m and f'{int(y):04d}-{int(m):02d}'!=month: raise ValueError('Trade month mismatch')
            if str(row.get('cdealType','')).strip().upper()=='O': continue
        rid=a.map_region_id(row, regions, sigungu_code=gu)
        if not rid or not rid.startswith(gu): raise ValueError('API row cannot be mapped to requested Changwon district')
        row['stdgCd']=rid
        out.append(row)
    return out

def unique(rows, field):
    seen={}
    for row in rows:
        key=str(row.get(field) or '')
        if not key: raise ValueError('Missing stable source identifier')
        if key in seen and seen[key]!=row: raise ValueError('Conflicting duplicate source identifier')
        seen[key]=row
    return list(seen.values())

def collect(source, month, group, regions, children, client):
    gu=group[0]['id'][:5]
    if source in ('apt_sale','apt_rent','commerce'):
        params={'divId':'signguCd','key':gu,'type':'json'} if source=='commerce' else {'LAWD_CD':gu,'DEAL_YMD':month.replace('-','')}
        rows=client.get_all(p.DEFAULT_ENDPOINTS[source],params,json_hint=False)
        rows=mapped(rows,regions,gu,month if source!='commerce' else None)
        if source=='commerce': rows=unique(rows,'bizesId')
        fn={'apt_sale':a.aggregate_apartment_sales,'apt_rent':a.aggregate_apartment_rent,'commerce':a.aggregate_commerce}[source]
        patches=fn(rows,regions,gu) if source=='commerce' else fn(rows,regions,month,gu)
    else:
        rid=group[0]['id']; rows=[]
        for code in children[rid]['children']:
            if source=='building_register':
                part=client.get_all(p.DEFAULT_ENDPOINTS[source],{'sigunguCd':code[:5],'bjdongCd':code[5:],'_type':'json'})
                for raw in part:
                    row=dict(raw)
                    if row.get('sigunguCd') and row.get('bjdongCd') and str(row['sigunguCd'])+str(row['bjdongCd'])!=code: raise ValueError('Building query code mismatch')
                    row['stdgCd']=rid; rows.append(row)
            else:
                listed=client.get_all(p.DEFAULT_ENDPOINTS['apt_list'],{'bjdCode':code},page_size=100,json_hint=False)
                for item in unique(listed,'kaptCode'):
                    detail=client.get(p.DEFAULT_ENDPOINTS[source],{'kaptCode':item['kaptCode']},json_hint=False,add_paging=False)
                    details=client.items(detail)
                    if len(details)!=1 or str(details[0].get('kaptCode') or item['kaptCode'])!=str(item['kaptCode']): raise ValueError('Listed complex has missing/mismatched detail')
                    row={**item,**details[0]}
                    code_return=str(row.get('bjdCode') or code)
                    if code_return!=code: raise ValueError('Complex legal-code mismatch')
                    row['bjdCode']=rid; rows.append(row)
        if source=='building_register':
            rows=unique(rows,'mgmBldrgstPk'); patches=a.aggregate_buildings(rows,group,as_of=date.today(),sigungu_code=gu)
        else:
            rows=unique(rows,'kaptCode'); patches=a.aggregate_apartment_basic(rows,group)
    # Successful complete query is necessary before an absent region is labelled no_data.
    counts=Counter(a.map_region_id({**r,'stdgCd':r.get('stdgCd') or r.get('bjdCode')},regions,sigungu_code=gu) for r in rows)
    return patches, counts

def merge_patch(current, source, patch, month, rid, count):
    if count < 0 or bool(patch) != bool(count): raise ValueError('Source rows and aggregate patch disagree')
    if source not in FIELDS or not set(patch).issubset(FIELDS[source]): raise ValueError('Source patch contains unowned fields')
    if state(current,source)!='unqueried': return None
    row=dict(current or {}); metrics={**row.get('metrics',{}),**patch}
    freshness=dict(row.get('freshness',{})); sources=dict(freshness.get('sources',{}))
    sources[source]={'status':'success' if count else 'no_data','sample_size':count,'fetched_at':utcnow_iso(),
                     'source_as_of':p.month_end(month) if source in ('apt_sale','apt_rent') else date.today().isoformat(),
                     'collection_method':'monthly_api' if source in ('apt_sale','apt_rent') else 'current_snapshot_in_analysis_bucket'}
    freshness.update({'sources':sources,'is_demo':False,'fetched_at':utcnow_iso()})
    row.update({'region_id':rid,'month':month,'metrics':metrics,'freshness':freshness,'indexes_need_recompute':True})
    return row

def apply_patch(store, source, patch, month, rid, count):
    from google.cloud import firestore
    doc=store.client.collection('monthly_data').document(f'{rid}_{month}')
    latest=store.client.collection('region_latest').document(rid)
    @firestore.transactional
    def write(tx):
        current=doc.get(transaction=tx).to_dict() or {}
        last=latest.get(transaction=tx).to_dict() or {}
        row=merge_patch(current,source,patch,month,rid,count)
        if row is None: return False
        row.pop('id',None)
        tx.set(doc,row,merge=True)
        if last.get('month')==month or (not last and month<=date.today().strftime('%Y-%m')):
            tx.set(latest,{**last,**row},merge=True)
        return True
    return write(store.client.transaction())

def audit(store, regions, months, snapshot):
    records={}
    for month in sorted(set(months+[snapshot])):
        records[month]={r['region_id']:r for r in store.filter_eq('monthly_data','month',month) if r.get('region_id') in {x['id'] for x in regions}}
    matrix=[]
    for source in FIELDS:
        for month in (months if source in ('apt_sale','apt_rent') else [snapshot]):
            for r in regions: matrix.append({'source':source,'month':month,'region_id':r['id'],'name':r['name'],'status':state(records[month].get(r['id']),source)})
    api=[]
    for name,source,role in CATALOG:
        if source=='regions': counts={'verified_master':len(regions)}
        elif source in FIELDS: counts=dict(Counter(r['status'] for r in matrix if r['source']==source))
        else:
            counts=dict(Counter('no_data' if (((row.get('freshness') or {}).get('sources') or {}).get(source) or {}).get('status')=='no_data' else 'recorded' if source in ((row.get('freshness') or {}).get('sources') or {}) else 'unqueried' for row in [records[snapshot].get(r['id'],{}) for r in regions]))
        api.append({'api':name,'source':source,'role':role,'firebase_counts':counts,'endpoint_access_tested':False})
    return {'created_at':utcnow_iso(),'region_count':204,'apis':api,'matrix':matrix,'summary':dict(Counter(r['status'] for r in matrix)),
            'population_action':'audit_only_no_population_API_calls','snapshot_observation_date':date.today().isoformat()}

def reindex(store, regions, month):
    ids={r['id'] for r in regions}
    rows=[r for r in store.filter_eq('monthly_data','month',month) if r.get('region_id') in ids]
    previous={r['region_id']:r for r in store.filter_eq('monthly_data','month',p.month_shift(month,-1))}
    yearly={r['region_id']:r for r in store.filter_eq('monthly_data','month',p.month_shift(month,-12))}
    for row in rows: row['derived']=compute_derived(row.get('metrics',{}),previous.get(row['region_id'],{}).get('metrics'),yearly.get(row['region_id'],{}).get('metrics'))
    indexes=compute_index_rows(rows)
    for row in rows:
        changes={'derived':row['derived'],'indexes':indexes.get(row['region_id'],{}),'indexes_need_recompute':False}
        store.update('monthly_data',row['id'],changes)
        latest=store.get('region_latest',row['region_id'])
        if latest and latest.get('month')==month: store.update('region_latest',row['region_id'],changes)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['audit','fill'],default='audit')
    parser.add_argument('--start',default='2022-10'); parser.add_argument('--end',default='2026-09')
    parser.add_argument('--snapshot',default='2026-09'); parser.add_argument('--max-months',type=int,default=6)
    args=parser.parse_args()
    for value in (args.start,args.end,args.snapshot):
        if date.fromisoformat(value+'-01').strftime('%Y-%m')!=value: raise ValueError('Invalid month')
    if args.start>args.end or args.end>=date.today().strftime('%Y-%m') or args.snapshot>date.today().strftime('%Y-%m') or args.max_months<1: raise ValueError('Invalid collection range')
    store=get_store()
    if not isinstance(store,FirestoreStore): raise ValueError('Real Firebase required; demo DB forbidden')
    regions,children=scope(store); months=p.month_range(args.start,args.end)
    out=ROOT/'artifacts/nonpopulation'; out.mkdir(parents=True,exist_ok=True)
    def report(name):
        result=audit(store,regions,months,args.snapshot)
        (out/f'{name}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        return result
    before=report('before'); errors=[]; changed=set(); applied=0
    if args.mode=='fill':
        client=CheckedClient()
        for source in FIELDS:
            pending=[r for r in before['matrix'] if r['source']==source and r['status']=='unqueried']
            target_months=sorted({r['month'] for r in pending})[:args.max_months]
            for month in target_months:
                ids={r['region_id'] for r in pending if r['month']==month}
                group_ids=sorted({rid[:5] if source in ('apt_sale','apt_rent','commerce') else rid for rid in ids})
                for group_id in group_ids:
                    group=[r for r in regions if r['id'].startswith(group_id)]
                    try:
                        patches,counts=collect(source,month,group,regions,children,client)
                        staged={'source':source,'month':month,'group':group_id,'patches':{rid:patches.get(rid,{}) for rid in ids if rid.startswith(group_id)},'counts':dict(counts)}
                        # Aggregate-only artifact; API keys and raw responses are never persisted.
                        (out/f'stage_{source}_{month}_{group_id}.json').write_text(json.dumps(staged,ensure_ascii=False,indent=2))
                        for rid,patch in staged['patches'].items():
                            if apply_patch(store,source,patch,month,rid,counts.get(rid,0)): applied+=1; changed.add(month)
                    except Exception as exc:
                        errors.append({'source':source,'month':month,'group':group_id,'error_type':type(exc).__name__})
                        print(json.dumps(errors[-1])) # Exceptions can contain serviceKey URLs; never print them.
        # Also repairs indexes if a prior interrupted run committed records before reindexing.
        for month in sorted(({m for m in months+[args.snapshot] if changed and m>=min(changed)})|{r['month'] for r in store.list('monthly_data') if r.get('region_id') in {x['id'] for x in regions} and r.get('indexes_need_recompute')}): reindex(store,regions,month)
    after=report('after')
    final={'mode':args.mode,'applied':applied,'errors':errors,'remaining':after['summary'],'needs_rerun':bool(after['summary'].get('unqueried')),'manual_review':bool(errors or after['summary'].get('conflict') or after['summary'].get('legacy_unverified'))}
    (out/'result.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)); print(json.dumps(final,ensure_ascii=False))
    if errors: raise SystemExit(1)
if __name__=='__main__': main()
