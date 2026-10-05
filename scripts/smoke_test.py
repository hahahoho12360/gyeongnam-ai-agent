from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트에서 실행하지 않아도 .env를 찾을 수 있게 한다.
ROOT = Path(__file__).resolve().parents[1]
# scripts/smoke_test.py를 파일 경로로 직접 실행해도 프로젝트 루트의 backend/scripts 패키지를 찾도록 한다.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')

# 중요: backend.config / pipeline import 전에 환경변수를 읽을 준비를 끝낸다.
from backend.config import settings
from backend.db import get_store, utcnow_iso
from backend.metrics import compute_derived
from scripts import pipeline

CORE_SOURCES = [
    'population',
    'age_population',
    'single_household',
    'apartment_basic',
    'apt_sale',
    'apt_rent',
    'building_register',
    'commerce',
]

SNAPSHOT_SOURCES = {'apartment_basic', 'building_register', 'commerce'}
RECENT_EVENT_SOURCES = {'apt_sale', 'apt_rent'}

REQUIRED_KEYS = {
    'population': ['population_total', 'households'],
    'age_population': ['age_20_39', 'age_60_plus'],
    'single_household': ['single_households'],
    'apartment_basic': ['apartment_complex_count', 'apartment_units'],
    'apt_sale': ['sale_count'],
    'apt_rent': ['rent_count'],
    'building_register': ['building_count'],
    'commerce': ['business_count'],
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='단일 법정지역 × 단일 월 필수 8종 End-to-End Smoke Test'
    )
    p.add_argument('--month', required=True, help='YYYY-MM, 예: 2026-09')
    p.add_argument('--region', required=True, help='10자리 법정지역코드, 예: 4812313300')
    p.add_argument(
        '--write', action='store_true',
        help='검증 결과를 실제 Firestore monthly_data/region_latest에 1건 저장. 기본은 dry-run.'
    )
    p.add_argument(
        '--cleanup', action='store_true',
        help='이 스크립트가 저장한 Smoke Test 문서만 안전하게 삭제.'
    )
    return p.parse_args()


def _print_json(title: str, payload: dict) -> None:
    print(f'\n[{title}]')
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _cleanup(region_id: str, month: str) -> int:
    store = get_store()
    doc_id = f'{region_id}_{month}'
    row = store.get('monthly_data', doc_id)
    if not row:
        print(f'cleanup: monthly_data/{doc_id} 문서가 없습니다.')
        return 0
    if not row.get('freshness', {}).get('smoke_test'):
        raise RuntimeError(
            f'monthly_data/{doc_id}는 smoke_test 표시가 없어 삭제하지 않습니다. '
            '실데이터 보호를 위한 안전장치입니다.'
        )
    store.delete('monthly_data', doc_id)
    latest = store.get('region_latest', region_id)
    if latest and latest.get('freshness', {}).get('smoke_test') and latest.get('month') == month:
        store.delete('region_latest', region_id)
    print(f'cleanup 완료: monthly_data/{doc_id}')
    return 0


