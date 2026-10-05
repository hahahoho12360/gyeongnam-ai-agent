from __future__ import annotations

import calendar
import json
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.db import get_store, utcnow_iso
from backend.indexes import compute_index_rows
from backend.metrics import compute_derived, data_confidence
from scripts.collect.adapters import (
    aggregate_age_rows,
    aggregate_apartment_rent,
    aggregate_apartment_sales,
    aggregate_apartment_basic,
    aggregate_buildings,
    aggregate_commerce,
    aggregate_population_rows,
    aggregate_other_real_estate,
    aggregate_onbid_rows,
    aggregate_single_household_rows,
    aggregate_household_size_rows,
    aggregate_birth_death_rows,
    yyyymm,
)
from scripts.collect.data_go_kr import DataGoKrClient

DEFAULT_ENDPOINTS = {
    # 국토부 상세자료 공식 요청 URL. 환경변수로 언제든 교체 가능하다.
    'apt_sale': 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev',
    'apt_rent': 'https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent',
    'apt_list': 'https://apis.data.go.kr/1613000/AptListService4/getLegaldongAptList4',
    'apartment_basic': 'https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5',
    'building_register': 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo',
    'commerce': 'https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong',
    'rowhouse_sale': 'https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade',
    'single_house_sale': 'https://apis.data.go.kr/1613000/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade',
    'commercial_sale': 'https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade',
}


def month_shift(month: str, delta: int) -> str:
    y, m = map(int, month.split('-'))
    index = y * 12 + (m - 1) + delta
    return f'{index // 12:04d}-{index % 12 + 1:02d}'


def month_range(start: str, end: str) -> list[str]:
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur = month_shift(cur, 1)
    return out


def current_month() -> str:
    now = datetime.now()
    return f'{now.year:04d}-{now.month:02d}'


def month_end(month: str) -> str:
    y, m = map(int, month.split('-'))
    return f'{y:04d}-{m:02d}-{calendar.monthrange(y,m)[1]:02d}'


_REGION_CACHE: dict[str, list[dict[str, Any]]] = {}


def all_regions() -> list[dict[str, Any]]:
    """분석 대상 regions를 반환한다.

    필터 우선순위:
    1) REGION_FILTER_IDS="id1,id2,..."  -> Batch용. 지정 문서만 직접 get 후 프로세스 내 cache
    2) REGION_FILTER_ID="id"           -> 단일 Smoke/Pilot용
    3) 아무 필터 없음                    -> 경남 Master 전체

    Batch 동안 같은 regions를 source마다 다시 Firestore에서 읽지 않도록 현재 Python
    프로세스 안에서 cache한다. 환경변수 문자열이 바뀌면 cache key도 달라져 다음 Batch는
    자동으로 별도 cache를 사용한다.
    """
    store = get_store()
    many = os.getenv('REGION_FILTER_IDS', '').strip()
    one = os.getenv('REGION_FILTER_ID', '').strip()
    cache_key = f'many:{many}' if many else (f'one:{one}' if one else 'all')
    if cache_key in _REGION_CACHE:
        return [dict(r) for r in _REGION_CACHE[cache_key]]

    if many:
        ids = []
        seen = set()
        for raw in many.split(','):
            rid = raw.strip()
            if rid and rid not in seen:
                ids.append(rid); seen.add(rid)
        rows: list[dict[str, Any]] = []
        for rid in ids:
            row = store.get('regions', rid)
            if not row:
                matches = store.filter_eq('regions', 'bjd_code', rid)
                row = matches[0] if matches else None
            if row and not row.get('is_demo'):
                rows.append(row)
        _REGION_CACHE[cache_key] = rows
        return [dict(r) for r in rows]

    if one:
        row = store.get('regions', one)
        if row and not row.get('is_demo'):
            rows = [row]
        else:
            matches = store.filter_eq('regions', 'bjd_code', one)
            rows = [r for r in matches if r and not r.get('is_demo')]
        _REGION_CACHE[cache_key] = rows
        return [dict(r) for r in rows]

    rows = [r for r in store.list('regions') if r and not r.get('is_demo')]
    _REGION_CACHE[cache_key] = rows
    return [dict(r) for r in rows]


