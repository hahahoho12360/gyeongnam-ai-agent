"""Checkpoint 3.1 - GitHub Actions용 무인 Cloud Rollout.

목적
----
사용자 PC가 꺼져 있어도 GitHub-hosted runner가 경남/창원 데이터 수집을 이어간다.
진행상태는 로컬 파일이 아니라 Firestore ``rollout_jobs`` 컬렉션에 저장하므로
GitHub Actions runner가 매 실행마다 새 VM으로 바뀌어도 이어서 실행할 수 있다.

안전 원칙
---------
1. 한 번의 GitHub Actions job이 6시간 한도에 닿지 않도록 자체 시간예산을 둔다.
2. source-month-batch 한 작업이 성공할 때마다 Firestore에 cursor를 저장한다.
3. 동일 작업이 이미 Firestore monthly_data에 저장된 경우 API 재호출을 건너뛴다.
4. retry 가능한 timeout/429/5xx는 제한 횟수만 재시도한다.
5. 설정/400/401/403류 오류는 무한 반복하지 않고 blocked 상태로 멈춘다.
6. Historical → Snapshot → Composite Index → Data Quality 순으로 진행한다.
7. 완료/중단 상태를 artifacts/cloud_rollout_status.json에도 기록한다.

로컬 예시
---------
python scripts/cloud_rollout.py --scope changwon --max-runtime-minutes 15
python scripts/cloud_rollout.py --scope gyeongnam --max-runtime-minutes 15

GitHub Actions에서는 .github/workflows/cloud-rollout.yml이 이 스크립트를 호출한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.collect.redaction import redact
from backend.config import settings
from backend.data_quality import quality_report
from backend.db import get_store, utcnow_iso
from scripts.backfill import CORE_HISTORICAL_SOURCES, SNAPSHOT_SOURCES, resolve_regions
from scripts.pipeline import month_range, month_shift, recompute_indexes, run_source

VERSION = 31
JOB_COLLECTION = 'rollout_jobs'
REPORT_COLLECTION = 'rollout_reports'
STATUS_PATH = ROOT / 'artifacts' / 'cloud_rollout_status.json'
SCOPE_PREFIX = {'changwon': '4812', 'gyeongnam': None}
RETRYABLE_MARKERS = (
    'ReadTimeout', 'ConnectTimeout', 'ConnectionError', 'Timeout',
    '429', 'Quota exceeded', 'ResourceExhausted',
    '500', '502', '503', '504', 'temporarily unavailable',
)
NON_RETRYABLE_MARKERS = (
    '400 Client Error', '401 Client Error', '403 Client Error',
    'SERVICE_KEY_IS_NOT_REGISTERED', 'SERVICE_ACCESS_DENIED',
    'NO_OPENAPI_SERVICE', 'INVALID_REQUEST',
)


def previous_month(today: date | None = None) -> str:
    today = today or date.today()
    return month_shift(f'{today.year:04d}-{today.month:02d}', -1)


def _region_code(row: dict[str, Any]) -> str:
    return str(row.get('bjd_code') or row.get('id') or '').strip()


def select_scope_regions(scope: str) -> list[dict[str, Any]]:
    if scope == 'changwon':
        return resolve_regions(
            region_ids=None, sigungu_prefix='4812', all_regions=False,
            region_offset=0, max_regions=10000,
        )
    if scope == 'gyeongnam':
        return resolve_regions(
            region_ids=None, sigungu_prefix=None, all_regions=True,
            region_offset=0, max_regions=10000,
        )
    raise ValueError(f'지원하지 않는 scope: {scope}')


def chunked(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if size < 1:
        raise ValueError('batch_size는 1 이상이어야 합니다.')
    return [rows[i:i + size] for i in range(0, len(rows), size)]


@dataclass(frozen=True)
class CloudTask:
    stage: str
    batch_index: int
    source: str
    month: str
    region_ids: tuple[str, ...]

    @property
    def key(self) -> str:
        return f'{self.stage}:b{self.batch_index}:{self.source}:{self.month}'


def build_tasks(
    *,
    stage: str,
    regions: list[dict[str, Any]],
    batch_size: int,
    historical_start: str,
    historical_end: str,
    snapshot_month: str,
) -> list[CloudTask]:
    batches = chunked(regions, batch_size)
    tasks: list[CloudTask] = []
    if stage == 'historical':
        for bi, batch in enumerate(batches):
            ids = tuple(_region_code(r) for r in batch if _region_code(r))
            for month in month_range(historical_start, historical_end):
                for source in CORE_HISTORICAL_SOURCES:
                    tasks.append(CloudTask(stage, bi, source, month, ids))
    elif stage == 'snapshot':
        for bi, batch in enumerate(batches):
            ids = tuple(_region_code(r) for r in batch if _region_code(r))
            for source in SNAPSHOT_SOURCES:
                tasks.append(CloudTask(stage, bi, source, snapshot_month, ids))
    else:
        raise ValueError(f'task stage 미지원: {stage}')
    return tasks


def job_id(scope: str) -> str:
    return f'cloud_{scope}_v31'


def initial_state(
    *, scope: str, region_count: int, batch_size: int,
    historical_start: str, historical_end: str, snapshot_month: str,
) -> dict[str, Any]:
    return {
        'version': VERSION,
        'scope': scope,
        'status': 'running',
        'stage': 'historical',
        'cursor': 0,
        'batch_size': batch_size,
        'region_count': region_count,
        'historical_start': historical_start,
        'historical_end': historical_end,
        'snapshot_month': snapshot_month,
        'consecutive_failures': 0,
        'total_success_tasks': 0,
        'total_skipped_tasks': 0,
        'run_count': 0,
        'created_at': utcnow_iso(),
        'updated_at': utcnow_iso(),
    }


def save_state(state: dict[str, Any]) -> None:
    state['updated_at'] = utcnow_iso()
    get_store().set(JOB_COLLECTION, job_id(str(state['scope'])), redact(state), merge=False)


def load_or_init_state(
    *, scope: str, regions: list[dict[str, Any]], batch_size: int,
    historical_start: str, historical_end: str, snapshot_month: str,
    reset: bool,
) -> dict[str, Any]:
    store = get_store()
    existing = store.get(JOB_COLLECTION, job_id(scope))
    if reset or not existing or int(existing.get('version') or 0) != VERSION:
        state = initial_state(
            scope=scope, region_count=len(regions), batch_size=batch_size,
            historical_start=historical_start, historical_end=historical_end,
            snapshot_month=snapshot_month,
        )
        save_state(state)
        return state

    # 시작한 작업의 범위는 중간에 바뀌면 cursor 의미가 깨지므로 Firestore 상태를 우선한다.
    return {k: v for k, v in existing.items() if k != 'id'}


def incomplete_region_ids(task: CloudTask) -> list[str]:
    """이미 성공 또는 no_data로 기록된 지역은 제외하고 실제 미완료 지역만 반환한다.

    v2.9 로컬 실행이나 이전 Cloud run이 Batch 중 일부만 끝낸 경우에도 완료 지역을
    재호출하지 않아 API/Firestore 비용과 시간을 줄인다.
    """
    store = get_store()
    pending: list[str] = []
    for rid in task.region_ids:
        row = store.get('monthly_data', f'{rid}_{task.month}')
        sources = ((row or {}).get('freshness') or {}).get('sources') or {}
        if task.source not in sources:
            pending.append(rid)
    return pending


def task_is_complete(task: CloudTask) -> bool:
    return not incomplete_region_ids(task)


def is_retryable(error: str) -> bool:
    text = str(error or '')
    if any(x in text for x in NON_RETRYABLE_MARKERS):
        return False
    return any(x in text for x in RETRYABLE_MARKERS)


def write_status(payload: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(exist_ok=True)
    STATUS_PATH.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2), encoding='utf-8')


def status_payload(state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    payload = {
        'version': VERSION,
        'scope': state.get('scope'),
        'status': state.get('status'),
        'stage': state.get('stage'),
        'cursor': state.get('cursor'),
        'region_count': state.get('region_count'),
        'batch_size': state.get('batch_size'),
        'historical_start': state.get('historical_start'),
        'historical_end': state.get('historical_end'),
        'snapshot_month': state.get('snapshot_month'),
        'total_success_tasks': state.get('total_success_tasks', 0),
        'total_skipped_tasks': state.get('total_skipped_tasks', 0),
        'consecutive_failures': state.get('consecutive_failures', 0),
        'last_task': state.get('last_task'),
        'last_error': state.get('last_error'),
        'updated_at': state.get('updated_at'),
        **extra,
    }
    return redact(payload)


def finalize_quality(state: dict[str, Any]) -> None:
    report = quality_report()
    report_doc = {
        'version': VERSION,
        'scope': state['scope'],
        'generated_at': utcnow_iso(),
        'historical_period': [state['historical_start'], state['historical_end']],
        'snapshot_month': state['snapshot_month'],
        'quality_report': report,
    }
    get_store().set(REPORT_COLLECTION, job_id(state['scope']), report_doc, merge=False)
    out = ROOT / 'artifacts' / f'cloud_rollout_{state["scope"]}_summary.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report_doc, ensure_ascii=False, indent=2), encoding='utf-8')


def advance_stage(state: dict[str, Any]) -> None:
    stage = state['stage']
    if stage == 'historical':
        state['stage'] = 'snapshot'; state['cursor'] = 0
    elif stage == 'snapshot':
        state['stage'] = 'indexes'; state['cursor'] = 0
    elif stage == 'indexes':
        state['stage'] = 'quality'; state['cursor'] = 0
    elif stage == 'quality':
        state['stage'] = 'done'; state['cursor'] = 0; state['status'] = 'complete'
    save_state(state)


def execute_task(task: CloudTask, *, attempts: int, retry_wait_seconds: int) -> tuple[bool, dict[str, Any]]:
    old_many = os.environ.get('REGION_FILTER_IDS')
    old_one = os.environ.get('REGION_FILTER_ID')
    old_defer = os.environ.get('DEFER_INDEX_RECOMPUTE')
    os.environ['REGION_FILTER_IDS'] = ','.join(task.region_ids)
    os.environ.pop('REGION_FILTER_ID', None)
    os.environ['DEFER_INDEX_RECOMPUTE'] = 'true'
    try:
        last: dict[str, Any] = {}
        for attempt in range(1, attempts + 1):
            print(f'[CLOUD] {task.key} attempt={attempt}/{attempts} regions={len(task.region_ids)}')
            result = run_source(task.source, task.month)
            last = result
            print(result)
            if result.get('status') == 'ok':
                return True, result
            error = str(result.get('error') or '')
            if not is_retryable(error):
                return False, result
            if attempt < attempts:
                wait = retry_wait_seconds * (2 ** (attempt - 1))
                print(f'[CLOUD] retryable error. {wait}초 후 재시도')
                time.sleep(wait)
        return False, last
    finally:
        if old_many is None: os.environ.pop('REGION_FILTER_IDS', None)
        else: os.environ['REGION_FILTER_IDS'] = old_many
        if old_one is None: os.environ.pop('REGION_FILTER_ID', None)
        else: os.environ['REGION_FILTER_ID'] = old_one
        if old_defer is None: os.environ.pop('DEFER_INDEX_RECOMPUTE', None)
        else: os.environ['DEFER_INDEX_RECOMPUTE'] = old_defer


def main() -> int:
    p = argparse.ArgumentParser(description='Checkpoint 3.1 GitHub Actions Cloud Rollout')
    p.add_argument('--scope', choices=['changwon', 'gyeongnam'], required=True)
    p.add_argument('--historical-start', default='2022-10')
    p.add_argument('--historical-end', default=None)
    p.add_argument('--snapshot-month', default=None)
    p.add_argument('--batch-size', type=int, default=10)
    p.add_argument('--max-runtime-minutes', type=int, default=270,
                   help='GitHub hosted runner 6시간 한도보다 충분히 짧게 종료. 기본 270분')
    p.add_argument('--task-attempts', type=int, default=3)
    p.add_argument('--retry-wait-seconds', type=int, default=10)
    p.add_argument('--max-consecutive-failure-runs', type=int, default=4)
    p.add_argument('--reset', action='store_true', help='Firestore cloud rollout 진행상태를 처음부터 재설정')
    p.add_argument('--status-only', action='store_true')
    a = p.parse_args()

    if settings.use_memory_db:
        print('ERROR: USE_MEMORY_DB=true입니다. Cloud Rollout은 Firestore 모드만 지원합니다.')
        return 2
    if not settings.firebase_project_id:
        print('ERROR: FIREBASE_PROJECT_ID가 비어 있습니다.')
        return 2
    if not settings.data_go_kr_service_key:
        print('ERROR: DATA_GO_KR_SERVICE_KEY가 비어 있습니다.')
        return 2
    if a.batch_size < 1 or a.batch_size > 50:
        print('ERROR: --batch-size는 1~50 사이를 사용하세요.')
        return 2

    historical_end = a.historical_end or previous_month()
    snapshot_month = a.snapshot_month or historical_end
    regions = select_scope_regions(a.scope)
    state = load_or_init_state(
        scope=a.scope, regions=regions, batch_size=a.batch_size,
        historical_start=a.historical_start, historical_end=historical_end,
        snapshot_month=snapshot_month, reset=a.reset,
    )
    state['run_count'] = int(state.get('run_count') or 0) + 1
    state['status'] = 'running'
    save_state(state)

    if a.status_only:
        payload = status_payload(state)
        write_status(payload); print(json.dumps(redact(payload), ensure_ascii=False, indent=2)); return 0

    # 기존 상태가 가진 설정을 사용해 task order를 절대 바꾸지 않는다.
    batch_size = int(state['batch_size'])
    historical_start = str(state['historical_start'])
    historical_end = str(state['historical_end'])
    snapshot_month = str(state['snapshot_month'])

    started = time.monotonic()
    deadline = started + max(1, a.max_runtime_minutes) * 60

    print('=' * 76)
    print('Gyeongnam AI Agent - Checkpoint 3.1 CLOUD ROLLOUT')
    print(f'project    : {settings.firebase_project_id}')
    print(f'scope      : {a.scope}')
    print(f'regions    : {len(regions)}')
    print(f'batch size : {batch_size}')
    print(f'historical : {historical_start} ~ {historical_end}')
    print(f'snapshot   : {snapshot_month}')
    print(f'stage      : {state["stage"]}')
    print(f'cursor     : {state["cursor"]}')
    print('=' * 76)

    while time.monotonic() < deadline:
        stage = str(state['stage'])
        if stage in {'historical', 'snapshot'}:
            tasks = build_tasks(
                stage=stage, regions=regions, batch_size=batch_size,
                historical_start=historical_start, historical_end=historical_end,
                snapshot_month=snapshot_month,
            )
            cursor = int(state.get('cursor') or 0)
            if cursor >= len(tasks):
                print(f'[CLOUD] {stage} stage 완료 ({len(tasks)} tasks)')
                advance_stage(state)
                continue

            task = tasks[cursor]
            state['last_task'] = task.key
            state['stage_total_tasks'] = len(tasks)
            state['stage_progress_pct'] = round(cursor * 100 / len(tasks), 2) if tasks else 100.0
            save_state(state)

            # Cloud runner가 중간에 죽었거나 v2.9가 일부 지역만 끝낸 경우, 완료 지역은 빼고
            # 실제 미완료 지역만 API에 전달한다. no_data freshness도 '처리 완료'로 인정한다.
            pending_ids = incomplete_region_ids(task)
            if not pending_ids:
                print(f'[CLOUD] already complete → skip: {task.key}')
                state['cursor'] = cursor + 1
                state['total_skipped_tasks'] = int(state.get('total_skipped_tasks') or 0) + 1
                state['consecutive_failures'] = 0
                state.pop('last_error', None)
                save_state(state)
                continue

            if len(pending_ids) != len(task.region_ids):
                print(f'[CLOUD] partial resume: {len(task.region_ids)-len(pending_ids)}개 완료, {len(pending_ids)}개만 처리')
            effective_task = CloudTask(task.stage, task.batch_index, task.source, task.month, tuple(pending_ids))
            ok, result = execute_task(effective_task, attempts=a.task_attempts, retry_wait_seconds=a.retry_wait_seconds)
            if ok:
                state['cursor'] = cursor + 1
                state['total_success_tasks'] = int(state.get('total_success_tasks') or 0) + 1
                state['consecutive_failures'] = 0
                state.pop('last_error', None)
                save_state(state)
                continue

            error = str(result.get('error') or 'unknown error')
            state['last_error'] = error
            state['consecutive_failures'] = int(state.get('consecutive_failures') or 0) + 1
            if not is_retryable(error):
                state['status'] = 'blocked'
            elif state['consecutive_failures'] >= a.max_consecutive_failure_runs:
                state['status'] = 'blocked'
            else:
                state['status'] = 'needs_continue'
            save_state(state)
            payload = status_payload(state, retry_after_seconds=60 if state['status'] == 'needs_continue' else 0)
            write_status(payload)
            print(json.dumps(redact(payload), ensure_ascii=False, indent=2))
            return 0

        if stage == 'indexes':
            if a.scope == 'gyeongnam':
                print(f'[CLOUD] Composite Index 재계산: {snapshot_month}')
                count = recompute_indexes(snapshot_month)
                state['indexes_rows'] = count
            else:
                print('[CLOUD] 창원 scope는 경남 전체 비교가 아니므로 Composite Index를 deferred 처리합니다.')
                state['indexes_rows'] = 0
                state['indexes_deferred'] = True
            advance_stage(state)
            continue

        if stage == 'quality':
            print('[CLOUD] Data Quality 리포트 생성')
            finalize_quality(state)
            advance_stage(state)
            continue

        if stage == 'done':
            state['status'] = 'complete'
            save_state(state)
            payload = status_payload(state, retry_after_seconds=0)
            write_status(payload)
            print(json.dumps(redact(payload), ensure_ascii=False, indent=2))
            return 0

        state['status'] = 'blocked'; state['last_error'] = f'unknown stage: {stage}'
        save_state(state)
        payload = status_payload(state, retry_after_seconds=0)
        write_status(payload); print(json.dumps(redact(payload), ensure_ascii=False, indent=2)); return 0

    # 시간예산 종료는 정상 동작이다. GitHub Actions가 다음 workflow_dispatch를 이어서 만든다.
    state['status'] = 'needs_continue'
    state['consecutive_failures'] = 0
    state['last_stop_reason'] = 'runtime_budget_reached'
    save_state(state)
    payload = status_payload(state, retry_after_seconds=20)
    write_status(payload)
    print('[CLOUD] 자체 시간예산 도달. 진행상태를 Firestore에 저장하고 다음 Actions 실행으로 넘깁니다.')
    print(json.dumps(redact(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

