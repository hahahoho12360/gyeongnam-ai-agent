from types import SimpleNamespace
from fastapi.testclient import TestClient
from backend import analysis, db
from backend.main import app
from backend.openai_agent import _compact_context
from backend.tooling import dispatch


def test_scope_excludes_other_cities_from_resolution_and_comparison(monkeypatch):
    store=db.MemoryStore()
    monkeypatch.setattr(db,'_store',store)
    monkeypatch.setattr(analysis,'settings',SimpleNamespace(analysis_scope_prefix='4812'))
    for rid in ('4812313300','4812313400','4825010100'):
        store.set('regions',rid,{'name':rid,'bjd_code':rid,'neighbors':['4825010100']})
    assert len(analysis.list_regions())==2
    assert analysis.resolve_region('4825010100') is None
    comparison=analysis.comparison_regions('4812313300')
    assert comparison['neighbors']==[]
    assert all(r['id'].startswith('4812') for r in comparison['seeded_random'])


def test_metadata_survives_summary_tools_and_ai_context(monkeypatch):
    store=db.MemoryStore()
    monkeypatch.setattr(db,'_store',store)
    rid='4812313300'
    store.set('regions',rid,{'name':'남양동','bjd_code':rid})
    meta={'comparison_scope':'changwon','comparison_month':'2026-09','official_statistic':False}
    store.set('monthly_data',rid+'_2026-09',{'region_id':rid,'month':'2026-09','metrics':{'population_total':100},'index_meta':meta})
    bundle=analysis.proactive_bundle(rid,'simple')
    assert bundle['charts'] and bundle['charts'][0]['labels']==['2026-09']
    assert bundle['summary']['index_meta']==meta
    assert dispatch('get_region_indexes',{'region':rid})['index_meta']==meta
    assert _compact_context(bundle)['summary']['index_meta']==meta


def test_saved_report_endpoint_never_scans_monthly_data(monkeypatch):
    store=db.MemoryStore()
    monkeypatch.setattr(db,'_store',store)
    store.set('rollout_reports','changwon_v32_final',{'scope':'changwon'})
    def forbidden(*args):
        raise AssertionError('saved report must use one document read')
    monkeypatch.setattr(store,'list',forbidden)
    client=TestClient(app)
    assert client.get('/api/meta/changwon-mvp').json()['scope']=='changwon'
    store.delete('rollout_reports','changwon_v32_final')
    assert client.get('/api/meta/changwon-mvp').status_code==404


def test_comparison_summaries_include_seeded_random(monkeypatch):
    store=db.MemoryStore()
    monkeypatch.setattr(db,'_store',store)
    regs=[{'id':str(i),'name':str(i)} for i in range(7)]
    for r in regs:
        store.set('regions',r['id'],r)
    monkeypatch.setattr(analysis,'comparison_regions',lambda rid: {
        'neighbors':regs[1:3], 'peers':regs[3:5], 'seeded_random':regs[5:6], 'seed':'fixed'})
    bundle=analysis.proactive_bundle('0')
    assert '5' in bundle['comparison_summaries']
    assert len(bundle['charts'][0]['datasets'])==4


def test_service_verifier_read_only_contract(monkeypatch):
    monkeypatch.setenv('DEMO_SEED_ON_START','false')
    from scripts import verify_changwon_service as verifier
    store=db.MemoryStore()
    monkeypatch.setattr(db,'_store',store)
    monkeypatch.setattr(verifier,'settings',SimpleNamespace(use_memory_db=False,analysis_scope_prefix='4812'))
    monkeypatch.setattr(analysis,'settings',SimpleNamespace(analysis_scope_prefix='4812'))
    rid='4812313300'
    store.set('regions',rid,{'name':'남양동','bjd_code':rid})
    row={'region_id':rid,'month':'2026-09','metrics':{'population_total':100},
         'index_meta':{'comparison_scope':'changwon','comparison_month':'2026-09','official_statistic':False}}
    store.set('monthly_data',rid+'_2026-09',row)
    store.set('region_latest',rid,row)
    store.set('rollout_reports','changwon_v32_final',{
        'scope':'changwon','latest_month':'2026-09',
        'quality_report':{'minimum_100_points_met':True,'invalid_numeric_count':0,'regions_master_count':1}})
    def forbidden(*args,**kwargs):
        raise AssertionError('verification must not write to the database')
    for method in ('create','set','update','delete'):
        monkeypatch.setattr(store,method,forbidden)
    assert verifier.verify()['status']=='passed'
