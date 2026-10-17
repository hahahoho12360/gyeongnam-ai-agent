import math
from backend import db, analysis
from backend.dashboard import value, dashboard, METRICS

def test_ratios_do_not_turn_missing_numerators_into_zero():
    row={'metrics':{'population_total':100,'households':50},'derived':{'young_population_share':0,'single_household_share':0}}
    assert value(row,'young_population_share') is None
    assert value(row,'single_household_share') is None
    row['metrics'].update(age_20_39=0,single_households=10)
    assert value(row,'young_population_share')==0
    assert value(row,'single_household_share')==20
    row['freshness']={'sources':{'age_population':{'status':'no_data'}}}
    assert value(row,'young_population_share') is None

def test_price_yoy_and_index_validity():
    row={'month':'2026-09','metrics':{'sale_price_per_m2':110.9},'indexes':{'vitality_index':50},'index_meta':{'comparison_scope':'changwon','comparison_month':'2026-09'}}
    assert math.isclose(value(row,'sale_price_yoy_pct',{'metrics':{'sale_price_per_m2':100}}),10.9)
    assert value(row,'sale_price_yoy_pct') is None
    assert value(row,'vitality_index')==50
    row['indexes_need_recompute']=True
    assert value(row,'vitality_index') is None
    assert value({'metrics':{'population_total':float('nan')}},'population_total') is None

def test_same_month_extremes_ties_scope_and_trend_gaps(monkeypatch):
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    for rid,name in [('4812110100','A'),('4812110200','B'),('4812110300','C'),('4825010100','외부')]:
        store.set('regions',rid,{'id':rid,'bjd_code':rid,'name':name})
    for rid,month,pop in [('4812110100','2026-09',10),('4812110200','2026-09',20),('4812110300','2026-09',20),('4825010100','2026-09',999),('4812110100','2026-07',99)]:
        store.set('monthly_data',rid+'_'+month,{'region_id':rid,'month':month,'metrics':{'population_total':pop}})
    monkeypatch.setattr(analysis,'comparison_regions',lambda *args:{'peers':[store.get('regions','4812110200')]})
    result=dashboard('4812110100','simple')
    pop=result['benchmarks'][0]
    assert pop['valid_count']==pop['region_count']==3
    assert pop['selected']==10 and pop['minimum']['value']==10 and len(pop['maximum']['regions'])==2
    assert math.isclose(pop['mean'],50/3)
    chart=result['metric_charts']['population_total']
    assert chart['labels'][-1]=='2026-09' and len(chart['labels'])==12
    assert chart['datasets'][0]['data'][-2] is None
    assert len(result['metric_charts'])==8
    assert 'business_count' not in result['metric_charts']
    assert len(METRICS)==9

def test_selected_period_uses_end_month_without_silent_fallback(monkeypatch):
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    rid='4812110100';store.set('regions',rid,{'id':rid,'bjd_code':rid,'name':'명서동'})
    for month,pop in [('2025-10',10),('2026-01',20),('2026-09',90)]:
        store.set('monthly_data',rid+'_'+month,{'region_id':rid,'month':month,'metrics':{'population_total':pop}})
    monkeypatch.setattr(analysis,'comparison_regions',lambda *args:{})
    x=dashboard(rid,'detail','2025-10','2026-01')
    assert x['benchmarks'][0]['selected']==20
    assert x['metric_charts']['population_total']['labels']==['2025-10','2025-11','2025-12','2026-01']
    assert x['summary']['count']==2
    x=dashboard(rid,'basic','2026-01','2026-02')
    assert x['benchmarks'][0]['selected'] is None
    assert x['summary']['metrics']=={}
    assert len(dashboard(rid,'detail')['metric_charts']['population_total']['labels'])==12

def test_period_validation():
    import pytest
    from backend.dashboard import validate_period
    for start,end in [('2026-13','2026-14'),('2026-09','2026-01'),('2000-01','2026-01')]:
        with pytest.raises(ValueError): validate_period(start,end)