def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def upsert_metric_patch(
    region_id: str,
    month: str,
    patch: dict[str, Any],
    *,
    source: str,
    source_as_of: str | None = None,
    provisional: bool = False,
    sample_size: int | None = None,
) -> dict[str, Any]:
    store = get_store()
    doc_id = f'{region_id}_{month}'
    existing = store.get('monthly_data', doc_id) or {
        'region_id': region_id, 'month': month, 'metrics': {}, 'derived': {}, 'indexes': {}, 'freshness': {}
    }
    metrics = _deep_merge(existing.get('metrics', {}), {k: v for k, v in patch.items() if v is not None})

    prev = store.get('monthly_data', f'{region_id}_{month_shift(month,-1)}') or {}
    yearago = store.get('monthly_data', f'{region_id}_{month_shift(month,-12)}') or {}
    derived = compute_derived(metrics, prev.get('metrics', {}), yearago.get('metrics', {}))

    freshness = dict(existing.get('freshness', {}))
    sources = dict(freshness.get('sources', {}))
    sources[source] = {
        'source_as_of': source_as_of or month_end(month),
        'fetched_at': utcnow_iso(),
        'is_provisional': bool(provisional),
        'sample_size': sample_size,
        'data_confidence': data_confidence(sample_size),
    }
    freshness.update({
        'source_as_of': max((x.get('source_as_of') or '') for x in sources.values()),
        'fetched_at': utcnow_iso(),
        'is_provisional': any(bool(x.get('is_provisional')) for x in sources.values()),
        'sample_size': sample_size if sample_size is not None else freshness.get('sample_size'),
        'data_confidence': data_confidence(sample_size) if sample_size is not None else freshness.get('data_confidence', 'unknown'),
        'sources': sources,
        'is_demo': False,
    })
    row = {
        'region_id': region_id,
        'month': month,
        'metrics': metrics,
        'derived': derived,
        'indexes': existing.get('indexes', {}),
        'freshness': freshness,
    }
    saved = store.set('monthly_data', doc_id, row, merge=False)
    latest = store.get('region_latest', region_id)
    if not latest or str(latest.get('month', '')) <= month:
        store.set('region_latest', region_id, row, merge=False)
    return saved


def apply_patches(month: str, source: str, patches: dict[str, dict[str, Any]], *, provisional=False, sample_key: str | None = None, source_as_of: str | None = None) -> int:
    count = 0
    # 잠정/실시간 계열은 '오늘 API에서 확인한 상태'가 기준시점이고, 월말 확정 통계는 해당 월말이 기준시점이다.
    source_as_of = source_as_of or (date.today().isoformat() if provisional else month_end(month))
    for rid, patch in patches.items():
        sample = patch.get(sample_key) if sample_key else None
        upsert_metric_patch(
            rid, month, patch, source=source, source_as_of=source_as_of, provisional=provisional,
            sample_size=int(sample) if isinstance(sample, (int, float)) else None,
        )
        count += 1
    # 단일지역 Pilot에서는 동월 경남 전체 비교가 없으므로 Composite Index 재계산이
    # 의미 없고 Firestore 읽기/쓰기만 늘린다. 필요 시 환경변수로 지연한다.
    defer = os.getenv('DEFER_INDEX_RECOMPUTE', 'false').strip().lower() in {'1','true','yes','on'}
    if not defer:
        recompute_indexes(month)
    return count


def recompute_indexes(month: str) -> int:
    store = get_store()
    rows = store.filter_eq('monthly_data', 'month', month)
    rows = [r for r in rows if not r.get('freshness', {}).get('is_demo')]
    if not rows:
        return 0
    computed = compute_index_rows(rows)
    for row in rows:
        rid = row['region_id']
        indexes = computed.get(rid, {})
        store.update('monthly_data', row['id'], {'indexes': indexes})
        latest = store.get('region_latest', rid)
        if latest and latest.get('month') == month:
            store.update('region_latest', rid, {'indexes': indexes})
    return len(rows)


def _unique_sigungu_codes(regions: list[dict]) -> list[str]:
    return sorted({str(r.get('bjd_code') or r.get('id'))[:5] for r in regions if str(r.get('bjd_code') or r.get('id'))[:5]})


