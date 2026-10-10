import pytest
from scripts.repair_nonpopulation import state, merge_patch, CheckedClient, mapped, unique, FIELDS, CATALOG
from scripts.collect.data_go_kr import DataGoKrClient

def test_states_distinguish_unqueried_empty_and_legacy():
    assert state({},'apt_sale')=='unqueried'
    assert state({'freshness':{'sources':{'apt_sale':{'status':'no_data'}}}},'apt_sale')=='no_data'
    assert state({'metrics':{'sale_count':3}},'apt_sale')=='legacy_unverified'
    row={'metrics':{'sale_count':3},'freshness':{'sources':{'apt_sale':{'status':'no_data'}}}}
    assert state(row,'apt_sale')=='conflict'
    row['freshness']['sources']['apt_sale']['status']='success'
    assert state(row,'apt_sale')=='stored'

def test_patch_preserves_population_metadata_and_is_idempotent():
    old={'metrics':{'population_total':123,'age_20_29':30},'index_meta':{'version':'old'},'freshness':{'sources':{'population':{'status':'success'}}}}
    row=merge_patch(old,'apt_sale',{'sale_count':2},'2026-09','4812110100',2)
    assert row['metrics']['population_total']==123
    assert row['index_meta']==old['index_meta']
    assert row['freshness']['sources']['population']==old['freshness']['sources']['population']
    assert merge_patch(row,'apt_sale',{'sale_count':99},'2026-09','4812110100',99) is None
    assert 'apt_sale' not in old['freshness']['sources']
    with pytest.raises(ValueError): merge_patch(old,'apt_sale',{'population_total':0},'2026-09','4812110100',1)

def test_no_data_requires_completed_query_and_no_zero_population():
    row=merge_patch({'metrics':{'population_total':8}},'commerce',{},'2026-09','4812110100',0)
    assert state(row,'commerce')=='no_data'
    assert 'business_count' not in row['metrics']
    assert row['metrics']['population_total']==8

def test_bad_envelope_is_not_empty(monkeypatch):
    monkeypatch.setattr(DataGoKrClient,'get',lambda *a,**kw:{'_raw':'gateway failure'})
    with pytest.raises(ValueError): CheckedClient(service_key='test').get('unused')

def test_incomplete_and_repeated_pages_are_rejected(monkeypatch):
    client=CheckedClient(service_key='test')
    responses=iter([{'body':{'items':[{'id':1}],'totalCount':2}},{'body':{'items':[],'totalCount':2}}])
    monkeypatch.setattr(client,'get',lambda *a,**kw:next(responses))
    with pytest.raises(ValueError): client.get_all('unused',page_size=1)
    monkeypatch.setattr(client,'get',lambda *a,**kw:{'body':{'items':[{'id':1}],'totalCount':2}})
    with pytest.raises(ValueError): client.get_all('unused',page_size=1)

def test_legitimate_empty_and_multiple_pages(monkeypatch):
    client=CheckedClient(service_key='test')
    responses=iter([{'body':{'items':[{'id':1}],'totalCount':2}},{'body':{'items':[{'id':2}],'totalCount':2}}])
    monkeypatch.setattr(client,'get',lambda *a,**kw:next(responses))
    assert len(client.get_all('unused',page_size=1))==2
    monkeypatch.setattr(client,'get',lambda *a,**kw:{'body':{'items':[],'totalCount':0}})
    assert client.get_all('unused')==[]

def test_mapping_and_stable_dedup():
    regions=[{'id':'4812110100','name':'동','bjd_code':'4812110100'}]
    assert mapped([{'bjdongCd':'4812110100'}],regions,'48121')[0]['stdgCd']=='4812110100'
    with pytest.raises(ValueError): mapped([{'bjdongCd':'4812110100'}],regions,'48123')
    with pytest.raises(ValueError): mapped([{'stdgCd':'4812110100','dealYear':2022,'dealMonth':10}],regions,'48121','2022-11')
    assert len(unique([{'kaptCode':'a'},{'kaptCode':'a'}],'kaptCode'))==1
    with pytest.raises(ValueError): unique([{'kaptCode':'a','n':1},{'kaptCode':'a','n':2}],'kaptCode')
    assert len(CATALOG)==11 and len(FIELDS)==5 and 'population' not in FIELDS


def test_nonempty_rows_without_aggregate_cannot_be_labelled_empty():
    with pytest.raises(ValueError): merge_patch({},'apt_sale',{},'2026-09','4812110100',3)
    with pytest.raises(ValueError): merge_patch({},'apt_sale',{'sale_count':3},'2026-09','4812110100',0)


def test_scope_uses_204_legal_regions_not_193_population_benchmark():
    import json
    from backend.db import MemoryStore
    from scripts.repair_nonpopulation import ROOT, scope, master_doc, _is_gyeongnam_eup_myeon_dong
    codes=json.loads((ROOT/'data/current_changwon_codes_verified20261010.json').read_text())
    store=MemoryStore()
    for r in codes:
        if _is_gyeongnam_eup_myeon_dong(r) and str(r['region_cd']).startswith('4812'):
            doc=master_doc(r); store.set('regions',doc['id'],doc)
    regions, hierarchy=scope(store)
    assert len(regions)==len(hierarchy)==204
    reference=json.loads((ROOT/'data/population_reference_202609.json').read_text())['regions']
    absent=set(hierarchy)-set(reference)
    assert len(absent)==11
    assert all(hierarchy[rid]['children']==[rid] for rid in absent)
    rural=[r for r in regions if r['region_type']=='eup_myeon']
    assert len(rural)==8
    for r in rural:
        assert hierarchy[r['id']]['children']
        assert all(c[:8]==r['id'][:8] and c[-2:]!='00' for c in hierarchy[r['id']]['children'])
    for rid, entry in reference.items():
        assert set(entry['children']).issubset(hierarchy[rid]['children'])
    official_ri={str(r['region_cd']) for r in codes if len(str(r['region_cd']))==10 and str(r['region_cd'])[-2:]!='00'}
    assert {c for r in rural for c in hierarchy[r['id']]['children']}==official_ri
    store.delete('regions',regions[0]['id'])
    with pytest.raises(ValueError,match='204'): scope(store)
