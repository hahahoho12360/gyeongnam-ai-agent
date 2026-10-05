"""승인된 공공 API의 실제 응답 필드명을 확인하는 안전한 probe.
서비스키는 출력하지 않는다.
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.collect.data_go_kr import DataGoKrClient
from scripts.pipeline import DEFAULT_ENDPOINTS, yyyymm


def main(source: str, month: str | None, sigungu: str | None, bjdong: str | None = None, sido: str = '48', kapt_code: str | None = None, bjd_code: str | None = None):
    client=DataGoKrClient()
    if source == 'apt_list':
        if not bjd_code:
            raise SystemExit('apt_list probe에는 --bjd-code 10자리 법정동코드가 필요합니다. 예: --bjd-code 4812313300')
        url=os.getenv('APT_LIST_API_URL') or DEFAULT_ENDPOINTS['apt_list']
        payload=client.get(url,{'bjdCode':bjd_code,'pageNo':1,'numOfRows':3},json_hint=False)
    elif source == 'apartment_basic':
        if not kapt_code:
            raise SystemExit('apartment_basic probe에는 --kapt-code가 필요합니다.')
        url=os.getenv('APARTMENT_BASIC_API_URL') or DEFAULT_ENDPOINTS['apartment_basic']
        payload=client.get(url,{'kaptCode':kapt_code},json_hint=False,add_paging=False)
    else:
        if not month or not sigungu:
            raise SystemExit(f'{source} probe에는 --month와 --sigungu가 필요합니다.')
        specs={
          'apt_sale':(os.getenv('APT_SALE_API_URL') or DEFAULT_ENDPOINTS['apt_sale'],{'LAWD_CD':sigungu,'DEAL_YMD':yyyymm(month)},False),
          'apt_rent':(os.getenv('APT_RENT_API_URL') or DEFAULT_ENDPOINTS['apt_rent'],{'LAWD_CD':sigungu,'DEAL_YMD':yyyymm(month)},False),
          'building':(os.getenv('BUILDING_REGISTER_API_URL') or DEFAULT_ENDPOINTS['building_register'],{'sigunguCd':sigungu, **({'bjdongCd': bjdong} if bjdong else {}), '_type':'json'},True),
          'commerce':(os.getenv('COMMERCE_API_URL') or DEFAULT_ENDPOINTS['commerce'],{'divId':'signguCd','key':sigungu,'type':'json'},False),
        }
        if source not in specs: raise SystemExit(f'지원 source: apt_list, apartment_basic, {", ".join(specs)}')
        if source == 'building' and not bjdong:
            raise SystemExit('building probe에는 --bjdong 법정동코드 뒤 5자리가 필요합니다. 예: --bjdong 13300')
        url,params,json_hint=specs[source]
        payload=client.get(url,{**params,'pageNo':1,'numOfRows':3},json_hint=json_hint)
    items=client.items(payload)
    print('source=',source,'rows=',len(items))
    if items:
        print('fields=',sorted(items[0].keys()))
        print(json.dumps(items[0],ensure_ascii=False,indent=2)[:5000])
    else:
        print('item이 없습니다. 조회조건/활용승인/Swagger의 현재 Base URL을 확인하세요.')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--source',required=True); p.add_argument('--month'); p.add_argument('--sigungu'); p.add_argument('--bjdong'); p.add_argument('--sido',default='48'); p.add_argument('--kapt-code'); p.add_argument('--bjd-code')
    a=p.parse_args(); main(a.source,a.month,a.sigungu,a.bjdong,a.sido,a.kapt_code,a.bjd_code)
