from backend.question_catalog import candidates,read,metric_analysis
from backend.dashboard import GRAPH_METRICS,value

def row(month,**metrics):return {'month':month,'metrics':metrics,'freshness':{'sources':{}}}

def test_requested_graphs_and_strict_under20():
    keys={m[0] for m in GRAPH_METRICS}
    assert len(keys)==9 and {'business_count','under_20','households','age_20_39','age_60_plus','single_households'}<=keys
    assert not {'sale_price_per_m2','sale_price_yoy_pct'}&keys
    assert value(row('2026-09',age_0_9=4,age_10_19=5),'under_20')==9
    assert value(row('2026-09',age_0_9=4),'under_20') is None
    assert value(row('2026-09',business_count=0),'business_count')==0

def test_candidates_use_available_fields_and_actual_categories():
    rows=[row('2026-08',population_total=10),row('2026-09',population_total=11,business_count=0,health_business_count=0,business_category_counts={'교육':2})]
    qs=candidates(rows,'2026-08','2026-09');ids={q['id'] for q in qs}
    assert 'population_total:증감' in ids and 'business_count:현황' in ids
    assert 'business_count:추세' not in ids and 'business_count:증감' not in ids
    assert 'category:교육:현황' in ids and not any('sale_count' in i for i in ids)
    assert any('병원 수로 단정하지 마' in q['prompt'] for q in qs)
    assert len(ids)==len(qs)

def test_missing_source_is_not_zero():
    r=row('2026-09',business_count=0);r['freshness']['sources']['commerce']={'status':'no_data'}
    assert read(r,'business_count') is None and not candidates([r],'2026-09','2026-09')

def test_metric_tool_exact_endpoints_and_gaps(monkeypatch):
    from backend import analysis
    monkeypatch.setattr(analysis,'series',lambda *a:[row('2026-07',age_20_39=4),row('2026-09',age_20_39=6)])
    monkeypatch.setattr(analysis,'resolve_region',lambda rid:{'id':rid})
    x=metric_analysis('r','age_20_39','2026-08','2026-09')
    assert [p['value'] for p in x['points']]==[None,6] and x['delta'] is None
    x=metric_analysis('r','age_20_39','2026-07','2026-09')
    assert x['delta']==2 and x['percent']==50
