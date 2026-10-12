import json
from copy import deepcopy
from pathlib import Path
import pytest
from scripts import population_history_final as core
from scripts import population_one_month as runner
from scripts.population_repair_core import validate_rows

FIXTURE=Path(__file__).parent/'fixtures/gwanghwa_202509_original.json'
RID='4812912400'

def original():return json.loads(FIXTURE.read_text())

def test_gwanghwa_distinct_original_metadata_partitions_reconcile():
    rows=original();clean={s:validate_rows(rs,RID,'2025-09') for s,rs in rows.items()}
    assert len(clean['age_population'])==2
    bundle=core.bundle_from(clean,{RID:{'id':RID,'bjd_code':RID,'name':'광화동'}},RID)
    assert bundle['population']['population_total']==727
    assert bundle['age_population']['age_30_39']==66
    assert sum(bundle['age_population'][f'age_{i}_{i+9}'] for i in range(0,100,10))==727


def test_same_partition_conflict_and_identical_count_label_ambiguity_still_blocked():
    rows=original()['age_population'];rows[1]['ctpvNm']=rows[0]['ctpvNm']
    with pytest.raises(ValueError,match='Conflicting'):validate_rows(rows,RID,'2025-09')
    rows=[deepcopy(rows[0]),deepcopy(rows[0])];rows[1]['ctpvNm']='경상남도'
    with pytest.raises(ValueError,match='Ambiguous'):validate_rows(rows,RID,'2025-09')
    assert len(validate_rows([rows[0],deepcopy(rows[0])],RID,'2025-09'))==1


def test_sex_and_bucket_mismatch_rejected_even_if_metadata_differs():
    rows=original();rows['age_population'][1]['feml30AgeNmprCnt']='2'
    with pytest.raises(core.UnresolvedMonth):
        core.bundle_from(rows,{RID:{'id':RID,'bjd_code':RID,'name':'광화동'}},RID)


def test_failed_raw_rows_retained_and_credentials_redacted(monkeypatch,tmp_path):
    def save(name,data):(tmp_path/name).write_text(json.dumps(data))
    monkeypatch.setattr(core,'OUT',tmp_path);monkeypatch.setattr(core,'save',save)
    monkeypatch.setattr(core,'SOURCES',('age_population',))
    monkeypatch.setenv('AGE_POPULATION_QUERY_JSON',json.dumps({'stdgCd':'{bjd_code}'}))
    monkeypatch.setenv('DATA_GO_KR_SERVICE_KEY','secret-for-test-123')
    monkeypatch.setattr(core,'DataGoKrClient',lambda **kw:None)
    def query(*args,**kw):
        rows=original()['age_population'];rows[1]['ctpvNm']=rows[0]['ctpvNm']
        save(f'age_population_{RID}_2025-09.json',{'rows':rows,'url':'https://example.org/?serviceKey=secret-for-test-123'})
        return rows
    monkeypatch.setattr(core,'query',query)
    errors=core.prefetch_window(['2025-09'],[RID],workers=1)
    assert 'Conflicting' in errors[0]['reason']
    failed=tmp_path/f'failed_original_age_population_{RID}_2025-09.json'
    assert len(json.loads(failed.read_text())['original_response']['rows'])==2
    assert 'secret-for-test-123' not in failed.read_text()
    assert not (tmp_path/f'age_population_{RID}_2025-09.json').exists()


def test_transient_failure_recovers_but_recovery_is_bounded(monkeypatch):
    monkeypatch.setattr(runner,'save',lambda *a:None)
    sleeps=[];monkeypatch.setattr(runner.time,'sleep',lambda s:sleeps.append(s))
    b=runner.Budget(600,threshold=2,max_recoveries=1,cooldown_seconds=30)
    b.record({'outcome':'read_timeout'},True);b.record({'outcome':'read_timeout'},True)
    b.check();assert b.degraded and b.recoveries==1 and sleeps==[30]
    b.record({'outcome':'connection_error'},True);b.record({'outcome':'connection_error'},True)
    with pytest.raises(runner.StopCollection,match='circuit'):b.check()


def test_quota_or_permission_error_never_recovered_or_retried(monkeypatch):
    monkeypatch.setattr(runner,'save',lambda *a:None)
    b=runner.Budget(600,max_recoveries=2)
    b.record({'outcome':'api_rate_limit'},True)
    with pytest.raises(runner.StopCollection,match='non_retryable'):b.check()
    assert b.recoveries==0


def test_verified_legal_reference_override_is_not_an_api_value_adjustment():
    root=Path(__file__).resolve().parents[1]
    current=json.loads((root/'data/population_official_history_totals.json').read_text())
    original=json.loads((root/'data/population_official_history_totals_admin_original.json').read_text())
    assert current['months']['2025-09']['48129']['population_total']==185762
    assert original['months']['2025-09']['48129']['population_total']==185761
    for month in current['months']:
        if month!='2025-09':assert current['months'][month]==original['months'][month]
    totals=current['months']['2025-09']
    for key in core.KEYS:assert sum(v[key] for k,v in totals.items() if k!='48120')==totals['48120'][key]
    assert len(current['reference_overrides']['2025-09']['proof_files'])==6


def test_only_transient_failure_has_one_fresh_runner_retry():
    import yaml
    root=Path(__file__).resolve().parents[1]
    workflow=yaml.safe_load((root/'.github/workflows/changwon-population-followup.yml').read_text())
    retries=[j for k,j in workflow['jobs'].items() if k.startswith('retry_month_')]
    assert len(retries)==12
    assert all('retryable_provider_failure' in j['if'] for j in retries)
    assert all(j['with']['attempt']=='retry' for j in retries)