def collect_apt_sale_for_sigungu(month: str, sigungu_code: str) -> dict[str, dict[str, Any]]:
    regions = [r for r in all_regions() if str(r.get('bjd_code') or r.get('id')).startswith(sigungu_code)]
    client = DataGoKrClient(); url = os.getenv('APT_SALE_API_URL') or DEFAULT_ENDPOINTS['apt_sale']
    rows = client.get_all(url, {'LAWD_CD': sigungu_code, 'DEAL_YMD': yyyymm(month)}, json_hint=False)
    return aggregate_apartment_sales(rows, regions, month, sigungu_code)

def collect_apt_sale(month: str) -> dict[str, dict[str, Any]]:
    regions = all_regions(); merged: dict[str, dict[str, Any]] = {}
    for sgg in _unique_sigungu_codes(regions):
        merged.update(collect_apt_sale_for_sigungu(month, sgg))
    return merged

def collect_apt_rent_for_sigungu(month: str, sigungu_code: str) -> dict[str, dict[str, Any]]:
    regions = [r for r in all_regions() if str(r.get('bjd_code') or r.get('id')).startswith(sigungu_code)]
    client = DataGoKrClient(); url = os.getenv('APT_RENT_API_URL') or DEFAULT_ENDPOINTS['apt_rent']
    rows = client.get_all(url, {'LAWD_CD': sigungu_code, 'DEAL_YMD': yyyymm(month)}, json_hint=False)
    return aggregate_apartment_rent(rows, regions, month, sigungu_code)

def collect_apt_rent(month: str) -> dict[str, dict[str, Any]]:
    regions = all_regions(); merged: dict[str, dict[str, Any]] = {}
    for sgg in _unique_sigungu_codes(regions):
        merged.update(collect_apt_rent_for_sigungu(month, sgg))
    return merged


def collect_apartment_basic(month: str) -> dict[str, dict[str, Any]]:
    """현재 공동주택 재고 snapshot. 단지목록 → 경남 단지만 기본정보 조회.

    기본정보 API는 단지코드별 호출이므로 월 1회 이하 실행을 권장한다.
    """
    regions = all_regions(); client = DataGoKrClient()
    list_url = os.getenv('APT_LIST_API_URL') or DEFAULT_ENDPOINTS['apt_list']
    detail_url = os.getenv('APARTMENT_BASIC_API_URL') or DEFAULT_ENDPOINTS['apartment_basic']
    # 현재 공식 Swagger(v4)의 법정동 목록 API는 bjdCode(10자리)를 요구한다.
    # Smoke Test와 본 수집 모두 regions Master의 법정지역코드를 순회한다.
    # 동일 kaptCode가 중복될 수 있으므로 단지코드 기준으로 dedupe한다.
    complexes_by_code: dict[str, dict[str, Any]] = {}
    for region in regions:
        bjd_code = str(region.get('bjd_code') or region.get('id') or '')
        if len(bjd_code) != 10:
            continue
        rows = client.get_all(list_url, {'bjdCode': bjd_code}, page_size=100, json_hint=False)
        for item in rows:
            code = str(item.get('kaptCode') or '')
            if code:
                complexes_by_code.setdefault(code, item)
    all_complexes = list(complexes_by_code.values())
    details=[]
    for item in all_complexes:
        bjd=str(item.get('bjdCode') or '')
        sido=str(item.get('as1') or '')
        if not (bjd.startswith('48') or '경상남도' in sido):
            continue
        code=item.get('kaptCode')
        if not code:
            continue
        payload=client.get(detail_url, {'kaptCode': code}, json_hint=False, add_paging=False)
        rows=client.items(payload)
        if rows:
            row=dict(rows[0])
            # 기본정보 응답에 일부 주소 필드가 비어 있을 경우 목록 값을 보강
            for key in ('bjdCode','as1','as2','as3','as4','kaptCode','kaptName'):
                row.setdefault(key,item.get(key))
            details.append(row)
    return aggregate_apartment_basic(details, regions)


