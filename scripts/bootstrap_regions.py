"""행정안전부 법정동코드 API에서 경상남도 법정읍·면·동 Master를 생성한다.

사전조건:
- 공공데이터포털 '행정안전부_행정표준코드_법정동코드' 활용신청
- DATA_GO_KR_SERVICE_KEY 설정
- 실제 Firestore 적재 시 USE_MEMORY_DB=false

공식 요청주소: https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList

중요:
`locatadd_nm=경상남도`를 넘기면 API가 '경상남도' 상위행만 반환할 수 있다.
따라서 전체 법정동코드를 페이지네이션으로 받은 뒤 sido_cd=48(경상남도)로
로컬 필터링한다.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from backend.db import get_store  # noqa: E402

URL = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"
PAGE_SIZE = 1000
GYEONGNAM_SIDO_CD = "48"


def _extract(payload: dict) -> tuple[list[dict], int]:
    """행안부 StanReginCd JSON의 rows와 totalCount를 추출한다."""
    if not isinstance(payload, dict):
        return [], 0

    blocks = payload.get("StanReginCd")
    if isinstance(blocks, list):
        total = 0
        rows: list[dict] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            head = block.get("head")
            if isinstance(head, list) and head:
                try:
                    total = int(head[0].get("totalCount") or total or 0)
                except (TypeError, ValueError, AttributeError):
                    pass
            block_rows = block.get("row")
            if isinstance(block_rows, list):
                rows.extend(x for x in block_rows if isinstance(x, dict))
            elif isinstance(block_rows, dict):
                rows.append(block_rows)
        return rows, total

    # 공공데이터포털 공통형 fallback
    response = payload.get("response") or {}
    body = response.get("body") or {}
    total = int(body.get("totalCount") or 0)
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    return (items if isinstance(items, list) else []), total


def _fetch_all(key: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    total = None

    while True:
        params = {
            "ServiceKey": key,
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
            "type": "json",
        }
        r = requests.get(URL, params=params, timeout=60)
        r.raise_for_status()
        payload = r.json()
        page_rows, reported_total = _extract(payload)

        if total is None:
            total = reported_total
            if total:
                print(f"법정동코드 전체 {total:,}건 조회 시작 (페이지당 {PAGE_SIZE}건)")

        rows.extend(page_rows)
        print(f"  page {page}: {len(page_rows):,}건 / 누적 {len(rows):,}건")

        if not page_rows:
            break
        if total and len(rows) >= total:
            break
        if len(page_rows) < PAGE_SIZE and not total:
            break

        page += 1
        if page > 100:  # 안전장치
            raise RuntimeError("법정동코드 페이지 수가 비정상적으로 많습니다. API 응답을 확인하세요.")

    return rows


def _is_gyeongnam_eup_myeon_dong(x: dict) -> bool:
    sido_cd = str(x.get("sido_cd") or "").strip()
    full = str(x.get("locatadd_nm") or "").strip()
    umd = str(x.get("umd_cd") or "").strip()
    ri = str(x.get("ri_cd") or "").strip()
    name = str(x.get("locallow_nm") or "").strip()

    is_gyeongnam = sido_cd == GYEONGNAM_SIDO_CD or full == "경상남도" or full.startswith("경상남도 ")
    if not is_gyeongnam:
        return False

    # 시도/시군구 상위행 제외, 리(里) 하위행 제외
    if umd in ("", "000"):
        return False
    if ri not in ("", "00", "000"):
        return False
    if not name.endswith(("읍", "면", "동")):
        return False
    return True


def main():
    csv_path = os.getenv("LEGAL_DONG_CSV_PATH", "").strip()
    if csv_path:
        from scripts.bootstrap_regions_file import main as file_main

        return file_main(csv_path, False)

    key = os.getenv("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not key:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY 또는 LEGAL_DONG_CSV_PATH가 필요합니다.")

    rows = _fetch_all(key)
    print(f"전체 법정동코드 수신 완료: {len(rows):,}건")

    selected = [x for x in rows if _is_gyeongnam_eup_myeon_dong(x)]
    print(f"경상남도 법정읍·면·동 후보: {len(selected):,}건")

    if not selected:
        # 진단용 샘플만 출력. 서비스키 등 비밀정보는 없음.
        gn_sample = [x for x in rows if str(x.get("sido_cd") or "") == GYEONGNAM_SIDO_CD][:5]
        print("경남 후보가 0건입니다. sido_cd=48 샘플:")
        for x in gn_sample:
            print({k: x.get(k) for k in ("region_cd", "sido_cd", "sgg_cd", "umd_cd", "ri_cd", "locatadd_nm", "locallow_nm")})
        raise SystemExit(2)

    store = get_store()
    count = 0
    for x in selected:
        code = str(x.get("region_cd") or "").strip()
        name = str(x.get("locallow_nm") or "").strip()
        full = str(x.get("locatadd_nm") or "").strip()
        if not code or not name:
            continue

        parts = full.split()
        sigungu = " ".join(parts[1:-1]) if len(parts) >= 3 else (parts[1] if len(parts) > 1 else "")
        peer = "rural" if name.endswith(("읍", "면")) else "urban"

        doc = {
            "id": code,
            "bjd_code": code,
            "name": name,
            "full_name": full,
            "sido": "경상남도",
            "sigungu": sigungu,
            "region_type": "eup_myeon" if peer == "rural" else "legal_dong",
            "peer_group": peer,
            "neighbors": [],
            "valid_from": x.get("adpt_de"),
            "source": "MOIS StanReginCd",
            "is_demo": False,
        }
        store.set("regions", code, doc, merge=False)
        count += 1

    print(f"경상남도 법정읍면동 Master {count:,}건 저장 완료")
    print("다음 단계: Firebase Console > Firestore Database > regions 컬렉션을 확인하세요.")


if __name__ == "__main__":
    main()
