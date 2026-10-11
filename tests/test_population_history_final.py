import json
from pathlib import Path
import pytest
from scripts.population_history_final import (
    SOURCES, KEYS, UnresolvedMonth, inventory, resolve_month, prefetch_window,
)


def rows(code, n):
    common={'stdgCd':code,'statsYm':'202408'}
    population={**common,'totNmprCnt':n,'hhCnt':n,'maleNmprCnt':0,'femlNmprCnt':n}
    age={**common,**{f'{sex}{i}AgeNmprCnt':n if sex=='feml' and i==20 else 0
                    for sex in ['male','feml'] for i in range(0,101,10)}}
    single={**common,'totHhCnt':n,'maleHhCnt':0,'femlHhCnt':n,
            **{f'{sex}{i}AgeHhCnt':n if sex=='feml' and i==20 else 0
               for sex in ['male','feml'] for i in range(0,101,10)}}
    return {s:[r] for s,r in zip(SOURCES,[population,age,single])}


def fixture(parent_n, child_n, official_n, parents=1):
    master={};children={};captures={}
    for i in range(parents):
        parent=f'481213{2+i}000';child=f'481213{2+i}021'
        master[parent]={'id':parent,'name':'대산면','bjd_code':parent,'region_type':'eup_myeon'}
        children[parent]=[child]
        for code,n in [(parent,parent_n),(child,child_n)]:
            for source,rs in rows(code,n).items():captures[source,code]=rs
    totals={sig:{k:official_n for k in KEYS} for sig in ['48120','48121']}
    for sig in totals:totals[sig]['population_male']=0
    return master,children,captures,totals


def resolve(f):
    master,children,captures,totals=f
    return resolve_month('2024-08',master,children,captures,totals)


def test_parent_residual_is_included_and_not_hardcoded_to_two():
    for residual in [2,3,11]:
        p=resolve(fixture(residual,6706,6706+residual))
        assert p['patches']['4812132000']['metrics']['population_total']==6706+residual
        assert p['parent_modes']['4812132000']['modes']==['ri_plus_parent']


def test_parent_full_total_is_not_added_twice():
    p=resolve(fixture(6708,6706,6708))
    assert p['parent_modes']['4812132000']['modes']==['parent_only']
    assert p['patches']['4812132000']['metrics']['population_total']==6708


def test_zero_parent_deduplicates_equivalent_child_candidates():
    p=resolve(fixture(0,6706,6706))
    assert p['patches']['4812132000']['metrics']['population_total']==6706


def test_all_empty_success_stays_null_and_strict_rejects():
    f=fixture(0,0,0); master,children,captures,totals=f
    captures={k:[] for k in captures}
    p=resolve_month('2024-08',master,children,captures,totals)
    assert p['patches']['4812132000']['metrics']['population_total'] is None
    with pytest.raises(UnresolvedMonth):resolve_month('2024-08',master,children,captures,totals,'strict')


def test_empty_single_source_is_null_not_zero():
    f=fixture(2,10,12);master,children,captures,totals=f
    for k in captures:
        if k[0]=='single_household':captures[k]=[]
    p=resolve(f)
    assert p['patches']['4812132000']['metrics']['population_total']==12
    assert p['patches']['4812132000']['metrics']['single_households'] is None


def test_same_district_total_cannot_hide_ambiguous_parent_assignments():
    with pytest.raises(UnresolvedMonth):resolve(fixture(2,10,22,parents=2))


def test_sex_and_household_mismatch_blocks_even_if_population_matches():
    f=fixture(2,10,12);f[-1]['48121']['households']=13
    with pytest.raises(UnresolvedMonth):resolve(f)


def test_wrong_month_and_region_are_rejected():
    from scripts.population_repair_core import validate_rows
    with pytest.raises(ValueError):validate_rows(rows('4812132021',1)['population'],'4812132022','2024-08')
    with pytest.raises(ValueError):validate_rows(rows('4812132021',1)['population'],'4812132021','2024-09')


def test_full_inventory_includes_latest_empty_dongs_and_deokcheon_ri():
    root=Path(__file__).resolve().parents[1]
    master,children,codes=inventory(json.loads((root/'data/current_changwon_codes_verified20261010.json').read_text()))
    assert len(master)==204 and len(codes)==317
    assert len(children['4812125000'])==24
    assert {'4812125024','4812111200','4812111300','4812112200','4812132000'} <= set(codes)
    assert sum(bool(c) for c in children.values())==8


