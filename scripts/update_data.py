"""최신 데이터 증분 갱신 진입점.

- daily: 최근 2~3개월 아파트 매매/전월세/기타부동산을 다시 받아 신고 지연·정정을 upsert 반영
- monthly: 주민등록/연령/1인세대/세대원수·출생사망/공동주택/건축물/상권/온비드를 최신 확정월 중심으로 갱신
- all: 위 두 묶음을 모두 실행

소스별 API 명세/키가 아직 설정되지 않은 경우 source_status에 skipped 상태를 기록한다.
KOSIS는 live API가 아니라 검증용 Benchmark import로 분리한다.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import get_store, utcnow_iso
from scripts.pipeline import current_month, month_shift, run_source

DAILY = ['apt_sale', 'apt_rent', 'other_real_estate', 'onbid']
MONTHLY = ['population', 'age_population', 'single_household', 'household_birth_death', 'apartment_basic', 'building_register', 'commerce', 'onbid']
PLANNED = ['kosis']


def _monthly_target() -> str:
    # 주민등록은 월말 집계이므로 당월 초에는 직전월이 가장 안전한 기본값이다.
    return os.getenv('MONTHLY_TARGET_MONTH') or month_shift(current_month(), -1)


def main(scope: str = 'daily') -> int:
    store = get_store()
    if not store.list('regions'):
        print('regions가 비어 있습니다. 먼저: python scripts/bootstrap_regions.py')
        return 2

    results = []
    if scope in ('daily', 'all'):
        recalc = max(1, int(os.getenv('RECENT_REAL_ESTATE_RECALC_MONTHS', '3')))
        # 현재월 포함 최근 N개월. 최근 신고가 계속 보강되므로 같은 문서를 upsert한다.
        months = [month_shift(current_month(), -i) for i in range(recalc)]
        for month in sorted(months):
            for source in DAILY:
                if _missing_config(source):
                    results.append(_skip_row(source,month)); continue
                results.append(run_source(source, month))

    if scope in ('monthly', 'all'):
        month = _monthly_target()
        for source in MONTHLY:
            # 주민등록 3종은 사용자가 활용신청 상세 URL/파라미터 template을 넣은 경우만 실행한다.
            if _missing_config(source):
                results.append(_skip_row(source,month)); continue
            results.append(run_source(source, month))

        for source in PLANNED:
            row = {'source': source, 'month': month, 'status': 'planned_adapter_pending', 'finished_at': utcnow_iso()}
            store.set('source_status', f'{source}_{month}', row, merge=False); results.append(row)

    ok = sum(r.get('status') == 'ok' for r in results)
    errors = [r for r in results if r.get('status') == 'error']
    skipped = len(results) - ok - len(errors)
    print(f'갱신 완료: ok={ok}, error={len(errors)}, skipped/planned={skipped}')
    for r in results:
        print(f"[{r.get('status')}] {r.get('source')} {r.get('month','')} regions={r.get('regions_updated','-')} {r.get('error','')}")
    return 1 if errors else 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--scope', default='daily', choices=['daily', 'monthly', 'all'])
    args = p.parse_args()
    raise SystemExit(main(args.scope))
