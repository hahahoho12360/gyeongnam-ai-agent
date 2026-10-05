"""공식 '전국 법정동' CSV 파일로 경상남도 법정읍·면·동 Master를 생성한다.

공공데이터포털의 파일데이터는 로그인 없이 내려받을 수 있으므로,
법정동코드 OpenAPI 서비스키가 아직 없어도 지역 Master를 준비할 수 있다.

공식 파일 페이지(2026-10 확인):
  https://www.data.go.kr/data/15063424/fileData.do

사용 예:
  python scripts/bootstrap_regions_file.py "국토교통부_전국 법정동_20260630.csv"
  python scripts/bootstrap_regions_file.py legal.csv --dry-run

CSV 인코딩은 utf-8-sig / cp949 / euc-kr 순으로 자동 시도한다.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import get_store


def _first(row: dict, *keys: str):
    for key in keys:
        if key in row and row[key] not in (None, ''):
            return str(row[key]).strip()
    return ''


def read_csv_rows(path: Path) -> list[dict]:
    errors = []
    for encoding in ('utf-8-sig', 'cp949', 'euc-kr', 'utf-8'):
        try:
            with path.open('r', encoding=encoding, newline='') as f:
                rows = list(csv.DictReader(f))
            if rows:
                return rows
        except UnicodeDecodeError as exc:
            errors.append(f'{encoding}: {exc}')
    raise RuntimeError('CSV 인코딩을 판별하지 못했습니다. ' + ' | '.join(errors[-2:]))


def normalize_gyeongnam_regions(rows: Iterable[dict]) -> list[dict]:
    """공식 파일의 현존 법정구역 행을 프로젝트 지역 Master로 변환한다.

    분석단위 원칙:
    - 법정동: 그대로 사용
    - 읍/면: 읍/면 행만 사용하고 그 아래 리 행은 저장하지 않는다(roll-up 대상)
    - 시도/시군구 레벨 행은 제외
    """
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        code = _first(row, '법정동코드', 'region_cd', '지역코드')
        sido = _first(row, '시도명', 'sido_nm', '시도')
        sigungu = _first(row, '시군구명', 'sgg_nm', '시군구')
        umd = _first(row, '읍면동명', '읍면도명', 'umd_nm', '읍면동')
        ri = _first(row, '리명', 'ri_nm', '리')
        created = _first(row, '생성일자', 'adpt_de', '생성일') or None

        if sido != '경상남도' or not code or len(code) != 10:
            continue
        # 시도/시군구 상위 행 및 리 상세행 제외
        if not umd or ri:
            continue
        if not umd.endswith(('읍', '면', '동')):
            continue
        if code in seen:
            continue

        region_type = 'eup_myeon' if umd.endswith(('읍', '면')) else 'legal_dong'
        peer_group = 'rural' if region_type == 'eup_myeon' else 'urban'
        full_name = ' '.join(x for x in (sido, sigungu, umd) if x)
        out.append({
            'id': code,
            'bjd_code': code,
            'name': umd,
            'full_name': full_name,
            'sido': sido,
            'sigungu': sigungu,
            'region_type': region_type,
            'peer_group': peer_group,
            'neighbors': [],
            'valid_from': created,
            'source': 'MOLIT 전국 법정동 파일 / MOIS 행정표준코드 기반',
            'is_demo': False,
        })
        seen.add(code)
    return sorted(out, key=lambda r: (r['sigungu'], r['name'], r['bjd_code']))


def main(path: str, dry_run: bool = False) -> int:
    p = Path(path)
    if not p.exists():
        print(f'파일을 찾을 수 없습니다: {p}')
        return 2
    regions = normalize_gyeongnam_regions(read_csv_rows(p))
    if not regions:
        print('경상남도 법정읍·면·동 행을 찾지 못했습니다. CSV 헤더/내용을 확인하세요.')
        return 3

    print(f'변환 대상: {len(regions)}개 법정읍·면·동')
    print('예시:', regions[0]['full_name'], regions[0]['bjd_code'])
    if dry_run:
        print('dry-run이므로 Firestore/DB에는 저장하지 않았습니다.')
        return 0

    store = get_store()
    for region in regions:
        store.set('regions', region['id'], region, merge=False)
    print(f'regions 컬렉션에 {len(regions)}건 저장 완료')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    raise SystemExit(main(args.csv_path, args.dry_run))
