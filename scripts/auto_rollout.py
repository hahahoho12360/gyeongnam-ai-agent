"""Checkpoint 2.9 - unattended rollout orchestrator.

목적
----
남양동 Pilot 이후 사용자가 여러 Batch 명령을 반복 입력하지 않아도
창원시 또는 경상남도 전체를 한 번의 명령으로 단계적으로 처리한다.

핵심 안전장치
-------------
1. Historical과 Snapshot을 분리한다.
2. Historical은 2022-10부터 마지막 확정월(기본: 전월)까지 처리한다.
3. Snapshot은 Historical 마지막 월 문서에 붙이되 source_as_of는 실제 조회일로 남는다.
4. 지역은 작은 batch로 나눈다.
5. 모든 작업은 Resume 파일을 사용해 중단 후 재시작할 수 있다.
6. quota/일시 오류가 있으면 일정 시간 기다린 뒤 제한 횟수만큼 자동 재시도한다.
7. Composite Index는 경남 전체 완료 후에만 자동 재계산한다.
8. 실행 계획과 최종 상태를 logs/ 및 artifacts/에 남긴다.

예시
----
# 창원시 전체 자동 처리 (Historical + 최신 Snapshot)
python scripts/auto_rollout.py --scope changwon

# 경남 전체 자동 처리
python scripts/auto_rollout.py --scope gyeongnam

# 아무 API/DB 쓰기 없이 계획만 확인
python scripts/auto_rollout.py --scope changwon --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import settings
from backend.data_quality import quality_report
from backend.db import get_store, utcnow_iso
from scripts.backfill import (
    CORE_HISTORICAL_SOURCES,
    SNAPSHOT_SOURCES,
    main as run_backfill,
    resolve_regions,
)
from scripts.pipeline import month_shift, recompute_indexes

SCOPE_PREFIX = {
    'changwon': '4812',
    'gyeongnam': None,
}


def previous_month(today: date | None = None) -> str:
    today = today or date.today()
    return month_shift(f'{today.year:04d}-{today.month:02d}', -1)


def current_month(today: date | None = None) -> str:
    today = today or date.today()
    return f'{today.year:04d}-{today.month:02d}'


def scope_resume_path(scope: str, kind: str) -> str:
    return f'.rollout-{scope}-{kind}.json'


def scope_state_path(scope: str) -> Path:
    return ROOT / f'.rollout-{scope}-state.json'


def load_state(scope: str) -> dict[str, Any]:
    path = scope_state_path(scope)
    if not path.exists():
        return {'version': 1, 'scope': scope, 'stages': {}}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError
        data.setdefault('version', 1)
        data.setdefault('scope', scope)
        data.setdefault('stages', {})
        return data
    except Exception:
        return {'version': 1, 'scope': scope, 'stages': {}}


def save_state(scope: str, state: dict[str, Any]) -> None:
    state['updated_at'] = utcnow_iso()
    scope_state_path(scope).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8'
    )


def _select_scope_regions(scope: str, max_regions: int | None = None) -> list[dict[str, Any]]:
    if scope == 'changwon':
        # 창원 5개 구 법정코드는 공통적으로 4812로 시작한다.
        return resolve_regions(
            region_ids=None,
            sigungu_prefix=SCOPE_PREFIX[scope],
            all_regions=False,
            region_offset=0,
            max_regions=max_regions or 10000,
        )
    if scope == 'gyeongnam':
        return resolve_regions(
            region_ids=None,
            sigungu_prefix=None,
            all_regions=True,
            region_offset=0,
            max_regions=max_regions or 10000,
        )
    raise ValueError(f'지원하지 않는 scope: {scope}')


class Tee:
    def __init__(self, *files):
        self.files = files
    def write(self, data):
        for f in self.files:
            f.write(data)
            f.flush()
        return len(data)
    def flush(self):
        for f in self.files:
            f.flush()


def run_with_retries(
    *,
    scope: str,
    stage: str,
    start: str,
    end: str,
    sources: list[str],
    regions: list[dict[str, Any]],
    batch_size: int,
    resume_file: str,
    max_passes: int,
    retry_wait_seconds: int,
    dry_run: bool,
) -> int:
    """Backfill runner를 resume 기반으로 자동 재시도한다.

    run_backfill return code:
      0: 모든 작업 성공
      1: 일반 실패가 일부 존재
      2: quota 감지로 안전 중단
    """
    if dry_run:
        return run_backfill(
            start, end, sources, resume_file,
            regions=regions, batch_size=batch_size, dry_run_plan=True,
        )

    last_rc = 1
    for attempt in range(1, max_passes + 1):
        print(f'\n[AUTO] {stage} pass {attempt}/{max_passes}')
        last_rc = run_backfill(
            start, end, sources, resume_file,
            regions=regions, batch_size=batch_size, dry_run_plan=False,
        )
        if last_rc == 0:
            print(f'[AUTO] {stage} 완료')
            return 0
        if attempt >= max_passes:
            break
        reason = 'quota/할당량' if last_rc == 2 else '일시 오류'
        print(f'[AUTO] {stage} {reason} 감지. {retry_wait_seconds}초 대기 후 resume 재시도합니다.')
        time.sleep(max(0, retry_wait_seconds))
    return last_rc


def write_report(scope: str, payload: dict[str, Any]) -> Path:
    out_dir = ROOT / 'artifacts'
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f'rollout_{scope}_summary.json'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def main() -> int:
    p = argparse.ArgumentParser(description='Checkpoint 2.9 창원/경남 무인 Rollout')
    p.add_argument('--scope', choices=['changwon', 'gyeongnam'], required=True)
    p.add_argument('--historical-start', default='2022-10')
    p.add_argument('--historical-end', default=None, help='기본값: 현재 날짜의 전월')
    p.add_argument('--snapshot-month', default=None, help='기본값: historical-end. 현재 Snapshot을 마지막 확정월 문서에 결합')
    p.add_argument('--stage', choices=['all', 'historical', 'snapshot', 'indexes'], default='all')
    p.add_argument('--batch-size', type=int, default=5)
    p.add_argument('--max-regions', type=int, default=None, help='테스트용 상한. 생략하면 scope 전체')
    p.add_argument('--max-passes', type=int, default=3)
    p.add_argument('--retry-wait-seconds', type=int, default=60)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--force-indexes', action='store_true', help='창원 scope에서도 Composite Index 계산(권장하지 않음)')
    a = p.parse_args()

    if settings.use_memory_db:
        print('ERROR: USE_MEMORY_DB=true입니다. 실제 Rollout은 Firestore 모드에서만 허용합니다.')
        return 2
    if not settings.firebase_project_id:
        print('ERROR: FIREBASE_PROJECT_ID가 비어 있습니다.')
        return 2
    if not settings.data_go_kr_service_key:
        print('ERROR: DATA_GO_KR_SERVICE_KEY가 비어 있습니다.')
        return 2

    historical_end = a.historical_end or previous_month()
    snapshot_month = a.snapshot_month or historical_end
    regions = _select_scope_regions(a.scope, a.max_regions)
    if a.batch_size < 1:
        print('ERROR: --batch-size는 1 이상이어야 합니다.')
        return 2

    state = load_state(a.scope)
    state.update({
        'scope': a.scope,
        'project_id': settings.firebase_project_id,
        'region_count': len(regions),
        'historical_start': a.historical_start,
        'historical_end': historical_end,
        'snapshot_month': snapshot_month,
        'batch_size': a.batch_size,
    })
    save_state(a.scope, state)

    logs = ROOT / 'logs'
    logs.mkdir(exist_ok=True)
    log_path = logs / f'rollout-{a.scope}.log'
    with log_path.open('a', encoding='utf-8') as log:
        tee = Tee(sys.stdout, log)
        with redirect_stdout(tee), redirect_stderr(tee):
            print('\n' + '=' * 72)
            print('Gyeongnam AI Agent - Checkpoint 2.9 AUTO ROLLOUT')
            print(f'scope           : {a.scope}')
            print(f'project         : {settings.firebase_project_id}')
            print(f'regions         : {len(regions)}')
            print(f'historical      : {a.historical_start} ~ {historical_end}')
            print(f'snapshot month  : {snapshot_month}')
            print(f'batch size      : {a.batch_size}')
            print(f'stage           : {a.stage}')
            print(f'dry-run         : {a.dry_run}')
            print('=' * 72)

            rc = 0
            if a.stage in {'all', 'historical'}:
                hist_rc = run_with_retries(
                    scope=a.scope,
                    stage='historical',
                    start=a.historical_start,
                    end=historical_end,
                    sources=list(CORE_HISTORICAL_SOURCES),
                    regions=regions,
                    batch_size=a.batch_size,
                    resume_file=scope_resume_path(a.scope, 'historical'),
                    max_passes=a.max_passes,
                    retry_wait_seconds=a.retry_wait_seconds,
                    dry_run=a.dry_run,
                )
                state['stages']['historical'] = {
                    'status': 'done' if hist_rc == 0 else ('plan' if a.dry_run else 'incomplete'),
                    'return_code': hist_rc,
                    'updated_at': utcnow_iso(),
                }
                save_state(a.scope, state)
                if hist_rc != 0:
                    print('[AUTO] Historical이 완주하지 못해 다음 단계로 진행하지 않습니다. 같은 명령을 다시 실행하면 resume됩니다.')
                    return hist_rc

            if a.stage in {'all', 'snapshot'}:
                snap_rc = run_with_retries(
                    scope=a.scope,
                    stage='snapshot',
                    start=snapshot_month,
                    end=snapshot_month,
                    sources=list(SNAPSHOT_SOURCES),
                    regions=regions,
                    batch_size=a.batch_size,
                    resume_file=scope_resume_path(a.scope, 'snapshot'),
                    max_passes=a.max_passes,
                    retry_wait_seconds=a.retry_wait_seconds,
                    dry_run=a.dry_run,
                )
                state['stages']['snapshot'] = {
                    'status': 'done' if snap_rc == 0 else ('plan' if a.dry_run else 'incomplete'),
                    'return_code': snap_rc,
                    'updated_at': utcnow_iso(),
                }
                save_state(a.scope, state)
                if snap_rc != 0:
                    print('[AUTO] Snapshot이 완주하지 못했습니다. 같은 명령을 다시 실행하면 resume됩니다.')
                    return snap_rc

            should_index = (a.scope == 'gyeongnam') or a.force_indexes
            if a.stage in {'all', 'indexes'}:
                if a.dry_run:
                    print(f'[AUTO] Index plan: month={snapshot_month}, enabled={should_index}')
                elif should_index:
                    count = recompute_indexes(snapshot_month)
                    print(f'[AUTO] Composite Index 재계산 완료: month={snapshot_month}, rows={count}')
                    state['stages']['indexes'] = {
                        'status': 'done', 'rows': count, 'updated_at': utcnow_iso()
                    }
                    save_state(a.scope, state)
                else:
                    print('[AUTO] 창원 단계에서는 경남 전체 비교가 아니므로 Composite Index를 의도적으로 건너뜁니다.')
                    state['stages']['indexes'] = {
                        'status': 'deferred', 'reason': 'requires_gyeongnam_wide_same_month_population', 'updated_at': utcnow_iso()
                    }
                    save_state(a.scope, state)

            if not a.dry_run:
                report = quality_report()
                summary = {
                    'generated_at': utcnow_iso(),
                    'scope': a.scope,
                    'project_id': settings.firebase_project_id,
                    'region_count_selected': len(regions),
                    'historical_period': [a.historical_start, historical_end],
                    'snapshot_month': snapshot_month,
                    'quality_report': report,
                    'state': state,
                }
                report_path = write_report(a.scope, summary)
                print(f'[AUTO] Rollout summary 저장: {report_path}')
                print('[AUTO] 완료. 같은 명령을 다시 실행해도 resume 파일 때문에 완료 작업은 건너뜁니다.')
            else:
                print('[AUTO] DRY-RUN 완료: API 호출/Firestore 쓰기 없음')
            return rc


if __name__ == '__main__':
    raise SystemExit(main())
