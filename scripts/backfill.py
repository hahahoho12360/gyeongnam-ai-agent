"""안전한 Historical / Snapshot Backfill runner.

Checkpoint 2.8부터의 핵심 원칙
------------------------------
1. 지역 범위를 명시하지 않으면 실행하지 않는다. (--region / --sigungu-prefix / --all-regions)
2. 기본 최대 지역 수는 5개다. 더 넓히려면 --max-regions를 사용자가 직접 늘린다.
3. Historical과 Snapshot을 섞어 과거 여러 달에 저장하지 않는다.
4. --batch-size 단위로 지역을 나눠 처리한다.
5. Resume key에 "지역 묶음(scope)"을 포함해 다른 Batch와 완료 이력이 충돌하지 않는다.
6. Backfill 중 Composite Index 재계산은 자동으로 미룬다. 경남 전체 동일월이 준비된 뒤 별도 계산한다.
7. Firestore quota 오류를 감지하면 즉시 멈추고 Resume 파일을 보존한다.

초보자 예시
------------
# 계획만 보기(아무 API/DB 쓰기 없음)
python scripts/backfill.py --start 2025-09 --end 2026-09 --historical-only --sigungu-prefix 4812 --max-regions 5 --batch-size 5 --dry-run-plan

# 창원권 법정지역 5개, 13개월 Historical 시험
python scripts/backfill.py --start 2025-09 --end 2026-09 --historical-only --sigungu-prefix 4812 --max-regions 5 --batch-size 5 --resume-file .backfill-changwon-5.json

# 현재 Snapshot은 반드시 한 달만
python scripts/backfill.py --start 2026-10 --end 2026-10 --snapshot-only --sigungu-prefix 4812 --max-regions 5 --batch-size 5 --resume-file .snapshot-changwon-5.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import get_store
from scripts.pipeline import month_range, run_source

# 과거 특정 월을 공식 API에서 다시 조회할 수 있는 계열
CORE_HISTORICAL_SOURCES = [
    'population',
    'age_population',
    'single_household',
    'apt_sale',
    'apt_rent',
]
OPTIONAL_HISTORICAL_SOURCES = ['household_birth_death', 'other_real_estate']
HISTORICAL_SOURCES = CORE_HISTORICAL_SOURCES + OPTIONAL_HISTORICAL_SOURCES

# "오늘 조회한 현재 상태" 성격이 강한 계열. 과거 여러 달에 복제하지 않는다.
SNAPSHOT_SOURCES = ['apartment_basic', 'building_register', 'commerce']
SPECIAL_SOURCES = ['onbid']
DEFAULT_SOURCES = list(CORE_HISTORICAL_SOURCES)


def _region_code(row: dict[str, Any]) -> str:
    return str(row.get('bjd_code') or row.get('id') or '').strip()


def _load_regions_direct(region_ids: list[str]) -> list[dict[str, Any]]:
    """정확한 문서 ID가 있으면 collection 전체를 읽지 않고 직접 get한다."""
    store = get_store()
    out: list[dict[str, Any]] = []
    for rid in region_ids:
        row = store.get('regions', rid)
        if not row:
            matches = store.filter_eq('regions', 'bjd_code', rid)
            row = matches[0] if matches else None
        if row and not row.get('is_demo'):
            out.append(row)
    return out


def resolve_regions(
    *,
    region_ids: list[str] | None,
    sigungu_prefix: str | None,
    all_regions: bool,
    region_offset: int,
    max_regions: int,
) -> list[dict[str, Any]]:
    """사용자가 명시한 안전 범위 안에서만 regions를 선택한다.

    - --region: 정확한 법정지역코드. 전체 collection scan 없이 직접 읽는다.
    - --sigungu-prefix: bjd_code 접두어. 4812처럼 창원권 구들을 묶어 고를 수 있다.
    - --all-regions: 경남 Master 전체를 명시적으로 허용한다.
    - --region-offset / --max-regions: 작은 묶음부터 단계적으로 확대한다.
    """
    region_ids = [str(x).strip() for x in (region_ids or []) if str(x).strip()]
    if not region_ids and not sigungu_prefix and not all_regions:
        raise ValueError(
            '안전장치: 지역 범위를 지정해야 합니다. '
            '--region 4812313300, --sigungu-prefix 4812, 또는 --all-regions 중 하나를 사용하세요.'
        )
    if region_offset < 0:
        raise ValueError('--region-offset은 0 이상이어야 합니다.')
    if max_regions < 1:
        raise ValueError('--max-regions는 1 이상이어야 합니다. 전체도 명시적인 숫자로 제한하세요.')

    if region_ids:
        rows = _load_regions_direct(region_ids)
    else:
        # sigungu/all 범위 선택은 한 번만 전체 Master를 읽고 이후 Pipeline에서는 ID cache를 사용한다.
        rows = [r for r in get_store().list('regions') if r and not r.get('is_demo')]
        if sigungu_prefix:
            prefix = str(sigungu_prefix).strip()
            rows = [r for r in rows if _region_code(r).startswith(prefix)]

    # 중복 제거 + 결정적 정렬. 동일 명령은 항상 같은 첫 5개/다음 5개를 선택한다.
    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = _region_code(row)
        if code:
            dedup.setdefault(code, row)
    ordered = [dedup[k] for k in sorted(dedup)]
    selected = ordered[region_offset: region_offset + max_regions]
    if not selected:
        raise ValueError('선택된 지역이 0개입니다. 지역 코드/접두어/offset을 확인하세요.')
    return selected


def resolve_sources(
    explicit_sources: list[str] | None,
    *,
    historical_only: bool,
    snapshot_only: bool,
    start: str,
    end: str,
) -> list[str]:
    if historical_only and snapshot_only:
        raise ValueError('--historical-only와 --snapshot-only는 동시에 사용할 수 없습니다.')

    if historical_only:
        sources = explicit_sources or list(CORE_HISTORICAL_SOURCES)
        invalid = [s for s in sources if s not in HISTORICAL_SOURCES]
        if invalid:
            raise ValueError(f'Historical 모드에서 사용할 수 없는 source: {invalid}')
        return sources

    if snapshot_only:
        if start != end:
            raise ValueError(
                'Snapshot은 현재 상태이므로 여러 과거 월에 복제하면 안 됩니다. '
                '--snapshot-only는 --start와 --end를 같은 월로 지정하세요.'
            )
        sources = explicit_sources or list(SNAPSHOT_SOURCES)
        invalid = [s for s in sources if s not in SNAPSHOT_SOURCES]
        if invalid:
            raise ValueError(f'Snapshot 모드에서 사용할 수 없는 source: {invalid}')
        return sources

    sources = explicit_sources or list(DEFAULT_SOURCES)
    # 사용자가 직접 source를 지정했더라도 여러 달에 Snapshot이 섞이는 실수를 막는다.
    if start != end:
        bad = [s for s in sources if s in SNAPSHOT_SOURCES]
        if bad:
            raise ValueError(
                f'여러 달 Backfill에 Snapshot source {bad}가 포함되어 있습니다. '
                '--historical-only를 사용하거나 Snapshot은 한 달만 별도로 실행하세요.'
            )
    return sources


def chunked(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if size < 1:
        raise ValueError('--batch-size는 1 이상이어야 합니다.')
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def scope_token(region_ids: list[str]) -> str:
    raw = ','.join(sorted(region_ids))
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]


def task_key(scope: str, source: str, month: str) -> str:
    return f'{scope}:{source}:{month}'


def _load_resume(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'version': 2, 'done': []}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return {'version': 2, 'done': []}
        data.setdefault('done', [])
        return data
    except Exception:
        return {'version': 2, 'done': []}


def _save_resume(path: Path, done: set[str], *, meta: dict[str, Any]) -> None:
    payload = {'version': 2, 'done': sorted(done), 'meta': meta}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def print_plan(
    *,
    regions: list[dict[str, Any]],
    sources: list[str],
    start: str,
    end: str,
    batch_size: int,
    region_offset: int,
    max_regions: int,
) -> None:
    months = month_range(start, end)
    batches = chunked(regions, batch_size)
    print('\n=== BACKFILL SAFETY PLAN ===')
    print(f'기간          : {start} ~ {end} ({len(months)}개월)')
    print(f'선택 지역 수  : {len(regions)}개 (offset={region_offset}, max={max_regions})')
    print(f'Batch 크기    : {batch_size}개 / 총 {len(batches)} batch')
    print(f'Source        : {", ".join(sources)}')
    print(f'논리 작업 수   : {len(months) * len(sources) * len(batches)} source-month-batch')
    print('선택 지역:')
    for row in regions:
        code = _region_code(row)
        name = row.get('full_name') or row.get('name') or ''
        print(f'  - {code}  {name}')
    print('============================\n')


def main(
    start: str,
    end: str,
    sources: list[str],
    resume_file: str,
    *,
    regions: list[dict[str, Any]],
    batch_size: int,
    dry_run_plan: bool,
) -> int:
    print_plan(
        regions=regions,
        sources=sources,
        start=start,
        end=end,
        batch_size=batch_size,
        region_offset=0,
        max_regions=len(regions),
    )
    if dry_run_plan:
        print('DRY-RUN PLAN: API 호출/Firestore 쓰기를 하지 않았습니다.')
        return 0

    path = Path(resume_file)
    resume = _load_resume(path)
    done = set(str(x) for x in resume.get('done', []))
    failures: list[dict[str, Any]] = []
    batches = chunked(regions, batch_size)

    old_filter_id = os.environ.get('REGION_FILTER_ID')
    old_filter_ids = os.environ.get('REGION_FILTER_IDS')
    old_defer = os.environ.get('DEFER_INDEX_RECOMPUTE')

    # Backfill 중에는 부분 지역만 존재하므로 Composite Index 재계산은 항상 지연한다.
    os.environ['DEFER_INDEX_RECOMPUTE'] = 'true'
    os.environ.pop('REGION_FILTER_ID', None)

    try:
        for batch_no, batch in enumerate(batches, start=1):
            ids = [_region_code(r) for r in batch]
            token = scope_token(ids)
            os.environ['REGION_FILTER_IDS'] = ','.join(ids)
            print(f'\n[BATCH {batch_no}/{len(batches)}] regions={len(ids)} scope={token}')
            for r in batch:
                print(f"  { _region_code(r) }  {r.get('full_name') or r.get('name') or ''}")

            for month in month_range(start, end):
                for source in sources:
                    key = task_key(token, source, month)
                    # Checkpoint 2.7의 단일지역 Pilot resume와 호환한다.
                    legacy_key = f'{source}:{month}'
                    if key in done or (len(ids) == 1 and legacy_key in done):
                        print('[resume skip]', key)
                        continue

                    result = run_source(source, month)
                    result['batch_scope'] = token
                    result['batch_regions'] = ids
                    print(result)
                    if result.get('status') == 'ok':
                        done.add(key)
                        meta = {
                            'start': start,
                            'end': end,
                            'sources': sources,
                            'last_batch_scope': token,
                            'last_batch_regions': ids,
                        }
                        _save_resume(path, done, meta=meta)
                    else:
                        failures.append(result)
                        err = str(result.get('error') or '')
                        if 'ResourceExhausted' in err or 'Quota exceeded' in err:
                            print('\n[quota stop] Firestore 할당량/쿼터 소진 감지. 성공 항목은 resume 파일에 보존되었습니다.')
                            print(f'backfill 중단: done={len(done)}, failures={len(failures)}, resume={path}')
                            return 2

        print(f'backfill 완료: done={len(done)}, failures={len(failures)}, resume={path}')
        return 1 if failures else 0
    finally:
        # 사용자의 기존 PowerShell 환경과 별개로 현재 Python 프로세스에서만 바꾼 값을 복원한다.
        if old_filter_id is None:
            os.environ.pop('REGION_FILTER_ID', None)
        else:
            os.environ['REGION_FILTER_ID'] = old_filter_id
        if old_filter_ids is None:
            os.environ.pop('REGION_FILTER_IDS', None)
        else:
            os.environ['REGION_FILTER_IDS'] = old_filter_ids
        if old_defer is None:
            os.environ.pop('DEFER_INDEX_RECOMPUTE', None)
        else:
            os.environ['DEFER_INDEX_RECOMPUTE'] = old_defer


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='경남 AI Agent 안전 Batch Backfill')
    p.add_argument('--start', default='2022-10')
    p.add_argument('--end', required=True)
    p.add_argument('--source', action='append', dest='sources', help='반복 지정 가능')
    p.add_argument('--historical-only', action='store_true', help='과거 월 재조회가 가능한 Historical source만 실행')
    p.add_argument('--snapshot-only', action='store_true', help='현재 Snapshot source만 실행. start=end 필수')

    region = p.add_argument_group('지역 안전장치')
    region.add_argument('--region', action='append', dest='region_ids', help='정확한 법정지역코드. 반복 지정 가능')
    region.add_argument('--sigungu-prefix', help='법정지역코드 접두어. 예: 4812 = 창원권')
    region.add_argument('--all-regions', action='store_true', help='경남 Master 전체를 명시적으로 선택')
    region.add_argument('--region-offset', type=int, default=0, help='정렬된 후보에서 앞 N개 건너뛰기')
    region.add_argument('--max-regions', type=int, default=5, help='한 명령에서 선택할 최대 지역 수. 기본 5')
    region.add_argument('--batch-size', type=int, default=5, help='한 번에 Pipeline에 노출할 지역 수. 기본 5')

    p.add_argument('--resume-file', default='.backfill-state.json')
    p.add_argument('--dry-run-plan', action='store_true', help='선택 지역/기간/작업량만 보여주고 API/DB 작업은 하지 않음')

    a = p.parse_args()
    try:
        selected_sources = resolve_sources(
            a.sources,
            historical_only=a.historical_only,
            snapshot_only=a.snapshot_only,
            start=a.start,
            end=a.end,
        )
        selected_regions = resolve_regions(
            region_ids=a.region_ids,
            sigungu_prefix=a.sigungu_prefix,
            all_regions=a.all_regions,
            region_offset=a.region_offset,
            max_regions=a.max_regions,
        )
        # 사용자가 지정한 실제 offset/max 정보를 계획 출력에 반영하기 위해 여기서 한 번 별도 출력하지 않고 main으로 전달.
        raise SystemExit(main(
            a.start,
            a.end,
            selected_sources,
            a.resume_file,
            regions=selected_regions,
            batch_size=a.batch_size,
            dry_run_plan=a.dry_run_plan,
        ))
    except ValueError as exc:
        print(f'ERROR: {exc}')
        raise SystemExit(2)
