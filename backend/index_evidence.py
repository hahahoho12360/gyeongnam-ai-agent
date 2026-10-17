"""Read-only explanations of stored scores; never repairs or overwrites data."""
import math
from .indexes import INDEX_DEFINITIONS, INDEX_METHODS
from .metrics import percentile_score, weighted_index

# label, unit, numerator, denominator, multiplier, source
COMPONENTS = {
    'population_yoy_pct': ('인구 전년 대비', '%', 'population_total', None, 100, 'population'),
    'young_population_share': ('청년 비율(20~39세)', '%', 'age_20_39', 'population_total', 100, 'age_population'),
    'housing_turnover_pct': ('아파트 매매 거래회전율', '%', 'sale_count', 'apartment_units', 100, 'apt_sale'),
    'businesses_per_1000_people': ('인구 1천 명당 업소 수', '개', 'business_count', 'population_total', 1000, 'commerce'),
    'sale_price_yoy_pct': ('아파트 ㎡당 중앙가격 전년 대비', '%', 'sale_price_per_m2', None, 100, 'apt_sale'),
    'rent_count_yoy_pct': ('전월세 거래량 전년 대비', '%', 'rent_count', None, 100, 'apt_rent'),
    'monthly_rent_share': ('월세 거래 비율', '%', 'monthly_rent_count', 'rent_count', 100, 'apt_rent'),
    'old_building_share': ('30년 이상 건축물 비율', '%', 'old_buildings_30y', 'building_count', 100, 'building_register'),
    'business_diversity_index': ('업종 다양성', '점', None, None, None, 'commerce'),
    'health_businesses_per_1000_people': ('인구 1천 명당 의료 업소', '개', 'health_business_count', 'population_total', 1000, 'commerce'),
    'education_businesses_per_1000_people': ('인구 1천 명당 교육 업소', '개', 'education_business_count', 'population_total', 1000, 'commerce'),
    'apartment_supply_proxy': ('공동주택 세대수 / 주민등록 세대수', '%', 'apartment_units', 'households', 100, 'apartment_basic'),
    'restaurant_businesses_per_1000_people': ('인구 1천 명당 음식점', '개', 'restaurant_count', 'population_total', 1000, 'commerce'),
    'cafe_businesses_per_1000_people': ('인구 1천 명당 카페', '개', 'cafe_count', 'population_total', 1000, 'commerce'),
    'convenience_businesses_per_1000_people': ('인구 1천 명당 편의점', '개', 'convenience_store_count', 'population_total', 1000, 'commerce'),
}
RAW_LABELS = {
    'population_total':'주민등록 인구(명)', 'age_20_39':'청년 인구(명)',
    'households':'주민등록 세대수', 'business_count':'업소 수(개)',
    'sale_count':'아파트 매매 거래(건)', 'apartment_units':'공동주택 세대수',
    'sale_price_per_m2':'아파트 ㎡당 중앙가격(원)', 'rent_count':'전월세 거래(건)',
    'monthly_rent_count':'월세 거래(건)', 'old_buildings_30y':'30년 이상 건축물(동)',
    'building_count':'전체 건축물(동)', 'health_business_count':'의료 업소(개)',
    'education_business_count':'교육 업소(개)', 'restaurant_count':'음식점(개)',
    'cafe_count':'카페(개)', 'convenience_store_count':'편의점(개)',
}

def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

def component_value(row, key):
    v=row.get('derived', {}).get(key) if key in row.get('derived', {}) else row.get('metrics', {}).get(key)
    return v if finite(v) else None

