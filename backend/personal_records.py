"""Personal CSV-metric observations; never overwrite official statistics."""
from collections import defaultdict
import math
from fastapi import HTTPException
from . import analysis

METRICS={
 'population_total':('인구','명'),
 'young_population_share':('청년 비율(20~39세)','%'),
 'older_population_share':('고령 인구 비율','%'),
 'single_household_share':('1인세대 비율','%'),
 'sale_price_per_m2':('아파트 매매 전용면적 ㎡당 중앙가격','원/㎡'),
 'sale_price_yoy_pct':('아파트 ㎡당 중앙가격 전년 대비','%'),
 'businesses_per_1000_people':('인구 1,000명당 사업체 수','개'),
 'vitality_index':('지역활력지수','점'),
 'housing_pressure_index':('주거시장압력지수','점'),
 'living_convenience_index':('생활편의지수','점'),
 'commerce_change_index':('상권활력 대리지수','점'),
 'custom':('기존 사용자 기록','사용자 단위'),
}

def validate_record(row):
    metric=row.get('metric_type','custom'); value=row['value']
    if not row.get('date'): raise HTTPException(422,'날짜를 입력해 주세요.')
    if metric not in METRICS or not isinstance(value,(int,float)) or not math.isfinite(value): raise HTTPException(422,'유효한 자료 항목과 숫자를 입력해 주세요.')
    if metric.endswith('_share') and not 0<=value<=100: raise HTTPException(422,'비율은 0~100 사이여야 합니다.')
    if metric.endswith('_index') and not 0<=value<=100: raise HTTPException(422,'지수는 0~100 사이여야 합니다.')
    if metric not in ('custom','sale_price_yoy_pct') and value<0: raise HTTPException(422,'이 항목에는 음수를 입력할 수 없습니다.')
    if metric=='population_total' and not float(value).is_integer(): raise HTTPException(422,'인구는 정수로 입력해 주세요.')
    rid=row.get('region_id')
    if metric!='custom' and not rid: raise HTTPException(422,'지역을 선택해 주세요.')
    if rid:
        region=analysis.resolve_region(rid)
        if not region or not rid.startswith('4812'): raise HTTPException(422,'창원 법정읍·면·동을 선택해 주세요.')
        row['region_name']=region.get('full_name') or region['name']
    row['metric_label'],row['unit']=METRICS[metric]
    row['source_type']='user_record'
    return row

def summarize(rows):
    groups=defaultdict(list)
    for row in rows:groups[(row.get('region_id'),row.get('metric_type','custom'))].append(row)
    summaries=[]
    for (rid,metric),items in groups.items():
        items=sorted(items,key=lambda r:r['date']); vals=[float(r['value']) for r in items]
        label,unit=METRICS.get(metric,METRICS['custom'])
        trend='자료 부족' if len(items)<2 else '상승' if vals[-1]>vals[0] else '감소' if vals[-1]<vals[0] else '유지'
        summaries.append({'region_id':rid,'region_name':items[0].get('region_name'),'metric_type':metric,'label':label,'unit':unit,
                          'period':items[0]['date']+' ~ '+items[-1]['date'],'count':len(items),
                          'metrics':{'average':sum(vals)/len(vals),'max':max(vals),'min':min(vals)},'trend':trend,
                          'latest_memo':items[-1].get('memo','')})
    dates=sorted(r['date'] for r in rows)
    return {'period':dates[0]+' ~ '+dates[-1] if dates else None,'count':len(rows),'groups':summaries,
            'metrics':summaries[0]['metrics'] if len(summaries)==1 else {},
            'trend':summaries[0]['trend'] if len(summaries)==1 else '항목·지역별로 분석합니다.',
            'source':'사용자가 직접 입력한 기록; 공식 통계가 아닙니다. 기록 조건이 다르면 비교에 주의하세요.'}
