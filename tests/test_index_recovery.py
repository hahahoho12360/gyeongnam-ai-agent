from copy import deepcopy
from backend import db,analysis
from backend.dashboard import dashboard
from backend.indexes import rebuild_index_rows
from backend.index_evidence import period_change

def test_dashboard_recovers_missing_metadata_and_entire_cohort(monkeypatch):
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    monkeypatch.setattr(analysis,'comparison_regions',lambda *args:{})
    for rid,pop,young in [('4812110100',100,30),('4812110200',200,60)]:
        store.set('regions',rid,{'name':rid,'bjd_code':rid})
        store.set('monthly_data',rid+'_2025-09',{'region_id':rid,'month':'2025-09','metrics':{'population_total':pop-10}})
        store.set('monthly_data',rid+'_2026-09',{'region_id':rid,'month':'2026-09','metrics':{'population_total':pop,'age_20_39':young,'business_count':10,'health_business_count':2,'cafe_count':1},'indexes':{'vitality_index':999},'indexes_need_recompute':True})
    original=deepcopy(store.get('monthly_data','4812110100_2026-09'))
    result=dashboard('4812110100',start_month='2026-09',end_month='2026-09')
    vitality=next(r for r in result['benchmarks'] if r['key']=='vitality_index')
    assert vitality['valid_count']==2 and 0<=vitality['selected']<=100
    assert vitality['maximum']['value'] is not None and vitality['minimum']['value'] is not None
    assert vitality['end_evidence']['verified'] is True
    assert result['summary']['index_meta']['comparison_scope']=='changwon'
    assert store.get('monthly_data','4812110100_2026-09')==original

def test_missing_selected_region_does_not_hide_other_regions(monkeypatch):
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    monkeypatch.setattr(analysis,'comparison_regions',lambda *args:{})
    for rid in ['4812110100','4812110200']:store.set('regions',rid,{'name':rid})
    store.set('monthly_data','peer',{'region_id':'4812110200','month':'2026-09','metrics':{'population_total':100,'age_20_39':20,'business_count':10}})
    result=dashboard('4812110100',start_month='2026-09',end_month='2026-09')
    score=next(r for r in result['benchmarks'] if r['key']=='vitality_index')
    assert score['selected'] is None and score['valid_count']==1

def test_no_data_and_missing_age_are_not_zero_components():
    rows=[{'region_id':'a','month':'2026-09','metrics':{'population_total':100,'business_count':10,'cafe_count':1},'freshness':{'sources':{'commerce':{'status':'no_data'}}}}]
    result=rebuild_index_rows(rows,month='2026-09')[0]
    assert result['derived']['young_population_share'] is None
    assert result['derived']['businesses_per_1000_people'] is None
    assert all(v is None for v in result['indexes'].values())
    note=period_change('vitality_index',None,None,result,result)['note']
    assert '구성자료 부족' in note and '최소 2개' in note

def test_pipeline_preserves_metadata_then_recomputes_scope(monkeypatch):
    from scripts import pipeline
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    rid='4812110100'
    store.set('monthly_data',rid+'_2026-09',{'region_id':rid,'month':'2026-09','metrics':{'population_total':100,'age_20_39':20,'business_count':10},'index_meta':{'comparison_scope':'changwon'},'custom_provenance':'keep'})
    pipeline.upsert_metric_patch(rid,'2026-09',{'sale_count':1},source='apt_sale')
    saved=store.get('monthly_data',rid+'_2026-09')
    assert saved['index_meta']['comparison_scope']=='changwon' and saved['custom_provenance']=='keep'
    assert saved['indexes_need_recompute'] is True
    pipeline.recompute_indexes('2026-09')
    saved=store.get('monthly_data',rid+'_2026-09')
    assert saved['indexes_need_recompute'] is False
    assert saved['index_meta']['comparison_month']=='2026-09'
    assert saved['index_meta']['comparison_region_count']==1
    assert saved['indexes']['vitality_index']==50
    assert store.get('region_latest',rid)['index_meta']==saved['index_meta']
    pipeline.mark_source_no_data(rid,'2026-09',source='apt_sale',reason='no rows',source_as_of='2026-09-30')
    assert store.get('monthly_data',rid+'_2026-09')['index_meta']==saved['index_meta']