def test_export_uses_exact_applied_period(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    rid='4812110100';store.set('regions',rid,{'id':rid,'bjd_code':rid,'name':'명서동'})
    for month in ('2026-01','2026-02','2026-03'):
        store.set('monthly_data',rid+'_'+month,{'region_id':rid,'month':month,'metrics':{'population_total':10}})
    with TestClient(app) as client:
        res=client.get(f'/api/analytics/export/{rid}?format=json&start_month=2026-02&end_month=2026-02')
        assert res.status_code==200 and [r['month'] for r in res.json()]==['2026-02']
        assert client.get(f'/api/analytics/regions/{rid}/dashboard?start_month=2026-03&end_month=2026-01').status_code==400

def test_month_bounds_use_korean_calendar_and_january_rollover():
    from datetime import datetime,timezone
    from backend.dashboard import period_bounds
    assert period_bounds(datetime(2026,10,11,tzinfo=timezone.utc))==('2022-10','2026-09')
    assert period_bounds(datetime(2027,1,1,tzinfo=timezone.utc))==('2022-10','2026-12')
    # UTC is still September, but Korea is already October.
    assert period_bounds(datetime(2026,9,30,15,0,tzinfo=timezone.utc))[1]=='2026-09'

def test_bounds_reject_older_current_and_future_months(monkeypatch):
    import pytest
    import backend.dashboard as module
    monkeypatch.setattr(module,'period_bounds',lambda:('2022-10','2026-09'))
    for start,end in [('2022-09','2026-09'),('2022-10','2026-10'),('2026-10','2026-11')]:
        with pytest.raises(ValueError): module.validate_period(start,end)
    module.validate_period('2022-10','2026-09')
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as client:
        for path in ('/api/analytics/regions/4812112400/dashboard','/api/analytics/export/4812112400'):
            assert client.get(path+'?start_month=2022-09&end_month=2026-09').status_code==400
            assert client.get(path+'?start_month=2022-10&end_month=2026-10').status_code==400

def test_default_period_stops_at_last_closed_month_and_collection_start(monkeypatch):
    import backend.dashboard as module
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    monkeypatch.setattr(module,'period_bounds',lambda:('2022-10','2026-09'))
    rid='4812110100';store.set('regions',rid,{'id':rid,'bjd_code':rid,'name':'A'})
    for month in ('2022-10','2026-09','2026-10'):
        store.set('monthly_data',rid+'_'+month,{'region_id':rid,'month':month,'metrics':{'population_total':10}})
    monkeypatch.setattr(analysis,'comparison_regions',lambda *args:{})
    result=module.dashboard(rid)
    assert result['end_month']=='2026-09' and result['period_max']=='2026-09'
    assert module.dashboard(rid,end_month='2022-10')['start_month']=='2022-10'


def test_comparison_uses_dashboard_end_month_even_when_snapshot_is_stale(monkeypatch):
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    rid='4812110100';store.set('regions',rid,{'bjd_code':rid,'name':'시험동'})
    store.set('monthly_data',rid+'_2026-08',{'region_id':rid,'month':'2026-08','metrics':{'population_total':10}})
    store.set('region_latest',rid,{'region_id':rid,'month':'2026-07','metrics':{'population_total':9}})
    calls=[]
    monkeypatch.setattr(analysis,'comparison_regions',lambda *args:(calls.append(args) or {}))
    result=dashboard(rid,question='인구 비교')
    assert result['end_month']=='2026-08'
    assert calls==[(rid,'2026-08','인구 비교')]


def test_small_population_basis_preserves_real_zero_and_missing():
    from backend.dashboard import metric_basis
    row={'metrics':{'population_total':12,'age_20_39':0,'households':10,'single_households':10}}
    assert value(row,'young_population_share')==0
    assert metric_basis(row,'young_population_share')['denominator']==12
    assert metric_basis(row,'young_population_share')['numerator']==0
    assert value(row,'single_household_share')==100
    assert metric_basis(row,'single_household_share')['denominator']==10
    assert metric_basis({'metrics':{'population_total':0}},'population_total')['count']==0
    assert metric_basis({'metrics':{'population_total':0,'age_20_39':0}},'young_population_share') is None
    row['freshness']={'sources':{'age_population':{'status':'no_data'}}}
    assert metric_basis(row,'young_population_share') is None

