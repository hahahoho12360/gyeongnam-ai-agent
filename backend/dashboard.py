"""Read-only Changwon dashboard: same-month comparisons and gap-safe trends."""
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from . import analysis
from .db import get_store
from .index_evidence import evidence, period_change

METRICS=[
 ('population_total','주민등록 인구(명)','인구','명'),
 ('young_population_share','청년 비율(20~39세, %)','청년 비율','%'),
 ('single_household_share','1인세대 비율(%)','1인세대 비율','%'),
 ('sale_price_per_m2','아파트 매매 전용면적 ㎡당 중앙가격(원)','아파트 ㎡당 가격','원/㎡'),
 ('sale_price_yoy_pct','아파트 ㎡당 중앙가격 전년 대비(%)','가격 전년 대비','%'),
 ('vitality_index','지역활력지수','지역활력','점'),
 ('housing_pressure_index','주거시장압력지수','주거시장압력','점'),
 ('living_convenience_index','생활편의지수','생활편의','점'),
 ('commerce_change_index','상권활력 대리지수','상권활력','점'),
]

GRAPH_METRICS=METRICS[:3]+[
 ('households','주민등록 세대 수','주민등록 세대 수','세대'),
 ('age_20_39','청년 인구 수(20~39세)','청년 인구 수(20~39세)','명'),
 ('single_households','1인세대 수','1인세대 수','세대'),
 ('age_60_plus','60세 이상 인구 수','60세 이상 인구 수','명'),
 ('under_20','20세 미만 인구 수','20세 미만 인구 수','명'),
]

def numeric(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def shift(month,delta):
    y,m=map(int,month.split('-')); n=y*12+m-1+delta
    return f'{n//12:04d}-{n%12+1:02d}'

def value(row,key,year_ago=None):
    if not row or row.get('freshness',{}).get('is_demo'): return None
    m=row.get('metrics',{}); sources=row.get('freshness',{}).get('sources',{})
    def raw(k,source):
        v=m.get(k)
        return v if numeric(v) and sources.get(source,{}).get('status')!='no_data' else None
    if key=='young_population_share':
        n=raw('age_20_39','age_population'); den=raw('population_total','population')
        return n/den*100 if n is not None and den is not None and den>0 and 0<=n<=den else None
    if key=='single_household_share':
        n=raw('single_households','single_household'); den=raw('households','population')
        return n/den*100 if n is not None and den is not None and den>0 and 0<=n<=den else None
    if key=='sale_price_yoy_pct':
        current=raw('sale_price_per_m2','apt_sale'); previous=value(year_ago,'sale_price_per_m2')
        return (current/previous-1)*100 if current is not None and previous is not None and previous>0 else None
    if key=='under_20':
        a=raw('age_0_9','age_population'); b=raw('age_10_19','age_population')
        return a+b if a is not None and b is not None else None
    sources_by_key={'households':'population','age_20_39':'age_population','age_60_plus':'age_population','single_households':'single_household','business_count':'commerce'}
    if key in sources_by_key: return raw(key,sources_by_key[key])
    if key in ('population_total','sale_price_per_m2'):

        return raw(key,'population' if key=='population_total' else 'apt_sale')
    # In-progress repairs must not expose a stale index as a comparable score.
    if row.get('indexes_need_recompute'): return None
    meta=row.get('index_meta',{})
    if meta.get('comparison_scope') not in ('changwon', '4812') or meta.get('comparison_month')!=row.get('month'): return None
    v=row.get('indexes',{}).get(key)
    return v if numeric(v) else None

def metric_basis(row,key):
    """Explain a valid value without replacing true zero or excluding small areas."""
    if value(row,key) is None: return None
    m=(row or {}).get('metrics',{})
    if key=='young_population_share':
        return {'numerator':m['age_20_39'],'denominator':m['population_total'],'numerator_label':'20~39세','denominator_label':'주민등록 인구','unit':'명'}
    if key=='single_household_share':
        return {'numerator':m['single_households'],'denominator':m['households'],'numerator_label':'1인세대','denominator_label':'전체 세대','unit':'세대'}
    if key=='population_total': return {'count':m['population_total'],'unit':'명'}
    return None

PERIOD_MIN='2022-10'

def period_bounds(now=None):
    current=now or datetime.now(ZoneInfo('Asia/Seoul'))
    if current.tzinfo is not None: current=current.astimezone(ZoneInfo('Asia/Seoul'))
    return PERIOD_MIN,shift(current.strftime('%Y-%m'),-1)

def validate_period(start_month=None,end_month=None):
    minimum,maximum=period_bounds()
    for month in (start_month,end_month):
        if month and not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])",month):
            raise ValueError('기준월은 YYYY-MM 형식으로 입력하세요.')
        if month and not minimum<=month<=maximum:
            raise ValueError(f'조회 기간은 {minimum}부터 {maximum}(한국 시간 기준 직전 월)까지 선택할 수 있어요.')
    if start_month and end_month and start_month>end_month:
        raise ValueError('시작월은 종료월보다 늦을 수 없어요.')
    if start_month and end_month:
        y,m=map(int,start_month.split('-')); ey,em=map(int,end_month.split('-'))
        if (ey-y)*12+em-m>=120: raise ValueError('한 번에 최대 120개월을 조회할 수 있어요.')

