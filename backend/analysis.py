from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from .db import get_store
from .config import settings

def _in_scope(region: dict) -> bool:
    prefix=settings.analysis_scope_prefix
    return not prefix or str(region.get('bjd_code') or region.get('id') or '').startswith(prefix)

def _month_sort(rows): return sorted(rows, key=lambda x:x.get('month',''))

def list_regions() -> list[dict]:
    return sorted([r for r in get_store().list('regions') if _in_scope(r)], key=lambda x:(x.get('sigungu',''),x.get('name','')))

def find_region_candidates(region_id_or_name: str, limit: int=10) -> list[dict]:
    """지역 코드/정확명/부분명을 검색하되 중복 이름을 임의 선택하지 않는다."""
    store=get_store()
    direct=store.get('regions', region_id_or_name)
    if direct and _in_scope(direct):
        return [direct]
    q=region_id_or_name.strip().lower()
    if not q:
        return []
    rows=list_regions()
    # 1) 전체명 정확 일치
    exact_full=[r for r in rows if str(r.get('full_name','')).strip().lower()==q]
    if exact_full:
        return exact_full[:limit]
    # 2) 짧은 이름 정확 일치. 같은 이름이 여러 시군에 있으면 모두 반환한다.
    exact_name=[r for r in rows if str(r.get('name','')).strip().lower()==q]
    if exact_name:
        return sorted(exact_name,key=lambda r:(r.get('sigungu',''),r.get('name','')))[:limit]
    # 3) 전체명 부분 일치. '창원 상남동'처럼 시군+동을 함께 입력한 경우를 지원한다.
    tokens=[x for x in q.split() if x]
    partial=[]
    for r in rows:
        text=' '.join(str(r.get(k,'')).lower() for k in ('sido','sigungu','name','full_name'))
        if all(token in text for token in tokens):
            partial.append(r)
    return sorted(partial,key=lambda r:(r.get('sigungu',''),r.get('name','')))[:limit]

def resolve_region(region_id_or_name: str) -> dict | None:
    candidates=find_region_candidates(region_id_or_name,limit=20)
    return candidates[0] if len(candidates)==1 else None

def region_resolution_error(region_id_or_name: str) -> dict:
    candidates=find_region_candidates(region_id_or_name)
    if not candidates:
        return {'error':'region_not_found','region':region_id_or_name,'candidates':[]}
    return {
        'error':'region_ambiguous',
        'region':region_id_or_name,
        'message':'같은 이름의 지역이 여러 곳입니다. 시군구를 포함한 전체 지역명 또는 region_id를 사용하세요.',
        'candidates':[{'id':r.get('id'),'name':r.get('name'),'full_name':r.get('full_name'),'sigungu':r.get('sigungu')} for r in candidates],
    }

def series(region_id: str, months: int=36) -> list[dict]:
    if settings.analysis_scope_prefix and not _in_scope(get_store().get('regions',region_id) or {}):
        return []
    # Firestore에서 monthly_data 전체를 읽지 않고 region_id만 읽는다.
    # 경남 전체 운용 시 무료 읽기 쿼터를 지키는 핵심 최적화다.
    rows=get_store().filter_eq('monthly_data','region_id',region_id)
    return _month_sort(rows)[-max(1,months):]

def latest(region_id: str) -> dict | None:
    if settings.analysis_scope_prefix and not _in_scope(get_store().get('regions',region_id) or {}):
        return None
    # 수집 파이프라인이 유지하는 denormalized 최신 snapshot을 우선 사용한다.
    cached=get_store().get('region_latest',region_id)
    if cached: return cached
    s=series(region_id,1); return s[-1] if s else None

def summary(region_id: str, months: int=12) -> dict:
    r=resolve_region(region_id)
    if not r: return region_resolution_error(region_id)
    rows=series(r['id'],months)
    if not rows: return {'region':r,'count':0,'message':'저장된 월별 집계 데이터가 없습니다.'}
    first,last=rows[0],rows[-1]
    def val(row,key): return row.get('derived',{}).get(key, row.get('metrics',{}).get(key))
    pop=[val(x,'population_total') for x in rows if val(x,'population_total') is not None]
    return {
      'region':r,'period':f"{first['month']} ~ {last['month']}",'count':len(rows),
      'metrics':last.get('metrics',{}),'derived':last.get('derived',{}),'indexes':last.get('indexes',{}),
      'index_meta':last.get('index_meta',{}),
      'population_min':min(pop) if pop else None,'population_max':max(pop) if pop else None,
      'freshness':last.get('freshness',{}),
    }

