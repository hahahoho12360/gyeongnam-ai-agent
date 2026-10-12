import json
import pytest
from scripts import repair_nonpopulation as n

@pytest.fixture
def regions():
    codes=list(n.official_inventory().values())
    return [n.master_doc(r) for r in codes if n._is_gyeongnam_eup_myeon_dong(r) and r['region_cd'].startswith('4812')]

@pytest.mark.parametrize('gu,name',[('48121','북면 감계리'),('48125','진동면 진동리'),('48127','내서읍 삼계리')])
def test_official_ri_names_and_split_codes_roll_up(regions,gu,name):
    inventory=n.official_inventory()
    code=next(code for code,r in inventory.items() if r['locatadd_nm'].endswith(name))
    expected=code[:8]+'00'
    row={'sggCd':gu,'umdNm':name,'dealYear':2022,'dealMonth':10}
    assert n.mapped([row],regions,gu,'2022-10')[0]['stdgCd']==expected
    row['umdCd']=code[5:]
    assert n.mapped([row],regions,gu,'2022-10')[0]['stdgCd']==expected

@pytest.mark.parametrize('row,category',[
    ({'sggCd':'48121','umdCd':'99999','umdNm':'북면 감계리'},'지역 코드 불일치'),
    ({'sggCd':'48123','umdNm':'북면 감계리'},'지역 코드 불일치'),
    ({'umdNm':'북면 가짜리'},'지역 연결 실패'),
    ({'umdNm':'북면 감계리','dealYear':2023,'dealMonth':10},'기준월 불일치'),
])
def test_failed_mapping_never_becomes_empty(regions,row,category):
    row={'dealYear':2022,'dealMonth':10,**row}
    with pytest.raises(n.DiagnosticError) as error:
        n.mapped([row],regions,'48121','2022-10')
    assert error.value.category==category


def test_safe_diagnostics_do_not_include_urls_or_key():
    assert n.diagnostic(ValueError('https://api/?serviceKey=secret'))=={'category':'API 또는 저장 처리 실패','error_type':'ValueError'}
    assert n.safe_fields({'sggCd':'48121','umdNm':'북면 감계리','serviceKey':'secret','address':'private'})=={'sggCd':'48121','umdNm':'북면 감계리'}


def test_preflight_checks_all_ten_groups_and_collects_errors(monkeypatch,regions,tmp_path):
    calls=[]
    def collect(source,month,group,*args):
        calls.append((source,group[0]['id'][:5]))
        if source=='apt_sale' and group[0]['id'].startswith('48121'):
            raise n.DiagnosticError('지역 연결 실패',umdNm='가짜동')
        return {},{}
    monkeypatch.setattr(n,'collect',collect)
    from types import SimpleNamespace
    cache,errors=n.preflight(SimpleNamespace(),regions,{},'2022-10',tmp_path)
    assert len(calls)==10 and len(cache)==9 and len(errors)==1
    assert len(json.loads((tmp_path/'preflight.json').read_text())['checks'])==10


def test_reindex_one_atomic_batch_and_checkpoint_skip(monkeypatch):
    from scripts import population_history_final as pop
    class Batch:
        def __init__(self): self.writes=[]
        def update(self,ref,data): self.writes.append(('update',ref,data))
        def set(self,ref,data): self.writes.append(('set',ref,data))
    class Collection:
        def document(self,id): return id
    class Store:
        def __init__(self): self.client=self; self.batches=[]; self.checkpoint={}
        def batch(self):
            batch=Batch(); self.batches.append(batch); return batch
        def collection(self,name): return Collection()
        def filter_eq(self,collection,field,month):
            rows=[{'id':'4812110100_2022-10','region_id':'4812110100','month':month,'metrics':{'population_total':8}}] if month=='2022-10' else []
            if rows and commits:
                changes=commits[-1].writes[0][2]
                rows[0].update(derived=changes['derived'],indexes=changes['indexes'])
            return rows
        def set(self,*args,**kwargs):pass
        def list(self,name): return [{'id':'4812110100','month':'2022-10'}]
        def get(self,*args): return self.checkpoint
    commits=[]; monkeypatch.setattr(pop,'commit_batch',lambda batch:commits.append(batch))
    store=Store()
    assert n.reindex(store,[{'id':'4812110100'}],'2022-10')
    assert len(commits)==1 and len(commits[0].writes)==3
    store.checkpoint={'version':n.VERSION,'verified':True}
    assert n.reindex(store,[{'id':'4812110100'}],'2022-10') is False
    assert len(commits)==1


def test_capture_cache_avoids_duplicate_query_and_preserves_failed_rows(monkeypatch,tmp_path):
    class Client:pass
    c=Client();calls=[]
    group=[{'id':'4812110100'}]
    def collect(*args):calls.append(1);return {'4812110100':{'sale_count':1}},{'4812110100':1}
    monkeypatch.setattr(n,'collect',collect)
    assert n.collect_cached('apt_sale','2025-12',group,group,{},c,tmp_path)[1]['4812110100']==1
    n.collect_cached('apt_sale','2025-12',group,group,{},c,tmp_path)
    assert len(calls)==1
    def bad(*args):
        c.last_rows=[{'serviceKey':'secret','stdgCd':'invalid'}]
        raise n.DiagnosticError('지역 연결 실패')
    monkeypatch.setattr(n,'collect',bad)
    with pytest.raises(n.DiagnosticError):n.collect_cached('apt_sale','2026-01',group,group,{},c,tmp_path)
    evidence=json.loads((tmp_path/'failed_apt_sale_2026-01_48121_0.json').read_text())
    assert evidence['received_rows'][0]['serviceKey']=='[REDACTED]'
    assert not (tmp_path/'capture_apt_sale_2026-01_48121.json').exists()


def test_request_budget_stops_before_provider_request():
    budget=n.CollectionBudget(n.time.monotonic()+60)
    with pytest.raises(n.DiagnosticError,match='시간 예산'):budget.check()
    budget=n.CollectionBudget(n.time.monotonic()+1000);budget.failures=3
    with pytest.raises(n.DiagnosticError,match='반복 연결'):budget.check()


def test_workflow_uses_branch_not_commit_and_retries_artifact_upload():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[1]/'.github/workflows/changwon-nonpopulation-repair.yml').read_text()
    assert '--ref "$GITHUB_REF_NAME"' in text
    assert '--ref "$GITHUB_SHA"' not in text
    assert 'steps.upload_primary.outcome' in text
    assert 'retryable_errors' in text
