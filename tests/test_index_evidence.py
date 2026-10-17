import pytest
from backend import db, analysis
from backend.indexes import compute_index_rows, methodology_payload
from backend.index_evidence import evidence, period_change
from backend.dashboard import dashboard


def rows_for(month):
    rows=[{'region_id':rid,'month':month,'metrics':{'population_total':pop,'age_20_39':young,'business_count':business},
           'derived':{'population_yoy_pct':growth,'young_population_share':young/pop*100,'businesses_per_1000_people':business/pop*1000}}
          for rid,pop,young,business,growth in [('4812110100',154,75,12,2.67),('4812110200',1000,200,30,-1)]]
    scores=compute_index_rows(rows)
    for row in rows:
        row['indexes']=scores[row['region_id']]
        row['index_meta']=methodology_payload(comparison_scope='changwon',month=month,region_count=2)
    return rows


def test_evidence_reproduces_score_and_renormalized_weights():
    rows=rows_for('2026-09');e=evidence(rows[0],'vitality_index',rows)
    assert e['verified'] and e['available_count']==3
    c={x['key']:x for x in e['components']}
    assert c['housing_turnover_pct']['effective_weight'] is None
    assert c['population_yoy_pct']['effective_weight']==pytest.approx(.35/.8)
    assert sum(x['contribution'] or 0 for x in c.values())==pytest.approx(e['stored_score'],abs=.01)
    assert c['young_population_share']['numerator']==75
    assert c['young_population_share']['denominator']==154


def test_stale_score_does_not_invent_contributions():
    rows=rows_for('2026-09');rows[0]['indexes']['vitality_index']+=1
    e=evidence(rows[0],'vitality_index',rows)
    assert not e['verified']
    assert all(c['contribution'] is None and c['percentile'] is None for c in e['components'])


def test_version_and_partial_collection_guard():
    rows=rows_for('2026-09');rows[0]['index_meta']['method_version']='other'
    assert not evidence(rows[0],'vitality_index',rows)['verified']
    rows=rows_for('2026-09');rows[0]['indexes_need_recompute']=True
    assert not evidence(rows[0],'vitality_index',rows)['verified']


def test_delta_units_zero_missing_and_methods():
    assert period_change('population_total',0,4)['delta']==4
    assert period_change('population_total',0,4)['percent'] is None
    assert period_change('young_population_share',40,45)['unit']=='%p'
    assert period_change('population_total',None,4)['delta'] is None
    a=rows_for('2025-09')[0];b=rows_for('2026-09')[0]
    assert period_change('vitality_index',50,60,a,b)['delta']==10
    b['derived']['housing_turnover_pct']=1
    assert period_change('vitality_index',50,60,a,b)['status']=='components_changed'
    b['index_meta']['method_version']='4'
    assert period_change('vitality_index',50,60,a,b)['delta'] is None


def test_dashboard_exact_endpoints_extreme_evidence_and_no_writes(monkeypatch):
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    monkeypatch.setattr(analysis,'comparison_regions',lambda *args:{})
    for month in ['2025-09','2026-09']:
        for row in rows_for(month):
            rid=row['region_id'];store.set('regions',rid,{'name':rid,'bjd_code':rid})
            store.set('monthly_data',rid+'_'+month,row)
    before=repr(store._data)
    x=dashboard('4812110100',start_month='2025-09',end_month='2026-09')
    pop=x['benchmarks'][0];idx=x['benchmarks'][5]
    assert pop['start_value']==pop['selected']==154 and pop['change']['delta']==0
    assert idx['start_evidence']['month']=='2025-09' and idx['end_evidence']['verified']
    assert idx['maximum']['regions'][0]['index_evidence']['verified']
    assert repr(store._data)==before
    x=dashboard('4812110100',start_month='2025-10',end_month='2026-09')
    assert x['benchmarks'][0]['start_value'] is None
    assert x['benchmarks'][0]['change']['status']=='missing'
    x=dashboard('4812110100',start_month='2026-09',end_month='2026-09')
    assert x['benchmarks'][5]['change']['delta']==0