def peer_regions(region_id: str, k: int=2, question: str='') -> list[dict]:
    return comparison_regions(region_id, question=question)['peers'][:k]

def comparison_regions(region_id: str, seed_month: str | None=None, question: str='') -> dict:
    from .topic_comparison import select_comparisons
    base=latest(region_id) or {}
    month=seed_month or base.get('month')
    regions=list_regions()
    rows={r['region_id']:r for r in get_store().filter_eq('monthly_data','month',month)} if month else {}
    # Latest-only fixtures/older installations can use snapshots, but never a different month.
    if month and not rows:
        rows={r.get('region_id') or r['id']:r for r in get_store().list('region_latest') if r.get('month')==month}
    return select_comparisons(region_id,regions,rows,month,question)

def chart_metric(region_ids: list[str], metric_key: str, months: int=36, title: str | None=None, end_month: str | None=None) -> dict:
    def selected(rid):
        return [r for r in series(rid,120) if r['month']<=end_month][-months:] if end_month else series(rid,months)
    all_months=sorted({x['month'] for rid in region_ids for x in selected(rid)})
    datasets=[]
    for rid in region_ids:
        reg=get_store().get('regions',rid) or {'name':rid}
        mapping={}
        for x in selected(rid):
            value=x.get('metrics',{}).get(metric_key)
            if value is None: value=x.get('derived',{}).get(metric_key)
            mapping[x['month']]=value
        datasets.append({'label':reg.get('name',rid),'data':[mapping.get(m) for m in all_months]})
    return {'type':'line','metric':metric_key,'title':title or f'최근 {months}개월 {metric_key} 추세','labels':all_months,'datasets':datasets}

def chart_population(region_ids: list[str], months: int=36) -> dict:
    return chart_metric(region_ids,'population_total',months,f'최근 {months}개월 인구 추세')

def proactive_bundle(region_id: str, answer_mode='basic', question='') -> dict:
    reg=resolve_region(region_id)
    if not reg: return region_resolution_error(region_id)
    months=12 if answer_mode=='simple' else 36
    from .period_selection import requested_month
    reference=requested_month(question)
    if not reference:
        from .dashboard import period_bounds
        minimum, maximum=period_bounds()
        eligible=[row['month'] for row in series(reg['id'],120) if minimum<=row['month']<=maximum]
        reference=max(eligible) if eligible else None
    comps=comparison_regions(reg['id'],reference,question)
    comps={key:value for key,value in comps.items() if key!='neighbors'}
    raw_ids=[reg['id']]+[r['id'] for group in ('peers','seeded_random') for r in comps[group]]
    compare_ids=list(dict.fromkeys(raw_ids))
    def context_summary(rid):
        if not reference:return {'region':get_store().get('regions',rid),'count':0}
        row=get_store().get('monthly_data',f'{rid}_{reference}')
        region=get_store().get('regions',rid)
        return {'region':region,'month':reference,'period':reference+' ~ '+reference,'count':1 if row else 0,
            **{k:(row or {}).get(k,{}) for k in ('metrics','derived','indexes','index_meta','freshness')}}
    comp_summaries={rid:context_summary(rid) for rid in compare_ids}
    charts=[]
    charts.append(chart_metric(compare_ids,'population_total',months,f'최근 {months}개월 인구 추세',end_month=reference))
    if answer_mode=='detail':
        charts.append(chart_metric(compare_ids,'sale_price_per_m2',months,f'최근 {months}개월 ㎡당 매매가격 추세',end_month=reference))
    return {'summary':context_summary(reg['id']),'comparison':comps,'comparison_summaries':comp_summaries,'question':question,'charts':charts,'answer_mode':answer_mode}

def statistics(region_id: str, months: int=36) -> dict:
    rows=series(region_id,months)
    vals=[r.get('metrics',{}).get('population_total') for r in rows]
    vals=[v for v in vals if isinstance(v,(int,float))]
    return {'region_id':region_id,'months':months,'count':len(rows),'population_avg':round(sum(vals)/len(vals),2) if vals else None,'population_min':min(vals) if vals else None,'population_max':max(vals) if vals else None}


