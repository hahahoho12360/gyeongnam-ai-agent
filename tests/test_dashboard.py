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
    monkeypatch.setattr(analysis,'proactive_bundle',lambda *args:{'summary':{},'comparison':{'peers':[store.get('regions','4812110200')]}})
    result=dashboard('4812110100','simple')
    pop=result['benchmarks'][0]
    assert pop['valid_count']==pop['region_count']==3
    assert pop['selected']==10 and pop['minimum']['value']==10 and len(pop['maximum']['regions'])==2
    assert math.isclose(pop['mean'],50/3)
    chart=result['metric_charts']['population_total']
    assert chart['labels'][-1]=='2026-09' and len(chart['labels'])==12
    assert chart['datasets'][0]['data'][-2] is None
    assert len(result['metric_charts'])==len(METRICS)==9