def main() -> int:
    args = parse_args()
    if len(args.region) != 10 or not args.region.isdigit():
        raise SystemExit('--region은 10자리 숫자 법정지역코드여야 합니다.')
    if len(args.month) != 7 or args.month[4] != '-':
        raise SystemExit('--month는 YYYY-MM 형식이어야 합니다.')

    if settings.use_memory_db:
        raise SystemExit(
            'USE_MEMORY_DB=true 입니다. 실제 Firestore Smoke Test는 .env에서 '
            'USE_MEMORY_DB=false, DEMO_SEED_ON_START=false로 바꾼 뒤 실행하세요.'
        )

    store = get_store()
    region = store.get('regions', args.region)
    if not region:
        raise SystemExit(f'regions/{args.region}를 Firestore에서 찾지 못했습니다.')

    if args.cleanup:
        return _cleanup(args.region, args.month)

    # 이 Python 프로세스에서만 all_regions()가 대상 지역 1곳을 반환하게 한다.
    # shell이나 .env에는 남지 않는다.
    os.environ['REGION_FILTER_ID'] = args.region

    print('=' * 72)
    print('Gyeongnam AI Agent - Dedicated Smoke Test')
    print(f"region : {region.get('full_name') or region.get('name')} ({args.region})")
    print(f'month  : {args.month}')
    print(f'mode   : {"WRITE → Firestore" if args.write else "DRY-RUN → Firestore 미기록"}')
    print('=' * 72)

    combined_metrics: dict = {}
    source_results: dict[str, dict] = {}
    patches_by_source: dict[str, dict] = {}
    failures = 0

    for source in CORE_SOURCES:
        collector, sample_key, _ = pipeline.COLLECTORS[source]
        print(f'\n>>> {source}: 수집 시작')
        try:
            patches = collector(args.month)
            patch = patches.get(args.region)
            if patch is None:
                source_results[source] = {'status': 'no_data', 'keys': []}
                print(f'    WARNING: {args.region}에 매핑된 데이터가 없습니다.')
                failures += 1
                continue

            patches_by_source[source] = patch
            combined_metrics.update({k: v for k, v in patch.items() if v is not None})
            missing = [k for k in REQUIRED_KEYS[source] if patch.get(k) is None]
            source_results[source] = {
                'status': 'ok' if not missing else 'warning',
                'keys': sorted(patch.keys()),
                'required_missing': missing,
                'sample_size': patch.get(sample_key) if sample_key else None,
            }
            if missing:
                failures += 1
                print(f'    WARNING: 필수 지표 누락 {missing}')
            else:
                print(f'    OK: {len(patch)}개 지표')
        except Exception as exc:
            source_results[source] = {
                'status': 'error',
                'error': f'{type(exc).__name__}: {exc}',
            }
            failures += 1
            print(f'    ERROR: {type(exc).__name__}: {exc}')

    # 이전월/전년동월이 아직 없을 수 있으므로 있으면 사용하고 없으면 None 기반으로 계산한다.
    prev = store.get('monthly_data', f'{args.region}_{pipeline.month_shift(args.month, -1)}') or {}
    yearago = store.get('monthly_data', f'{args.region}_{pipeline.month_shift(args.month, -12)}') or {}
    derived = compute_derived(combined_metrics, prev.get('metrics', {}), yearago.get('metrics', {}))

    print('\n' + '-' * 72)
    print('SOURCE CHECK')
    for source in CORE_SOURCES:
        r = source_results.get(source, {})
        print(f'{source:22s} : {r.get("status", "unknown")}')
    print('-' * 72)

    preview = {
        'region_id': args.region,
        'region_name': region.get('full_name') or region.get('name'),
        'month': args.month,
        'metrics': combined_metrics,
        'derived': derived,
        # Composite Index는 경남 전체 동월 분포가 있어야 의미가 있으므로 Smoke Test에서 계산하지 않는다.
        'indexes': {},
        'smoke_test_note': 'Composite Index intentionally skipped: requires Gyeongnam-wide same-month population.',
    }
    _print_json('INTEGRATED PREVIEW', preview)

    if failures:
        print(f'\nSmoke Test 경고/오류: {failures}개 source. --write는 실행하지 않습니다.')
        return 2

    if not args.write:
        print('\nDRY-RUN 성공: 실제 Firestore monthly_data에는 아직 쓰지 않았습니다.')
        print('다음: 같은 명령에 --write를 붙여 1건만 실제 저장하세요.')
        return 0

    doc_id = f'{args.region}_{args.month}'
    existing = store.get('monthly_data', doc_id)
    if existing and not existing.get('freshness', {}).get('smoke_test'):
        raise RuntimeError(
            f'monthly_data/{doc_id}에 기존 실데이터가 있어 덮어쓰지 않습니다. '
            'Smoke Test는 다른 월/지역을 사용하거나 기존 데이터를 먼저 확인하세요.'
        )

    # 실제 운영과 같은 upsert 경로를 사용하되 Composite Index는 단일지역에서 계산하지 않는다.
    for source in CORE_SOURCES:
        patch = patches_by_source[source]
        sample_key = pipeline.COLLECTORS[source][1]
        sample = patch.get(sample_key) if sample_key else None
        # Snapshot은 현재 상태를 과거월 문서에 시험 연결하는 것이므로 fetched date를 기준시점으로 표시한다.
        provisional = source in SNAPSHOT_SOURCES or source in RECENT_EVENT_SOURCES
        pipeline.upsert_metric_patch(
            args.region,
            args.month,
            patch,
            source=source,
            source_as_of=date.today().isoformat() if provisional else pipeline.month_end(args.month),
            provisional=provisional,
            sample_size=int(sample) if isinstance(sample, (int, float)) else None,
        )

    final = store.get('monthly_data', doc_id) or {}
    freshness = dict(final.get('freshness', {}))
    freshness.update({
        'smoke_test': True,
        'smoke_test_at': utcnow_iso(),
        'smoke_test_region': args.region,
        'smoke_test_month': args.month,
    })
    final['freshness'] = freshness
    # 1지역만으로 percentile Composite Index를 만들면 모두 50점 근처가 되어 의미가 없다.
    final['indexes'] = {}
    store.set('monthly_data', doc_id, {k: v for k, v in final.items() if k != 'id'}, merge=False)

    latest = store.get('region_latest', args.region)
    if latest and latest.get('month') == args.month:
        latest['freshness'] = freshness
        latest['indexes'] = {}
        store.set('region_latest', args.region, {k: v for k, v in latest.items() if k != 'id'}, merge=False)

    saved = store.get('monthly_data', doc_id) or {}
    print(f'\nWRITE 성공: Firestore monthly_data/{doc_id}')
    print('중요: 이 문서는 smoke_test=true로 표시되었습니다.')
    print('검증 후 삭제하려면:')
    print(f'python scripts/smoke_test.py --month {args.month} --region {args.region} --cleanup')
    _print_json('FIRESTORE SAVED', saved)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\n사용자가 중단했습니다.')
        sys.exit(130)
