"""환경변수형 OpenAPI(주민등록/확장/온비드)의 실제 승인 명세를 안전하게 시험한다.

서비스키는 출력하지 않는다. 응답 첫 행의 필드명과 최대 1개 샘플만 보여준다.

예:
  python scripts/probe_configured_api.py --source population --month 2026-09 --bjd-code 4812310100
  python scripts/probe_configured_api.py --source onbid_result --month 2026-09 --bjd-code 4812310100
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT/'.env')

from scripts.collect.data_go_kr import DataGoKrClient

SPECS={
    'population':('POPULATION_API_URL','POPULATION_QUERY_JSON'),
    'age_population':('AGE_POPULATION_API_URL','AGE_POPULATION_QUERY_JSON'),
    'single_household':('SINGLE_HOUSEHOLD_API_URL','SINGLE_HOUSEHOLD_QUERY_JSON'),
    'household_size':('HOUSEHOLD_SIZE_API_URL','HOUSEHOLD_SIZE_QUERY_JSON'),
    'birth_death':('BIRTH_DEATH_API_URL','BIRTH_DEATH_QUERY_JSON'),
    'birth':('BIRTH_API_URL','BIRTH_QUERY_JSON'),
    'death':('DEATH_API_URL','DEATH_QUERY_JSON'),
    'onbid_result':('ONBID_RESULT_API_URL','ONBID_RESULT_QUERY_JSON'),
    'onbid_property':('ONBID_PROPERTY_API_URL','ONBID_PROPERTY_QUERY_JSON'),
}


def render(template:dict,month:str,bjd_code:str)->dict:
    y,m=map(int,month.split('-')); last=calendar.monthrange(y,m)[1]
    values={
        'month':month,'yyyymm':f'{y:04d}{m:02d}','bjd_code':bjd_code,
        'sigungu_code':bjd_code[:5],'bjdong_code':bjd_code[5:10],
        'region_name':'','full_name':'',
        'start_date':f'{y:04d}{m:02d}01','end_date':f'{y:04d}{m:02d}{last:02d}',
    }
    out={}
    for k,v in template.items():
        out[k]=v.format(**values) if isinstance(v,str) else v
    return out


def main(source:str,month:str,bjd_code:str)->int:
    if source not in SPECS:
        print('지원 source:',', '.join(SPECS)); return 2
    url_env,query_env=SPECS[source]
    url=os.getenv(url_env,'').strip(); raw=os.getenv(query_env,'{}').strip()
    if not url:
        print(f'{url_env} 미설정'); return 3
    try: template=json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f'{query_env} JSON 오류: {exc}'); return 4
    if not template:
        print(f'{query_env}가 비어 있습니다. 승인 Swagger의 필수 파라미터를 입력하세요.'); return 5
    params=render(template,month,bjd_code)
    # 파라미터 이름만 출력하고 값은 출력하지 않아 주소/코드/검색조건 노출을 줄인다.
    print('source=',source)
    print('query parameter names=',sorted(params.keys()))
    client=DataGoKrClient()
    payload=client.get(url,{**params,'pageNo':1,'numOfRows':3})
    rows=client.items(payload)
    print('rows=',len(rows))
    if rows:
        print('fields=',sorted(rows[0].keys()))
        # 필드 매핑 검증을 위한 1행. 공공 통계 레코드이며 Secret/URL은 포함하지 않는다.
        print(json.dumps(rows[0],ensure_ascii=False,indent=2)[:6000])
    else:
        print('item이 없습니다. 승인상태/검색코드/날짜/필수 파라미터를 확인하세요.')
    return 0

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',required=True,choices=sorted(SPECS))
    ap.add_argument('--month',required=True)
    ap.add_argument('--bjd-code',required=True)
    a=ap.parse_args()
    raise SystemExit(main(a.source,a.month,a.bjd_code))
