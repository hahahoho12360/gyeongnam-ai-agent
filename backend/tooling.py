from __future__ import annotations
from . import analysis

TOOLS=[
 {"type":"function","name":"get_region_summary","description":"특정 경남 법정읍면동의 최근 인구·주거·부동산·상권 요약을 조회합니다. 동명이 중복되면 시군구를 포함한 전체명을 사용하세요.","strict":True,"parameters":{"type":"object","properties":{"region":{"type":"string"},"months":{"type":"integer","minimum":1,"maximum":120}},"required":["region","months"],"additionalProperties":False}},
 {"type":"function","name":"get_population_trend","description":"특정 지역의 월별 인구 추세와 차트 데이터를 조회합니다.","strict":True,"parameters":{"type":"object","properties":{"region":{"type":"string"},"months":{"type":"integer","minimum":3,"maximum":120}},"required":["region","months"],"additionalProperties":False}},
 {"type":"function","name":"get_housing_market","description":"특정 지역의 아파트 매매가격·거래량·거래회전율과 추세를 조회합니다.","strict":True,"parameters":{"type":"object","properties":{"region":{"type":"string"},"months":{"type":"integer","minimum":3,"maximum":120}},"required":["region","months"],"additionalProperties":False}},
 {"type":"function","name":"get_rental_market","description":"특정 지역의 전세가격·전월세 거래량·월세화 비율과 추세를 조회합니다.","strict":True,"parameters":{"type":"object","properties":{"region":{"type":"string"},"months":{"type":"integer","minimum":3,"maximum":120}},"required":["region","months"],"additionalProperties":False}},
 {"type":"function","name":"get_commerce_trend","description":"특정 지역의 상가 수·인구천명당 상가·순증감·업종다양성 추세를 조회합니다.","strict":True,"parameters":{"type":"object","properties":{"region":{"type":"string"},"months":{"type":"integer","minimum":3,"maximum":120}},"required":["region","months"],"additionalProperties":False}},
 {"type":"function","name":"get_auction_market","description":"특정 지역의 온비드 공매물건·낙찰/유찰·낙찰가율 등 저장된 공매 지표를 조회합니다.","strict":True,"parameters":{"type":"object","properties":{"region":{"type":"string"},"months":{"type":"integer","minimum":1,"maximum":120}},"required":["region","months"],"additionalProperties":False}},
 {"type":"function","name":"compare_regions","description":"대상 지역과 실제 인접지역·유사 Peer·재현 가능한 seeded random 비교군을 선정하고 비교합니다.","strict":True,"parameters":{"type":"object","properties":{"region":{"type":"string"},"months":{"type":"integer","minimum":3,"maximum":120}},"required":["region","months"],"additionalProperties":False}},
 {"type":"function","name":"get_region_indexes","description":"지역활력·주거시장압력·생활편의·상권변화 Composite Index를 조회합니다.","strict":True,"parameters":{"type":"object","properties":{"region":{"type":"string"}},"required":["region"],"additionalProperties":False}},
 {"type":"function","name":"get_live_area_snapshot","description":"저장된 최신 스냅샷과 데이터 기준시점/갱신시점을 조회합니다. 허용된 경우 TTL 초과 최신 실거래를 다시 조회합니다.","strict":True,"parameters":{"type":"object","properties":{"region":{"type":"string"}},"required":["region"],"additionalProperties":False}}
]


def _resolve_or_error(name: str):
    r=analysis.resolve_region(name)
    return r, None if r else analysis.region_resolution_error(name)


def _market_bundle(rid: str, months: int, metric: str, title: str) -> dict:
    return {
        'summary': analysis.summary(rid, min(months, 36)),
        'chart': analysis.chart_metric([rid], metric, months, title),
        'rows': analysis.series(rid, months),
    }


def dispatch(name: str, args: dict):
    region=str(args.get('region','')).strip()
    months=int(args.get('months',12))
    reg,error=_resolve_or_error(region)
    if error:
        return error
    rid=reg['id']
    if name=='get_region_summary':
        return analysis.summary(rid,months)
    if name=='get_population_trend':
        return {'summary':analysis.summary(rid,months),'chart':analysis.chart_population([rid],months)}
    if name=='get_housing_market':
        return _market_bundle(rid,months,'sale_price_per_m2',f'최근 {months}개월 ㎡당 매매가격 추세')
    if name=='get_rental_market':
        return _market_bundle(rid,months,'jeonse_price',f'최근 {months}개월 전세가격 추세')
    if name=='get_commerce_trend':
        return _market_bundle(rid,months,'business_count',f'최근 {months}개월 상가 수 추세')
    if name=='get_auction_market':
        from .live import live_auction_snapshot
        return {
            **_market_bundle(rid,months,'auction_listing_count',f'최근 {months}개월 공매물건 추세'),
            'live': live_auction_snapshot(rid),
        }
    if name=='compare_regions':
        bundle=analysis.proactive_bundle(rid,'detail' if months>=36 else 'basic')
        bundle['requested_months']=months
        return bundle
    if name=='get_region_indexes':
        row=analysis.latest(rid)
        return {'region':reg,'indexes':(row or {}).get('indexes',{}),'freshness':(row or {}).get('freshness',{})}
    if name=='get_live_area_snapshot':
        from .live import live_snapshot
        return live_snapshot(rid)
    return {'error':'unknown_tool','name':name}