def collect_building_register(month: str) -> dict[str, dict[str, Any]]:
    regions = all_regions(); client = DataGoKrClient()
    url = os.getenv('BUILDING_REGISTER_API_URL') or DEFAULT_ENDPOINTS['building_register']
    merged: dict[str, dict[str, Any]] = {}
    # 법정읍면동별 표제부를 조회. rural ri는 Master에서 이미 읍면으로 roll-up되어 있다.
    for r in regions:
        code = str(r.get('bjd_code') or r.get('id'))
        if len(code) < 10:
            continue
        rows = client.get_all(url, {'sigunguCd': code[:5], 'bjdongCd': code[5:10], '_type': 'json'})
        patch = aggregate_buildings(rows, [r], as_of=date.fromisoformat(month_end(month)), sigungu_code=code[:5]).get(r['id'])
        if patch:
            merged[r['id']] = patch
    return merged


def collect_commerce(month: str) -> dict[str, dict[str, Any]]:
    regions = all_regions(); client = DataGoKrClient()
    url = os.getenv('COMMERCE_API_URL') or DEFAULT_ENDPOINTS['commerce']
    merged: dict[str, dict[str, Any]] = {}
    for sgg in _unique_sigungu_codes(regions):
        rows = client.get_all(url, {'divId': 'signguCd', 'key': sgg, 'type': 'json'}, json_hint=False)
        merged.update(aggregate_commerce(rows, regions, sgg))
    return merged


def collect_other_real_estate(month: str) -> dict[str, dict[str, Any]]:
    regions=all_regions(); client=DataGoKrClient(); merged: dict[str, dict[str, Any]]={}
    specs=(
        ('rowhouse', os.getenv('ROWHOUSE_SALE_API_URL') or DEFAULT_ENDPOINTS['rowhouse_sale']),
        ('single_house', os.getenv('SINGLE_HOUSE_SALE_API_URL') or DEFAULT_ENDPOINTS['single_house_sale']),
        ('commercial', os.getenv('COMMERCIAL_SALE_API_URL') or DEFAULT_ENDPOINTS['commercial_sale']),
    )
    for sgg in _unique_sigungu_codes(regions):
        scoped=[r for r in regions if str(r.get('bjd_code') or r.get('id')).startswith(sgg)]
        for kind,url in specs:
            rows=client.get_all(url, {'LAWD_CD':sgg,'DEAL_YMD':yyyymm(month)}, json_hint=False)
            patches=aggregate_other_real_estate(rows,scoped,kind=kind,sigungu_code=sgg)
            for rid,patch in patches.items():
                merged[rid]={**merged.get(rid,{}),**patch}
    return merged


def _render_template(value: Any, *, region: dict, month: str) -> Any:
    if not isinstance(value, str):
        return value
    code = str(region.get('bjd_code') or region.get('id'))
    return value.format(
        month=month,
        yyyymm=yyyymm(month),
        bjd_code=code,
        sigungu_code=code[:5],
        bjdong_code=code[5:10],
        region_name=region.get('name', ''),
        full_name=region.get('full_name', ''),
    )


def _render_global_query(template: dict[str, Any], month: str) -> dict[str, Any]:
    y,m=map(int,month.split('-')); last=calendar.monthrange(y,m)[1]
    values={'month':month,'yyyymm':yyyymm(month),'start_date':f'{y:04d}{m:02d}01','end_date':f'{y:04d}{m:02d}{last:02d}'}
    out={}
    for k,v in template.items():
        out[k]=v.format(**values) if isinstance(v,str) else v
    return out

def collect_onbid(month: str) -> dict[str, dict[str, Any]]:
    regions=all_regions(); client=DataGoKrClient(); merged: dict[str,dict[str,Any]]={}
    configured=0
    for url_env,query_env,is_result in (
      ('ONBID_PROPERTY_API_URL','ONBID_PROPERTY_QUERY_JSON',False),
      ('ONBID_RESULT_API_URL','ONBID_RESULT_QUERY_JSON',True),
    ):
        url=os.getenv(url_env,'')
        if not url: continue
        configured+=1
        try: template=json.loads(os.getenv(query_env,'{}'))
        except json.JSONDecodeError as e: raise RuntimeError(f'{query_env}는 JSON이어야 합니다.') from e
        if not template: raise RuntimeError(f'{query_env}가 필요합니다. 온비드 활용명세의 필수 검색조건을 넣으세요.')
        rows=client.get_all(url,_render_global_query(template,month),page_size=500)
        patches=aggregate_onbid_rows(rows,regions,result_rows=is_result)
        for rid,patch in patches.items(): merged[rid]={**merged.get(rid,{}),**patch}
    if not configured: raise RuntimeError('ONBID_PROPERTY_API_URL/ONBID_RESULT_API_URL이 설정되지 않았습니다.')
    return merged


