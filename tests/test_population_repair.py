import pytest
from scripts.population_repair_core import validate_rows, validate_bundle, population_reconciliation

def test_scope_month_and_conflicting_duplicates():
    row={'stdgCd':'4812510600','statsYm':'202609','totNmprCnt':237}
    assert validate_rows([row,row],'4812510600','2026-09') == [row]
    for bad in [{**row,'statsYm':'202608'},{**row,'stdgCd':'4812510700'}]:
        with pytest.raises(ValueError): validate_rows([bad],'4812510600','2026-09')
    with pytest.raises(ValueError): validate_rows([row,{**row,'totNmprCnt':238}],'4812510600','2026-09')

def test_age_and_households_must_reconcile():
    b={'population':{'population_total':10,'population_male':4,'population_female':6,'households':7},
       'age_population':{**{f'age_{i}_{i+9}':0 for i in range(0,100,10)},'age_100_plus':0,'age_20_29':10},
       'single_household':{'single_households':3}}
    assert validate_bundle(b)
    b['age_population']['age_20_29']=9
    with pytest.raises(ValueError): validate_bundle(b)

def test_equal_total_cannot_hide_region_errors():
    regions=[{'id':'4812510600'},{'id':'4812510700'}]
    benchmark={'regions':{'4812510600':{'population_total':2},'4812510700':{'population_total':3}},
               'totals':{'48125':{'population_total':5},'48120':{'population_total':5}}}
    rows=[{'region_id':'4812510600','metrics':{'population_total':3}},
          {'region_id':'4812510700','metrics':{'population_total':2}}]
    assert population_reconciliation(regions,rows,benchmark)['status']=='failed'

def test_unknown_is_not_automatically_zero():
    r=population_reconciliation([{'id':'4812510600'}],[],{'regions':{},'totals':{'48120':{'population_total':0}}})
    assert r['unknown_no_official_rows']==['4812510600']

def test_regular_collector_uses_children_without_parent_double_count(monkeypatch):
    from scripts import pipeline
    parent={'id':'4812131000','bjd_code':'4812131000','name':'북면','region_type':'eup_myeon',
            'population_query_codes':['4812131021','4812131022']}
    calls=[]
    class Client:
        def get_all(self,url,params):
            code=params['stdgCd'];calls.append(code)
            return [{'stdgCd':code,'statsYm':'202609','totNmprCnt':10,'hhCnt':4,'maleNmprCnt':5,'femlNmprCnt':5}]
    monkeypatch.setattr(pipeline,'all_regions',lambda:[parent])
    monkeypatch.setattr(pipeline,'DataGoKrClient',Client)
    monkeypatch.setenv('POPULATION_API_URL','https://example.invalid')
    monkeypatch.setenv('POPULATION_QUERY_JSON','{"stdgCd":"{bjd_code}"}')
    monkeypatch.setenv('POPULATION_QUERY_SCOPE','region')
    result=pipeline.collect_population('2026-09')
    assert calls==['4812131021','4812131022']
    assert result[parent['id']]['population_total']==20
    parent['population_query_codes'].append('4812131021')
    with pytest.raises(RuntimeError):pipeline.collect_population('2026-09')
