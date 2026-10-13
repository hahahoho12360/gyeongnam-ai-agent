"""Changwon-only, resumable five-source repair. Never calls population APIs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import time
from functools import lru_cache
from collections import Counter
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.db import get_store, FirestoreStore, utcnow_iso
from backend.metrics import compute_derived
from backend.indexes import compute_index_rows,methodology_payload
from scripts import pipeline as p
from scripts.collect import adapters as a
from scripts.collect.data_go_kr import DataGoKrClient
from scripts.collect.redaction import redact
import requests
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

VERSION = '3.9.2'

class DiagnosticError(ValueError):
    def __init__(self, category, **details):
        self.category = category
        self.details = details
        super().__init__(category)

def diagnostic(exc):
    # Never include arbitrary exception strings, URLs, addresses or credentials.
    if isinstance(exc, DiagnosticError):
        return {'category': exc.category, **exc.details}
    category=('응답 시간 초과' if isinstance(exc,requests.exceptions.ReadTimeout) else
        '연결 시간 초과' if isinstance(exc,requests.exceptions.ConnectTimeout) else
        '일시 연결 장애' if isinstance(exc,requests.exceptions.ConnectionError) else
        'HTTP 요청 실패' if isinstance(exc,requests.exceptions.HTTPError) else 'API 또는 저장 처리 실패')
    return {'category':category,'error_type':type(exc).__name__}

TRANSIENT={'응답 시간 초과','연결 시간 초과','일시 연결 장애','일시 서버 장애'}

class CollectionBudget:
    def __init__(self,deadline):self.deadline=deadline;self.failures=0
    def check(self):
        if time.monotonic()>self.deadline-120:raise DiagnosticError('작업 시간 예산 도달')
        if self.failures>=3:raise DiagnosticError('반복 연결 실패로 보류')


def collect_cached(source,month,group,regions,children,client,out):
    gid=group[0]['id'][:5] if source in ('apt_sale','apt_rent','commerce') else group[0]['id']
    path=out/f'capture_{source}_{month}_{gid}.json'
    if path.exists():
        try:
            d=json.loads(path.read_text())
            if (d.get('version')==VERSION and d.get('source')==source and d.get('month')==month
                    and d.get('group')==gid and d.get('successful_query') is True):
                targets={r['id'] for r in group}
                if not set(d['patches']).issubset(targets) or not set(d['counts']).issubset(targets):raise ValueError()
                for rid in targets:
                    if bool(d['patches'].get(rid))!=bool(d['counts'].get(rid,0)):raise ValueError()
                return d['patches'],Counter(d['counts'])
        except (ValueError,KeyError,TypeError):
            path.rename(path.with_name('invalid_'+path.name))
    for attempt in range(2):
        client.last_rows=[]
        try:
            patches,counts=collect(source,month,group,regions,children,client)
            path.write_text(json.dumps(redact({'version':VERSION,'source':source,'month':month,'group':gid,
                'successful_query':True,'patches':patches,'counts':dict(counts)}),ensure_ascii=False))
            return patches,counts
        except Exception as exc:
            info=diagnostic(exc)
            (out/f'failed_{source}_{month}_{gid}_{attempt}.json').write_text(json.dumps(redact({
                'source':source,'month':month,'group':gid,'diagnostic':info,
                'received_rows':getattr(client,'last_rows',[]),'successful_query':False}),ensure_ascii=False))
            if attempt or info['category'] not in TRANSIENT:raise
            if callable(getattr(client,'before_request',None)):client.before_request()
            time.sleep(5)


def verify_group(store,source,month,expected,out,gid):
    records={r['region_id']:r for r in store.filter_eq('monthly_data','month',month)}
    mismatches=[]
    for rid,(patch,count) in expected.items():
        row=records.get(rid,{})
        if state(row,source)!=('stored' if count else 'no_data') or any(row.get('metrics',{}).get(k)!=v for k,v in patch.items()):
            mismatches.append(rid)
    (out/f'verified_{source}_{month}_{gid}.json').write_text(json.dumps({'checked_regions':len(expected),'mismatches':mismatches}))
    if mismatches:raise DiagnosticError('저장 후 재조회 불일치',region_ids=mismatches)


@lru_cache(maxsize=1)
def official_inventory():
    return {str(r['region_cd']): r for r in json.loads((ROOT/'data/current_changwon_codes_verified20261010.json').read_text())}

def safe_fields(row):
    result = {}
    for key in ('sggCd','umdCd','stdgCd','bjdCode','bjdongCd','umdNm','dealYear','dealMonth'):
        value = str(row.get(key, ''))
        if value and len(value) <= 80 and all(c.isalnum() or c in ' -·' for c in value):
            result[key] = value
    return result

class CheckedClient(DataGoKrClient):
    def get(self, *args, **kwargs):
        try:
            payload = super().get(*args, **kwargs)
        except requests.exceptions.HTTPError as exc:
            status=getattr(exc.response,'status_code',None)
            raise DiagnosticError('요청 제한' if status==429 else '일시 서버 장애' if status and status>=500 else '인증 또는 요청 오류',http_status=status) from None
        error=self.error_message(payload)
        if error and not self.is_no_data_error(error):raise DiagnosticError('API 결과 오류')
        error = self.error_message(payload)
        if error and self.is_no_data_error(error):
            return {'body': {'items': [], 'totalCount': 0}}
        root = payload.get('response', payload.get('Response', payload)) if isinstance(payload, dict) else {}
        body = root.get('body', root) if isinstance(root, dict) else {}
        if not isinstance(body, dict) or not any(k in body for k in ('items','item','totalCount')):
            raise DiagnosticError('응답 형식 오류')
        return payload
    def get_all(self, url, params=None, *, page_size=1000, max_pages=1000, json_hint=True):
        out=[]; self.last_rows=[]; fingerprints=set(); expected=None
        for page in range(1, max_pages+1):
            payload=self.get(url,{**(params or {}),'pageNo':page,'numOfRows':page_size},json_hint=json_hint)
            rows=self.items(payload); total=self.total_count(payload)
            if total is not None:
                if total < 0 or (expected is not None and total != expected):
                    raise DiagnosticError('페이지 총건수 변경', page=page)
                expected=total
            if rows:
                digest=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                if digest in fingerprints: raise DiagnosticError('페이지 반복', page=page)
                fingerprints.add(digest)
            out.extend(rows); self.last_rows=list(out)
            if expected is not None and len(out)>expected: raise DiagnosticError('페이지 건수 초과', page=page)
            if expected is not None and len(out)==expected: return out
            if not rows:
                if expected is not None and len(out)!=expected: raise DiagnosticError('페이지 누락', page=page, expected=expected, received=len(out))
                return out
            if expected is None and len(rows)<page_size: return out
        raise DiagnosticError('페이지 상한 초과')

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
    code=row.get('stdgCd') or row.get('bjdCd') or row.get('bjd_code') or row.get('bjdongCd') or row.get('bjdCode')
    if code and len(str(code).strip())==10:
        row['stdgCd']=str(code).strip()
    elif row.get('sggCd') and row.get('umdCd'):
        sig=str(row['sggCd']).strip(); suffix=str(row['umdCd']).strip()
        if sig.isdigit() and len(sig)==5 and suffix.isdigit() and len(suffix)<=5:
            row['stdgCd']=sig+suffix.zfill(5)
    return row

def resolve_region(row, regions, gu):
    inventory=official_inventory(); targets={r['id']:r for r in regions if r['id'].startswith(gu)}
    code=row.get('stdgCd')
    if code:
        if code not in inventory or not code.startswith(gu):
            raise DiagnosticError('지역 코드 불일치', **safe_fields(row))
        parent=code if code in targets else code[:8]+'00'
        if parent not in targets:
            raise DiagnosticError('지역 연결 실패', **safe_fields(row))
        return parent
    sig=str(row.get('sggCd') or row.get('signguCd') or gu)
    if sig != gu:
        raise DiagnosticError('지역 코드 불일치', **safe_fields(row))
    name=' '.join(str(row.get('umdNm') or row.get('stdgNm') or row.get('dongNm') or '').split())
    if name:
        matches=set()
        for legal, entry in inventory.items():
            if not legal.startswith(gu): continue
            full=entry['locatadd_nm']; local=full.split(gu_name(entry),1)[-1].strip()
            if name in (full, local):
                parent=legal if legal in targets else legal[:8]+'00'
                if parent in targets: matches.add(parent)
        if len(matches)==1: return matches.pop()
        raise DiagnosticError('지역 연결 실패', **safe_fields(row))
    # Commerce supplies legal codes or official address fields instead of umdNm.
    rid=a.map_region_id(row,regions,sigungu_code=gu)
    if rid in targets: return rid
    raise DiagnosticError('지역 연결 실패', **safe_fields(row))

def gu_name(entry):
    return next((part for part in entry['locatadd_nm'].split() if part.endswith('구')), '')

def mapped(rows, regions, gu, month=None):
    out=[]
    for raw in rows:
        row=normalized(raw)
        if month:
            try:
                actual=f"{int(row['dealYear']):04d}-{int(row['dealMonth']):02d}"
            except (KeyError, ValueError, TypeError):
                raise DiagnosticError('기준월 누락', **safe_fields(row)) from None
            if actual!=month: raise DiagnosticError('기준월 불일치', requested_month=month, **safe_fields(row))
        rid=resolve_region(row,regions,gu)
        if month and str(row.get('cdealType','')).strip().upper()=='O': continue
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
    marker=f'changwon_nonpopulation_index_{month}'
    checkpoint=store.get('rollout_reports',marker) or {}
    if checkpoint.get('version')==VERSION and checkpoint.get('verified') is True and not any(r.get('indexes_need_recompute') for r in rows):
        return False
    previous={r['region_id']:r for r in store.filter_eq('monthly_data','month',p.month_shift(month,-1))}
    yearly={r['region_id']:r for r in store.filter_eq('monthly_data','month',p.month_shift(month,-12))}
    latest={r['id']:r for r in store.list('region_latest') if r.get('id') in ids}
    for row in rows: row['derived']=compute_derived(row.get('metrics',{}),previous.get(row['region_id'],{}).get('metrics'),yearly.get(row['region_id'],{}).get('metrics'))
    indexes=compute_index_rows(rows)
    batch=store.client.batch()
    for row in rows:
        changes={'derived':row['derived'],'indexes':indexes.get(row['region_id'],{}),'indexes_need_recompute':False,
                 'index_meta':{**row.get('index_meta',{}),**methodology_payload(comparison_scope='changwon',month=month,region_count=len(rows)),
                    'computed_at':utcnow_iso(),'nonpopulation_version':VERSION,'requires_recompute':False}}
        batch.update(store.client.collection('monthly_data').document(row['id']),changes)
        if latest.get(row['region_id'],{}).get('month')==month:
            batch.update(store.client.collection('region_latest').document(row['region_id']),changes)
    batch.set(store.client.collection('rollout_reports').document(marker),{'version':VERSION,'month':month,'region_count':len(rows),'completed_at':utcnow_iso(),'verified':False})
    # At most 204 monthly + 204 latest + one checkpoint, below Firestore 500.
    from scripts.population_history_final import commit_batch
    commit_batch(batch)
    actual={r['region_id']:r for r in store.filter_eq('monthly_data','month',month)}
    mismatches=[r['region_id'] for r in rows if actual.get(r['region_id'],{}).get('derived')!=r['derived']
        or actual.get(r['region_id'],{}).get('indexes')!=indexes.get(r['region_id'],{})]
    if mismatches:raise DiagnosticError('지수 저장 후 재조회 불일치',month=month,region_ids=mismatches)
    store.set('rollout_reports',marker,{'verified':True,'verified_regions':len(rows)},merge=True)
    return True

def preflight(client, regions, children, month, out):
    checks=[]; cached={}; errors=[]
    for source in ('apt_sale','apt_rent'):
        for gu in sorted({r['id'][:5] for r in regions}):
            try:
                group=[r for r in regions if r['id'].startswith(gu)]
                cached[(source,month,gu)]=collect_cached(source,month,group,regions,children,client,out)
                checks.append({'source':source,'month':month,'group':gu,'status':'passed',
                               'mapped_rows':sum(cached[(source,month,gu)][1].values())})
            except Exception as exc:
                item={'source':source,'month':month,'group':gu,**diagnostic(exc)}
                errors.append(item); checks.append({**item,'status':'failed'})
    (out/'preflight.json').write_text(json.dumps({'version':VERSION,'checks':checks,'errors':errors},ensure_ascii=False,indent=2))
    return cached,errors


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['audit','fill'],default='audit')
    parser.add_argument('--start',default='2022-10'); parser.add_argument('--end',default='2026-09')
    parser.add_argument('--snapshot',default='2026-09'); parser.add_argument('--max-months',type=int,default=6)
    parser.add_argument('--max-minutes',type=int,default=250)
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
    started=time.monotonic(); deadline=started+args.max_minutes*60; timed_out=False; blocked=False
    if args.mode=='fill':
        budget=CollectionBudget(deadline-20*60)
        client=CheckedClient(timeout=(15,60),max_retries=1)
        client.before_request=budget.check
        pending_months=sorted({r['month'] for r in before['matrix'] if r['source'] in ('apt_sale','apt_rent') and r['status']=='unqueried'})
        cached,errors=preflight(client,regions,children,pending_months[0] if pending_months else args.end,out)
        blocked=bool(errors)
        for source in ([] if blocked else FIELDS):
            pending=[r for r in before['matrix'] if r['source']==source and r['status']=='unqueried']
            target_months=sorted({r['month'] for r in pending})[:args.max_months]
            for month in target_months:
                ids={r['region_id'] for r in pending if r['month']==month}
                group_ids=sorted({rid[:5] if source in ('apt_sale','apt_rent','commerce') else rid for rid in ids})
                for group_id in group_ids:
                    if time.monotonic()>deadline-20*60:
                        timed_out=True; break
                    group=[r for r in regions if r['id'].startswith(group_id)]
                    try:
                        key=(source,month,group_id)
                        patches,counts=cached.pop(key) if key in cached else collect_cached(source,month,group,regions,children,client,out)
                        staged={'source':source,'month':month,'group':group_id,'patches':{rid:patches.get(rid,{}) for rid in ids if rid.startswith(group_id)},'counts':dict(counts)}
                        # Aggregate-only artifact; API keys and raw responses are never persisted.
                        (out/f'stage_{source}_{month}_{group_id}.json').write_text(json.dumps(staged,ensure_ascii=False,indent=2))
                        expected={}
                        for rid,patch in staged['patches'].items():
                            if apply_patch(store,source,patch,month,rid,counts.get(rid,0)):
                                applied+=1; changed.add(month);expected[rid]=(patch,counts.get(rid,0))
                        verify_group(store,source,month,expected,out,group_id)
                        budget.failures=0
                        (out/'progress.json').write_text(json.dumps({'source':source,'month':month,'group':group_id,'applied':applied,'updated_at':utcnow_iso()}))
                    except Exception as exc:
                        errors.append({'source':source,'month':month,'group':group_id,**diagnostic(exc)})
                        if errors[-1]['category'] in TRANSIENT:budget.failures+=1
                        if errors[-1]['category'] in {'작업 시간 예산 도달','반복 연결 실패로 보류','요청 제한','인증 또는 요청 오류','API 결과 오류'}:timed_out=True;break
                        print(json.dumps(errors[-1])) # Exceptions can contain serviceKey URLs; never print them.
        # Source edits affect following month and same month next year too.
        index_months=set(months+[args.snapshot])
        dirty={r['month'] for r in store.list('monthly_data') if r.get('region_id') in {x['id'] for x in regions} and r.get('indexes_need_recompute')}
        changed |= dirty
        invalidated=changed | {p.month_shift(m,1) for m in changed} | {p.month_shift(m,12) for m in changed}
        if not blocked:
            for month in sorted(index_months & invalidated):
                store.set('rollout_reports',f'changwon_nonpopulation_index_{month}',{'version':'invalidated'},merge=True)
        pending_after_fill=audit(store,regions,months,args.snapshot)['summary'].get('unqueried',0)
        # Recalculate once after all sources complete, not after every six-month chunk.
        for month in ([] if pending_after_fill or errors else sorted(index_months)):
            if time.monotonic()>deadline: timed_out=True; break
            if blocked: break
            reindex(store,regions,month)
    after=report('after')
    status='blocked' if blocked else 'partial' if errors else 'needs_continue' if after['summary'].get('unqueried') or timed_out else 'needs_review' if after['summary'].get('conflict') or after['summary'].get('legacy_unverified') else 'complete'
    retryable_errors=bool(errors) and all(e.get('category') in TRANSIENT | {'작업 시간 예산 도달','반복 연결 실패로 보류'} for e in errors)
    final={'retryable_errors':retryable_errors,'version':VERSION,'status':status,'elapsed_seconds':round(time.monotonic()-started),'mode':args.mode,'applied':applied,'errors':errors,'remaining':after['summary'],'needs_rerun':bool(after['summary'].get('unqueried')),'manual_review':bool(errors or after['summary'].get('conflict') or after['summary'].get('legacy_unverified'))}
    (out/'result.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)); print(json.dumps(final,ensure_ascii=False))
    if blocked: raise SystemExit(2)
if __name__=='__main__': main()