def collect_configured_per_region(
    month: str,
    *,
    url_env: str,
    query_env: str,
    adapter: Callable[[list[dict], list[dict], str | None], dict[str, dict[str, Any]]],
    scope_env: str | None = None,
) -> dict[str, dict[str, Any]]:
    """명세가 자주 바뀌는 주민등록 계열을 환경변수 템플릿으로 수집한다.

    기본은 안전한 `region`(분석지역 1곳당 1회)이다. 승인된 Swagger가 시군구 단위 또는
    전역 조회를 허용한다면 `*_QUERY_SCOPE=sigungu|global`로 바꿔 API 호출량을 크게 줄일 수 있다.
    예: POPULATION_QUERY_JSON={"statMonth":"{yyyymm}","bjdCd":"{bjd_code}"}
    """
    url = os.getenv(url_env, '')
    if not url:
        raise RuntimeError(f'{url_env}가 설정되지 않았습니다.')
    try:
        template = json.loads(os.getenv(query_env, '{}'))
    except json.JSONDecodeError as e:
        raise RuntimeError(f'{query_env}는 올바른 JSON이어야 합니다.') from e
    if not template:
        raise RuntimeError(f'{query_env}가 비어 있습니다. docs/PUBLIC_DATA_SETUP.md 예시를 확인하세요.')

    mode = (os.getenv(scope_env, 'region') if scope_env else 'region').strip().lower()
    if mode not in {'region', 'sigungu', 'global'}:
        raise RuntimeError(f'{scope_env or "QUERY_SCOPE"}는 region, sigungu, global 중 하나여야 합니다.')

    regions = all_regions(); client = DataGoKrClient(); out: dict[str, dict[str, Any]] = {}

    if mode == 'global':
        if not regions:
            return out
        representative = regions[0]
        params = {k: _render_template(v, region=representative, month=month) for k, v in template.items()}
        rows = client.get_all(url, params)
        return adapter(rows, regions, None)

    if mode == 'sigungu':
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for region in regions:
            code = str(region.get('bjd_code') or region.get('id'))
            grouped[code[:5]].append(region)
        for sig, scoped in grouped.items():
            representative = scoped[0]
            params = {k: _render_template(v, region=representative, month=month) for k, v in template.items()}
            rows = client.get_all(url, params)
            normalized = adapter(rows, scoped, sig)
            out.update(normalized)
        return out

    for region in regions:
        params = {k: _render_template(v, region=region, month=month) for k, v in template.items()}
        rows = client.get_all(url, params)
        code = str(region.get('bjd_code') or region.get('id'))
        normalized = adapter(rows, [region], code[:5])
        if region['id'] in normalized:
            out[region['id']] = normalized[region['id']]
    return out

