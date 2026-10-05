from scripts.cloud_rollout import build_tasks, initial_state, is_retryable


def _regions(n=3):
    return [{'id': f'481230000{i}', 'bjd_code': f'481230000{i}'} for i in range(n)]


def test_historical_task_count():
    tasks = build_tasks(
        stage='historical', regions=_regions(3), batch_size=2,
        historical_start='2026-08', historical_end='2026-09', snapshot_month='2026-09'
    )
    # 2 batches * 2 months * 5 core sources
    assert len(tasks) == 20
    assert tasks[0].stage == 'historical'


def test_snapshot_task_count():
    tasks = build_tasks(
        stage='snapshot', regions=_regions(3), batch_size=2,
        historical_start='2026-08', historical_end='2026-09', snapshot_month='2026-09'
    )
    # 2 batches * 3 snapshot sources
    assert len(tasks) == 6


def test_retry_classification():
    assert is_retryable('ReadTimeout: slow server') is True
    assert is_retryable('ResourceExhausted: 429 Quota exceeded') is True
    assert is_retryable('HTTP 503 temporarily unavailable') is True
    assert is_retryable('400 Client Error: bad request') is False
    assert is_retryable('403 Client Error: denied') is False


def test_initial_state():
    s = initial_state(
        scope='gyeongnam', region_count=523, batch_size=10,
        historical_start='2022-10', historical_end='2026-09', snapshot_month='2026-09'
    )
    assert s['stage'] == 'historical'
    assert s['cursor'] == 0
    assert s['status'] == 'running'
    assert s['region_count'] == 523


def test_version_31_job_id_and_partial_resume(monkeypatch):
    import scripts.cloud_rollout as cr

    class FakeStore:
        def get(self, collection, doc_id):
            if collection != 'monthly_data':
                return None
            if doc_id == '4812300000_2026-09':
                return {'freshness': {'sources': {'population': {'status': 'ok'}}}}
            if doc_id == '4812300001_2026-09':
                return {'freshness': {'sources': {'population': {'status': 'no_data'}}}}
            return None

    monkeypatch.setattr(cr, 'get_store', lambda: FakeStore())
    task = cr.CloudTask('historical', 0, 'population', '2026-09', ('4812300000','4812300001','4812300002'))
    assert cr.incomplete_region_ids(task) == ['4812300002']
    assert cr.job_id('changwon') == 'cloud_changwon_v31'


def test_nodata_patch_is_durable_completion(monkeypatch):
    import scripts.pipeline as pl
    from backend.db import MemoryStore

    store = MemoryStore()
    store.set('regions', '4812300000', {'id': '4812300000', 'bjd_code': '4812300000', 'name': '가상동'}, merge=False)
    monkeypatch.setattr(pl, 'get_store', lambda: store)
    pl.apply_patches(
        '2022-10', 'population',
        {'4812300000': pl.no_data_patch('NODATA_ERROR')},
        provisional=False,
    )
    row = store.get('monthly_data', '4812300000_2022-10')
    assert row is not None
    assert row['freshness']['sources']['population']['status'] == 'no_data'
    assert row['metrics'] == {}
