"""KOSIS benchmark CSV import.

KOSIS의 읍면동/시군구 주택·가구 통계는 공표 주기와 공간 해상도가 월간 API와 다르므로
실시간 monthly_data에 억지로 섞지 않고 `benchmarks` 컬렉션에 별도 저장한다.

CSV 최소 열:
  region_key, period, metric, value
region_key는 프로젝트 region_id/10자리 법정동코드 또는 시군구명을 사용할 수 있다.
"""
from __future__ import annotations
import argparse,csv,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backend.db import get_store,utcnow_iso


def main(path: str) -> int:
    store=get_store(); count=0
    with open(path,encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            key=(row.get('region_key') or '').strip(); period=(row.get('period') or '').strip(); metric=(row.get('metric') or '').strip()
            if not key or not period or not metric: continue
            raw=(row.get('value') or '').replace(',','').strip()
            try: value=float(raw)
            except ValueError: value=raw
            doc_id=f"{key}_{period}_{metric}".replace('/','_').replace(' ','_')
            store.set('benchmarks',doc_id,{'region_key':key,'period':period,'metric':metric,'value':value,'source':'KOSIS','imported_at':utcnow_iso()},merge=False); count+=1
    print(f'KOSIS benchmark {count}건 import 완료')
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('csv_path'); a=p.parse_args(); raise SystemExit(main(a.csv_path))