def test_transient_code_failure_does_not_abort_other_requests(monkeypatch,tmp_path):
    from scripts import population_history_final as module
    monkeypatch.setattr(module,'OUT',tmp_path)
    monkeypatch.setattr(module,'save',lambda n,v:(tmp_path/n).write_text(json.dumps(v)))
    for s in SOURCES:monkeypatch.setenv(module.SPECS[s][1],'{}')
    monkeypatch.setattr(module,'DataGoKrClient',lambda **kw:None)
    def fake(client,source,code,month):
        if code=='4812132021':raise RuntimeError('Unavailable')
        return rows(code,1)[source]
    monkeypatch.setattr(module,'query',fake)
    errors=prefetch_window(['2024-08'],['4812132021','4812132022'],workers=2)
    assert len(errors)==3
    assert (tmp_path/'population_4812132022_2024-08.json').exists()
    assert not (tmp_path/'population_4812132021_2024-08.json').exists()


def test_atomic_apply_preserves_nonpopulation_fields_and_marks_indexes(monkeypatch,tmp_path):
    from scripts import population_history_final as module
    calls=[]
    class Batch:
        def update(self,ref,fields):calls.append(('update',ref,fields))
        def set(self,ref,fields,**kw):calls.append(('set',ref,fields,kw))
        def commit(self):calls.append(('commit',))
    class Collection:
        def __init__(self,name):self.name=name
        def document(self,key):return self.name+'/'+key
    class Client:
        def batch(self):return Batch()
        def collection(self,name):return Collection(name)
    class Store:
        client=Client()
        def filter_eq(self,*args):return [{'region_id':'4812132000','metrics':{'business_count':22}}]
    monkeypatch.setattr(module,'save',lambda *args:None)
    p=resolve(fixture(2,6706,6708));module.apply_plan(Store(),p)
    updates=[c for c in calls if c[0]=='update']
    assert len(updates)==1
    assert updates[0][2]['metrics.population_total']==6708
    assert 'metrics.business_count' not in updates[0][2]
    assert 'freshness.sources.commerce' not in updates[0][2]
    assert updates[0][2]['indexes_need_recompute'] is True
    assert calls[-1]==('commit',)


def test_failed_range_falls_back_to_single_months_without_shared_env_changes(monkeypatch,tmp_path):
    from scripts import population_history_final as module
    monkeypatch.setattr(module,'OUT',tmp_path)
    monkeypatch.setattr(module,'save',lambda n,v:(tmp_path/n).write_text(json.dumps(v)))
    for s in SOURCES:monkeypatch.setenv(module.SPECS[s][1],'{"srchFrYm":"{yyyymm}"}')
    monkeypatch.setattr(module,'DataGoKrClient',lambda **kw:None)
    def fake(client,source,code,month,template_override=None):
        if template_override is None:raise RuntimeError('Range rejected')
        assert template_override['srchFrYm']==month.replace('-','')
        assert template_override['srchToYm']==month.replace('-','')
        return [{**r,'statsYm':month.replace('-','')} for r in rows(code,1)[source]]
    monkeypatch.setattr(module,'query',fake)
    assert prefetch_window(['2024-08','2024-09'],['4812132021'],2)==[]
    for source in SOURCES:
        for month in ['2024-08','2024-09']:
            assert json.loads((tmp_path/f'{source}_4812132021_{month}.json').read_text())['successful_request']


def test_provider_outage_diagnostics_do_not_exceed_firestore_document_limit():
    from scripts.population_history_final import compact_status
    errors=[{'source':'population','code':f'48121{i:05d}','months':['2024-08'],'exception_type':'RuntimeError'} for i in range(951)]
    status={'status':'partial','issues':[{'month':f'2024-{i+1:02d}','errors':errors} for i in range(25)]}
    compact=compact_status(status)
    assert len(json.dumps(compact).encode()) < 100_000
    assert compact['issues'][0]['error_count']==951
    assert len(compact['issues'][0]['errors'])==10
    assert len(status['issues'][0]['errors'])==951
