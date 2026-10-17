"""Data-backed question candidates and deterministic metric retrieval."""
import math
CATALOG={}
def add(source,domain,unit,pairs,snapshot=False):
    for key,label in pairs:
        CATALOG[key]={'key':key,'label':label,'source':source,'domain':domain,'unit':unit,'snapshot':snapshot}
add('population','인구·세대','명',[('population_total','주민등록 인구'),('population_male','남성 인구'),('population_female','여성 인구')])
add('population','인구·세대','세대',[('households','주민등록 세대 수')])
add('population','인구·세대','명/세대',[('persons_per_household','세대당 인구')])
add('age_population','연령','명',[(f'age_{a}_{a+9}',f'{a}~{a+9}세 인구') for a in range(0,100,10)]+[('age_100_plus','100세 이상 인구'),('age_20_39','청년 인구(20~39세)'),('age_60_plus','60세 이상 인구'),('under_20','20세 미만 인구')])
add('single_household','1인세대','세대',[(f'single_age_{a}_{a+9}',f'{a}~{a+9}세 1인세대') for a in range(0,100,10)]+[('single_age_100_plus','100세 이상 1인세대'),('single_age_20_39','청년 1인세대(20~39세)'),('single_age_60_plus','60세 이상 1인세대'),('single_households','1인세대 수'),('single_male_households','남성 1인세대'),('single_female_households','여성 1인세대')])
add('apt_sale','매매','건',[('sale_count','아파트 매매 거래량')])
add('apt_sale','매매','원',[('sale_median_price','매매 중앙가격'),('sale_total_amount','매매 거래금액 합계')])
add('apt_sale','매매','원/㎡',[('sale_price_per_m2','아파트 ㎡당 가격')])
add('apt_sale','매매','㎡',[('sale_mean_area_m2','매매 평균 거래면적')])
add('apt_rent','임대','건',[('rent_count','전월세 거래량'),('jeonse_count','전세 거래량'),('monthly_rent_count','월세 거래량')])
add('apt_rent','임대','원',[('jeonse_price','전세 보증금'),('monthly_rent_median','월세 중앙값'),('monthly_deposit_median','월세 보증금 중앙값')])
add('apt_rent','임대','원/㎡',[('jeonse_price_per_m2','전세 ㎡당 보증금')])
add('apartment_basic','주거 재고','개',[('apartment_complex_count','공동주택 단지 수'),('apartment_building_count','공동주택 동 수')],True)
add('apartment_basic','주거 재고','세대',[('apartment_units','공동주택 세대 수')],True)
add('apartment_basic','주거 재고','㎡',[('apartment_total_area_m2','공동주택 연면적')],True)
add('building_register','건축물','개',[('building_count','건축물 수'),('old_buildings_30y','30년 이상 건축물 수'),('apartment_like_building_count','아파트 용도 건축물 수')],True)
add('building_register','건축물','㎡',[('building_total_area_m2','건축물 연면적'),('residential_building_area_m2','주거용 건축물 연면적')],True)
add('building_register','건축물','세대',[('building_register_household_units','건축물대장 세대 수')],True)
add('commerce','상권','개',[(k,l) for k,l in [('business_count','업소 수'),('cafe_count','카페·커피 업소 수'),('restaurant_count','음식점 업소 수'),('convenience_store_count','편의점 업소 수'),('health_business_count','의료·건강 관련 업소 수'),('education_business_count','교육 관련 업소 수')]],True)

def number(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def definition(key):
    if key.startswith('category:'):
        return {'key':key,'label':key[9:]+' 업종 업소 수','source':'commerce','domain':'상권','unit':'개','snapshot':True}
    return CATALOG.get(key)
def read(row,key):
    d=definition(key)
    if not d or not row or row.get('freshness',{}).get('is_demo'): return None
    if row.get('freshness',{}).get('sources',{}).get(d['source'],{}).get('status')=='no_data': return None
    m=row.get('metrics',{})
    if key=='under_20':
        a,b=m.get('age_0_9'),m.get('age_10_19')
        return a+b if number(a) and number(b) else None
    v=(m.get('business_category_counts') or {}).get(key[9:]) if key.startswith('category:') else m.get(key)
    return v if number(v) else None

def candidates(rows,start,end):
    lookup={r['month']:r for r in rows}; last=lookup.get(end,{})
    keys=list(CATALOG)+['category:'+k for k in (last.get('metrics',{}).get('business_category_counts') or {})]
    out=[]
    for key in keys:
        d=definition(key); end_value=read(last,key)
        valid=[r for r in rows if start<=r['month']<=end and read(r,key) is not None]
        intents=[]
        if end_value is not None: intents += [('현황','규모와 단위, 자료 기준일을 설명해줘.'),('비교','같은 자료 기준의 유사 지역과 비교하고 기준일이 다르면 밝혀줘.'),('해석','수치의 의미와 활용 방법, 집계 범위의 한계를 설명해줘.')]
        if not d['snapshot']:
            if len(valid)>=2: intents += [('추세','월별 관측값의 추세를 분석하고 빈 달은 추정하지 마.')]
            if start!=end and end_value is not None and read(lookup.get(start),key) is not None: intents += [('증감','정확한 시작월과 종료월 값, 증감 수와 증감률을 비교해줘. 시작값이 0이면 증감률은 계산하지 마.')]
        for intent,request in intents:
            period=f'{end} 저장 구간의 현황' if d['snapshot'] or intent in ('현황','비교','해석') else f'{start}부터 {end}까지'
            note=' 현황 자료의 실제 source_as_of를 표시하고 저장 구간을 실제 관측일로 해석하지 마. 과거 추세나 개업·폐업 수를 추정하지 마.' if d['snapshot'] else ''
            if key=='health_business_count': note+=' 병원·의원·약국·건강 관련 업소를 포괄할 수 있으므로 병원 수로 단정하지 마.'
            out.append({'id':key+':'+intent,'domain':d['domain'],'label':d['label']+' '+intent,'prompt':f'{period} {d["label"]}에 대해 {request}'+note,'metric':key})
    return out

def metric_analysis(rid,key,start,end):
    from . import analysis
    from .dashboard import validate_period,shift
    d=definition(key)
    if not d: return {'error':'unknown_metric'}
    rows=analysis.series(rid,120)
    end=end or (rows[-1]['month'] if rows else None)
    if not end:return {'error':'no_data'}
    start=start or shift(end,-11)
    validate_period(start,end)
    lookup={r['month']:r for r in rows}; points=[]; month=start
    while month<=end:
        row=lookup.get(month,{})
        points.append({'month':month,'value':read(row,key),'source':row.get('freshness',{}).get('sources',{}).get(d['source'],{})})
        month=shift(month,1)
    a,b=points[0]['value'],points[-1]['value']
    delta=b-a if not d['snapshot'] and a is not None and b is not None else None
    return {'region':analysis.resolve_region(rid),'metric':d,'points':points,'delta':delta,'percent':delta/a*100 if delta is not None and a else None,'note':'현황 자료는 실제 source_as_of를 확인하세요. 저장 월간 값의 차이는 개업·폐업 수가 아닙니다.' if d['snapshot'] else '결측은 0이 아닙니다. 증감은 요청 시작월과 종료월 기준입니다.'}