def collect_household_birth_death(month: str) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]]={}
    specs=(
      ('HOUSEHOLD_SIZE_API_URL','HOUSEHOLD_SIZE_QUERY_JSON','HOUSEHOLD_SIZE_QUERY_SCOPE',aggregate_household_size_rows),
      # 기관이 출생/사망을 한 응답에 같이 제공하는 경우
      ('BIRTH_DEATH_API_URL','BIRTH_DEATH_QUERY_JSON','BIRTH_DEATH_QUERY_SCOPE',aggregate_birth_death_rows),
      # 기관이 출생과 사망을 별도 상세기능으로 제공하는 경우도 지원
      ('BIRTH_API_URL','BIRTH_QUERY_JSON','BIRTH_QUERY_SCOPE',aggregate_birth_death_rows),
      ('DEATH_API_URL','DEATH_QUERY_JSON','DEATH_QUERY_SCOPE',aggregate_birth_death_rows),
    )
    configured=0
    for url_env,query_env,scope_env,adapter in specs:
        if os.getenv(url_env):
            configured+=1
            patches=collect_configured_per_region(
                month,url_env=url_env,query_env=query_env,scope_env=scope_env,adapter=adapter
            )
            for rid,patch in patches.items():
                merged[rid]={**merged.get(rid,{}),**patch}

    # 출생·사망이 별도 API에서 왔어도 최종 자연증감을 계산한다.
    for patch in merged.values():
        if patch.get('birth_count') is not None and patch.get('death_count') is not None:
            patch['natural_change']=patch['birth_count']-patch['death_count']
    if not configured:
        raise RuntimeError('HOUSEHOLD_SIZE_API_URL, BIRTH_DEATH_API_URL, BIRTH_API_URL, DEATH_API_URL 중 하나가 설정되어야 합니다.')
    return merged


def collect_population(month: str) -> dict[str, dict[str, Any]]:
    return collect_configured_per_region(month, url_env='POPULATION_API_URL', query_env='POPULATION_QUERY_JSON', scope_env='POPULATION_QUERY_SCOPE', adapter=aggregate_population_rows)


def collect_age_population(month: str) -> dict[str, dict[str, Any]]:
    return collect_configured_per_region(month, url_env='AGE_POPULATION_API_URL', query_env='AGE_POPULATION_QUERY_JSON', scope_env='AGE_POPULATION_QUERY_SCOPE', adapter=aggregate_age_rows)


def collect_single_household(month: str) -> dict[str, dict[str, Any]]:
    return collect_configured_per_region(month, url_env='SINGLE_HOUSEHOLD_API_URL', query_env='SINGLE_HOUSEHOLD_QUERY_JSON', scope_env='SINGLE_HOUSEHOLD_QUERY_SCOPE', adapter=aggregate_single_household_rows)


COLLECTORS: dict[str, tuple[Callable[[str], dict[str, dict[str, Any]]], str | None, bool]] = {
    'population': (collect_population, None, False),
    'age_population': (collect_age_population, None, False),
    'single_household': (collect_single_household, None, False),
    'household_birth_death': (collect_household_birth_death, None, False),
    'apartment_basic': (collect_apartment_basic, None, False),
    'building_register': (collect_building_register, None, False),
    'commerce': (collect_commerce, 'business_count', False),
    'apt_sale': (collect_apt_sale, 'sale_count', True),
    'apt_rent': (collect_apt_rent, 'rent_count', True),
    'other_real_estate': (collect_other_real_estate, None, True),
    'onbid': (collect_onbid, 'auction_result_count', True),
}


def run_source(source: str, month: str) -> dict[str, Any]:
    if source not in COLLECTORS:
        return {'source': source, 'month': month, 'status': 'not_implemented'}
    collector, sample_key, provisional_capable = COLLECTORS[source]
    started = utcnow_iso()
    try:
        patches = collector(month)
        # 신고/실시간 계열도 오래된 과거월까지 영원히 잠정치로 표시하지 않는다.
        # 기본은 현재월 포함 최근 N개월만 provisional=true.
        recalc=max(1,int(os.getenv('RECENT_REAL_ESTATE_RECALC_MONTHS','3')))
        recent_floor=month_shift(current_month(),-(recalc-1))
        provisional=bool(provisional_capable and month >= recent_floor)
        snapshot_sources={'apartment_basic','building_register','commerce'}
        explicit_as_of=date.today().isoformat() if source in snapshot_sources else None
        count = apply_patches(month, source, patches, provisional=provisional, sample_key=sample_key, source_as_of=explicit_as_of)
        result = {'source': source, 'month': month, 'status': 'ok', 'regions_updated': count, 'started_at': started, 'finished_at': utcnow_iso()}
    except Exception as exc:
        result = {'source': source, 'month': month, 'status': 'error', 'error': f'{type(exc).__name__}: {exc}', 'started_at': started, 'finished_at': utcnow_iso()}
    get_store().set('source_status', f'{source}_{month}', result, merge=False)
    return result