def dashboard(region_id,answer_mode='basic',start_month=None,end_month=None,question=''):
    validate_period(start_month,end_month)
    region=analysis.resolve_region(region_id)
    if not region or not str(region.get('bjd_code') or region['id']).startswith('4812'):
        return {'error':'region_not_found','message':'창원 법정읍·면·동을 선택하세요.'}
    bundle={'comparison':{},'answer_mode':answer_mode,'summary':{'region':region,'count':0}}
    store=get_store()
    master={r['id']:r for r in analysis.list_regions() if str(r.get('bjd_code') or r['id']).startswith('4812') and not r.get('is_demo')}
    minimum,maximum=period_bounds()
    bundle.update(period_min=minimum,period_max=maximum)
    target=[r for r in analysis.series(region['id'],120) if minimum<=r['month']<=maximum]
    from .period_selection import requested_month
    month=end_month or requested_month(question) or (target[-1]['month'] if target else None)
    if month:
        start_month=start_month or max(minimum,shift(month,-11))
        validate_period(start_month,month)
    if not month: return {**bundle,'benchmarks':[],'metric_charts':{},'metric_definitions':[{'key':k,'label':l,'tab':t,'unit':u} for k,l,t,u in GRAPH_METRICS]}
    comparisons=analysis.comparison_regions(region['id'],month,question)
    bundle['comparison']=comparisons
    current={r['region_id']:r for r in store.filter_eq('monthly_data','month',month) if r.get('region_id') in master}
    previous={r['region_id']:r for r in store.filter_eq('monthly_data','month',shift(month,-12)) if r.get('region_id') in master}
    start_lookup={r['month']:r for r in target}
    start_row=start_lookup.get(start_month)
    start_prior=start_lookup.get(shift(start_month,-12))
    start_peers=list(current.values()) if start_month==month else [r for r in store.filter_eq('monthly_data','month',start_month) if r.get('region_id') in master]
    benchmarks=[]
    selected_meta=current.get(region['id'],{}).get('index_meta',{})
    for key,label,tab,unit in METRICS:
        vals=[]
        for rid,row in current.items():
            if key.endswith('_index') and row.get('index_meta',{}).get('method_version')!=selected_meta.get('method_version'): continue
            v=value(row,key,previous.get(rid))
            if v is not None: vals.append((rid,v))
        low=min((v for _,v in vals),default=None); high=max((v for _,v in vals),default=None)
        def extreme(v):
            return {'value':v,'regions':[{'id':rid,'name':master[rid].get('full_name') or master[rid]['name'],'basis':metric_basis(current[rid],key),'index_evidence':evidence(current[rid],key,list(current.values()),previous.get(rid))} for rid,x in vals if x==v]} if v is not None else {'value':None,'regions':[]}
        start_value=value(start_row,key,start_prior)
        end_value=value(current.get(region['id']),key,previous.get(region['id']))
        benchmarks.append({'start_value':start_value,'start_basis':metric_basis(start_row,key),
                           'start_evidence':evidence(start_row,key,start_peers,start_prior),
                           'end_evidence':evidence(current.get(region['id']),key,list(current.values()),previous.get(region['id'])),
                           'change':period_change(key,start_value,end_value,start_row,current.get(region['id'])),
                           'key':key,'label':label,'unit':unit,'selected':value(current.get(region['id']),key,previous.get(region['id'])),
                           'selected_basis':metric_basis(current.get(region['id']),key),'minimum':extreme(low),'maximum':extreme(high),'mean':sum(v for _,v in vals)/len(vals) if vals else None,
                           'valid_count':len(vals),'region_count':len(master),'month':month,'mean_method':'unweighted_region_mean'})
        ids=list(dict.fromkeys([region['id']]+[r['id'] for group in ('peers','seeded_random') for r in comparisons.get(group,[]) if r['id'] in master]))
    histories={rid:target if rid==region['id'] else analysis.series(rid,120) for rid in ids}
    labels=[]
    cursor=start_month
    while cursor<=month:
        labels.append(cursor); cursor=shift(cursor,1)
    charts={}
    for key,label,tab,unit in GRAPH_METRICS:
        datasets=[]
        for rid,rows in histories.items():
            lookup={r['month']:r for r in rows}
            datasets.append({'label':master[rid].get('full_name',master[rid]['name']).replace('경상남도 ','').replace('창원시 ',''),'source_dates':[lookup.get(m,{}).get('freshness',{}).get('sources',{}).get('commerce',{}).get('source_as_of') for m in labels] if key=='business_count' else [],'data':[value(lookup.get(m),key,lookup.get(shift(m,-12))) for m in labels]})
        charts[key]={'title':tab+' 비교 추세','unit':unit,'metric':key,'labels':labels,'datasets':datasets}
    last=current.get(region['id'],{}); recent=[r for r in target if start_month<=r['month']<=month]
    bundle['summary']={'region':region,'count':len(recent),'period':f"{start_month} ~ {month}",
                       'metrics':last.get('metrics',{}),'derived':last.get('derived',{}),'indexes':last.get('indexes',{}),
                       'freshness':last.get('freshness',{}),'index_meta':last.get('index_meta',{})}
    from .question_catalog import candidates
    bundle['question_candidates']=candidates(target,start_month,month)
    bundle['charts']=[charts['population_total']]
    return {**bundle,'start_month':start_month,'end_month':month,'available_start':target[0]['month'] if target else None,'available_end':target[-1]['month'] if target else None,'benchmark_month':month,'benchmarks':benchmarks,'metric_charts':charts,
            'metric_definitions':[{'key':k,'label':l,'tab':t,'unit':u} for k,l,t,u in GRAPH_METRICS]}