def evidence(row, key, month_rows, year_ago=None):
    if not row or key not in INDEX_DEFINITIONS: return None
    weights=INDEX_DEFINITIONS[key]
    metrics=row.get('metrics', {}); meta=row.get('index_meta', {})
    peers=[r for r in month_rows if r.get('month')==row.get('month') and not r.get('freshness', {}).get('is_demo')]
    scores={k:percentile_score(component_value(row,k), [component_value(r,k) for r in peers]) for k in weights}
    active=[k for k in weights if scores[k] is not None]
    total=sum(weights[k] for k in active)
    rebuilt=weighted_index(scores, weights, minimum_components=INDEX_METHODS[key]['minimum_components'])
    stored=row.get('indexes', {}).get(key)
    # Exact inputs at collection time are not stored. Only describe contributions
    # when a same-month reconstruction reproduces the displayed stored score.
    verified=(meta.get('method_version')=='3.2' and meta.get('comparison_scope') in ('changwon','4812')
              and meta.get('comparison_month')==row.get('month') and not row.get('indexes_need_recompute')
              and finite(stored) and rebuilt is not None and abs(stored-rebuilt)<0.011)
    components=[]; raw_keys={'population_total','age_20_39'}
    for k,w in weights.items():
        label,unit,num,den,mult,source=COMPONENTS[k]
        raw_keys.update(x for x in (num,den) if x)
        prior=(year_ago or {}).get('metrics', {}).get(num) if k.endswith('_yoy_pct') else None
        source_meta=row.get('freshness',{}).get('sources',{}).get(source,{})
        components.append({'key':k,'label':label,'unit':unit,'value':component_value(row,k),
            'numerator':metrics.get(num), 'denominator':metrics.get(den) if den else prior,
            'numerator_label':RAW_LABELS.get(num), 'denominator_label':RAW_LABELS.get(den) if den else ('전년 동월 '+RAW_LABELS.get(num,'')) if k.endswith('_yoy_pct') else None,
            'base_weight':w, 'effective_weight':w/total if k in active and total else None,
            'percentile':scores[k] if verified else None, 'contribution':scores[k]*w/total if verified and k in active else None,
            'valid_regions':sum(component_value(r,k) is not None for r in peers),
            'source_as_of':source_meta.get('source_as_of'), 'fetched_at':source_meta.get('fetched_at'),
            'source_status':source_meta.get('status')})
    return {'month':row.get('month'),'region_id':row.get('region_id'),'key':key,'stored_score':stored,
        'method_version':meta.get('method_version'),'verified':verified,'active_components':active,
        'available_count':len(active),'total_count':len(weights),'comparison_region_count':len(peers),
        'components':components,'raw':[{'key':k,'label':RAW_LABELS[k],'value':metrics.get(k)} for k in RAW_LABELS if k in raw_keys],
        'source_as_of':row.get('freshness',{}).get('source_as_of'),
        'notice':'현재 저장 구성자료로 점수 재현 확인' if verified else '저장 점수의 산출 시점 입력값을 재현하지 못해 백분위·기여점수는 표시하지 않습니다.'}

def period_change(key, start, end, start_row=None, end_row=None):
    unit='점' if key in INDEX_DEFINITIONS else '%p' if key.endswith(('_share','_pct')) else '명' if key=='population_total' else '원/㎡'
    result={'delta':None,'percent':None,'unit':unit,'status':'missing','note':'시작월 또는 종료월 자료 없음'}
    if start is None or end is None:
        if key in INDEX_DEFINITIONS:
            reasons=[]
            for label,score,row in [('시작월',start,start_row),('종료월',end,end_row)]:
                if score is not None:continue
                if not row:reason='월별 자료 없음'
                elif row.get('indexes_need_recompute'):reason='지수 재계산 대기'
                elif not row.get('index_meta'):reason='지수 계산정보 누락'
                else:
                    count=sum(component_value(row,k) is not None for k in INDEX_DEFINITIONS[key])
                    minimum=INDEX_METHODS[key]['minimum_components']
                    reason=f'지수 구성자료 부족({count}개 / 최소 {minimum}개 필요)'
                reasons.append(label+' '+reason)
            result['note']=' · '.join(reasons)
        return result
    if key in INDEX_DEFINITIONS:
        a=(start_row or {}).get('index_meta',{}); b=(end_row or {}).get('index_meta',{})
        if not a.get('method_version') or a.get('method_version')!=b.get('method_version') or a.get('comparison_scope')!=b.get('comparison_scope'):
            return {**result,'status':'incompatible','note':'지수 방법 버전 또는 비교범위가 달라 증감 미산출'}
        same=all((component_value(start_row,k) is None)==(component_value(end_row,k) is None) for k in INDEX_DEFINITIONS[key])
        note='월별 상대점수 변화이며 절대적인 개선 정도가 아닙니다.'
        if not same: note='구성항목·적용 가중치가 다릅니다. '+note
        result.update(status='relative' if same else 'components_changed',note=note)
    else: result.update(status='ok',note='')
    result['delta']=end-start
    if unit not in ('점','%p'):
        result['percent']=(end/start-1)*100 if start>0 else None
        if start==0: result['note']='시작값이 0이므로 증감률 미산출'
    return result

