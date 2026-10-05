"""기능검증용 데모 데이터 3지역 x 48개월 = 144 포인트 생성.
실제 통계가 아니므로 최종 증빙에는 사용하지 않는다.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backend.db import get_store
from backend.demo import seed_demo
if __name__=='__main__':
    n=seed_demo(get_store()); print(f'데모 데이터 생성: {n}건 (이미 있으면 0). 실제 통계 아님.')
