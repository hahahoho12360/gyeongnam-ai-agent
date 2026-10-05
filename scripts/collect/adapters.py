from __future__ import annotations

"""공공 API 원자료 → 프로젝트 공통 metric 변환기.

각 기관은 필드 이름과 응답 포맷이 다르므로 여기에서만 기관 의존성을 다룬다.
필드명 변경이 생기면 이 파일의 alias 목록만 조정하면 나머지 FastAPI/Agent 코드는 유지된다.
"""

from collections import Counter, defaultdict
from datetime import date, datetime
from statistics import median
from typing import Any, Iterable
import re


def _clean(value: Any) -> str:
    return '' if value is None else str(value).strip()


def first(row: dict[str, Any], *names: str, default=None):
    for name in names:
        if name in row and row[name] not in (None, ''):
            return row[name]
    return default


def number(value: Any, default=None) -> float | None:
    if value in (None, ''):
        return default
    s = str(value).replace(',', '').replace(' ', '').replace('㎡', '')
    s = re.sub(r'[^0-9.\-]', '', s)
    if s in ('', '-', '.', '-.'):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def integer(value: Any, default=None) -> int | None:
    n = number(value, default=None)
    return int(n) if n is not None else default


def yyyymm(month: str) -> str:
    return month.replace('-', '')[:6]


def region_name_from_row(row: dict[str, Any]) -> str:
    return _clean(first(row, 'stdgNm', 'umdNm', 'umd_nm', '법정동', '법정동명', '읍면동명', '읍면동', 'emdNm', 'dongNm'))


def _region_lookup(regions: list[dict]) -> tuple[dict[tuple[str, str], str], dict[str, list[tuple[str, str]]]]:
    """(5자리 시군구코드, 읍면동명) → region_id와 이름 검색용 index."""
    exact: dict[tuple[str, str], str] = {}
    names: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in regions:
        code = _clean(r.get('bjd_code') or r.get('id'))
        sig = code[:5]
        name = _clean(r.get('name'))
        if sig and name:
            exact[(sig, name)] = r['id']
            names[sig].append((name, r['id']))
    return exact, names


def map_region_id(row: dict[str, Any], regions: list[dict], *, sigungu_code: str | None = None) -> str | None:
    exact, names = _region_lookup(regions)

    # 주민등록 법정동 API처럼 10자리 법정지역코드를 직접 주는 경우를 최우선으로 사용한다.
    stdg = _clean(first(row, 'stdgCd', 'bjdCd', 'bjd_code', '법정동코드'))
    if stdg:
        direct = next((r['id'] for r in regions if _clean(r.get('bjd_code') or r.get('id')) == stdg), None)
        if direct:
            return direct
        # 농촌의 법정리 코드는 Master의 부모 읍·면으로 roll-up한다.
        if len(stdg) == 10 and stdg[-2:] != '00':
            parent = stdg[:8] + '00'
            rolled = next((r['id'] for r in regions if _clean(r.get('bjd_code') or r.get('id')) == parent), None)
            if rolled:
                return rolled

    sig = _clean(first(row, 'sggCd', 'sgg_cd', 'sigunguCd', '시군구코드', default=sigungu_code))[:5]
    if not sig and stdg:
        sig = stdg[:5]
    umd = region_name_from_row(row)
    if sig and umd and (sig, umd) in exact:
        return exact[(sig, umd)]

    # 주소 기반 fallback. 읍·면 roll-up도 주소 문자열에 부모 읍면명이 남으므로 매핑 가능하다.
    address = ' '.join(_clean(first(row, k)) for k in ('lnoAdr', 'rdnmAdr', 'platPlc', '주소', '지번주소', '도로명주소'))
    candidates = names.get(sig, []) if sig else [x for values in names.values() for x in values]
    hits = [(len(name), rid) for name, rid in candidates if name and name in address]
    return max(hits)[1] if hits else None


def aggregate_apartment_sales(rows: Iterable[dict[str, Any]], regions: list[dict], month: str, sigungu_code: str | None = None) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        rid = map_region_id(row, regions, sigungu_code=sigungu_code)
        if rid:
            grouped[rid].append(row)
    out: dict[str, dict[str, Any]] = {}
    for rid, items in grouped.items():
        prices_per_m2: list[float] = []
        deal_amounts: list[float] = []
        areas: list[float] = []
        for x in items:
            amount_10k = number(first(x, 'dealAmount', '거래금액', '거래금액(만원)', '거래금액만원'))
            area = number(first(x, 'excluUseAr', '전용면적', '전용면적(㎡)', '전용면적㎡'))
            if amount_10k is not None:
                won = amount_10k * 10_000
                deal_amounts.append(won)
                if area and area > 0:
                    prices_per_m2.append(won / area)
            if area:
                areas.append(area)
        out[rid] = {
            'sale_count': len(items),
            'sale_total_amount': round(sum(deal_amounts), 2) if deal_amounts else None,
            'sale_median_price': round(median(deal_amounts), 2) if deal_amounts else None,
            'sale_price_per_m2': round(median(prices_per_m2), 2) if prices_per_m2 else None,
            'sale_mean_area_m2': round(sum(areas) / len(areas), 2) if areas else None,
        }
    return out


def aggregate_apartment_rent(rows: Iterable[dict[str, Any]], regions: list[dict], month: str, sigungu_code: str | None = None) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        rid = map_region_id(row, regions, sigungu_code=sigungu_code)
        if rid:
            grouped[rid].append(row)
    out: dict[str, dict[str, Any]] = {}
    for rid, items in grouped.items():
        jeonse_deposits: list[float] = []
        jeonse_per_m2: list[float] = []
        monthly_deposits: list[float] = []
        monthly_rents: list[float] = []
        monthly_count = 0
        for x in items:
            deposit_10k = number(first(x, 'deposit', '보증금액', '보증금', 'depositAmount'))
            rent_10k = number(first(x, 'monthlyRent', '월세금액', '월세', 'monthlyRentAmount'), 0) or 0
            area = number(first(x, 'excluUseAr', '전용면적', '전용면적(㎡)', '전용면적㎡'))
            dep_won = deposit_10k * 10_000 if deposit_10k is not None else None
            rent_won = rent_10k * 10_000
            if rent_10k > 0:
                monthly_count += 1
                if dep_won is not None:
                    monthly_deposits.append(dep_won)
                monthly_rents.append(rent_won)
            elif dep_won is not None:
                jeonse_deposits.append(dep_won)
                if area and area > 0:
                    jeonse_per_m2.append(dep_won / area)
        out[rid] = {
            'rent_count': len(items),
            'jeonse_count': len(items) - monthly_count,
            'monthly_rent_count': monthly_count,
            'jeonse_price': round(median(jeonse_deposits), 2) if jeonse_deposits else None,
            'jeonse_price_per_m2': round(median(jeonse_per_m2), 2) if jeonse_per_m2 else None,
            'monthly_deposit_median': round(median(monthly_deposits), 2) if monthly_deposits else None,
            'monthly_rent_median': round(median(monthly_rents), 2) if monthly_rents else None,
        }
    return out


def _approval_year(row: dict[str, Any]) -> int | None:
    raw = _clean(first(row, 'useAprDay', '사용승인일', '사용승인일자'))
    m = re.search(r'(19|20)\d{2}', raw)
    return int(m.group(0)) if m else None


def aggregate_buildings(rows: Iterable[dict[str, Any]], regions: list[dict], *, as_of: date | None = None, sigungu_code: str | None = None) -> dict[str, dict[str, Any]]:
    as_of = as_of or date.today()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        rid = map_region_id(row, regions, sigungu_code=sigungu_code)
        if rid:
            grouped[rid].append(row)
    out: dict[str, dict[str, Any]] = {}
    for rid, items in grouped.items():
        old30 = 0
        total_area = 0.0
        residential_area = 0.0
        apartment_like = 0
        apartment_units = 0
        for x in items:
            y = _approval_year(x)
            if y and as_of.year - y >= 30:
                old30 += 1
            area = number(first(x, 'totArea', '연면적', 'totalArea'), 0) or 0
            total_area += area
            purpose = _clean(first(x, 'mainPurpsCdNm', '주용도코드명', '주용도명'))
            if any(token in purpose for token in ('주택', '공동주택', '단독주택', '아파트', '연립', '다세대')):
                residential_area += area
            if any(token in purpose for token in ('공동주택', '아파트', '연립', '다세대')):
                apartment_like += 1
            apartment_units += integer(first(x, 'hhldCnt', '세대수', 'householdCount'), 0) or 0
        out[rid] = {
            'building_count': len(items),
            'old_buildings_30y': old30,
            'building_total_area_m2': round(total_area, 2),
            'residential_building_area_m2': round(residential_area, 2),
            'apartment_like_building_count': apartment_like,
            # 건축물대장의 세대수 합은 K-APT 공동주택 세대수 보완용. 최종 apartment_units는 K-APT가 있으면 우선한다.
            'building_register_household_units': apartment_units or None,
        }
    return out


def aggregate_commerce(rows: Iterable[dict[str, Any]], regions: list[dict], sigungu_code: str | None = None) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        rid = map_region_id(row, regions, sigungu_code=sigungu_code)
        if rid:
            grouped[rid].append(row)
    out: dict[str, dict[str, Any]] = {}
    for rid, items in grouped.items():
        categories: Counter[str] = Counter()
        health = education = restaurant = cafe = convenience = 0
        for x in items:
            large = _clean(first(x, 'indsLclsNm', '상권업종대분류명', '업종대분류명')) or '기타'
            middle = _clean(first(x, 'indsMclsNm', '상권업종중분류명', '업종중분류명'))
            small = _clean(first(x, 'indsSclsNm', '상권업종소분류명', '업종소분류명'))
            text = f'{large} {middle} {small}'
            categories[large] += 1
            if any(k in text for k in ('의료', '병원', '의원', '약국', '건강')):
                health += 1
            if any(k in text for k in ('교육', '학원', '교습', '학교')):
                education += 1
            if any(k in text for k in ('음식', '식당', '한식', '외식')):
                restaurant += 1
            if any(k in text for k in ('카페', '커피')):
                cafe += 1
            if '편의점' in text:
                convenience += 1
        out[rid] = {
            'business_count': len(items),
            'business_category_counts': dict(categories),
            'health_business_count': health,
            'education_business_count': education,
            'restaurant_count': restaurant,
            'cafe_count': cafe,
            'convenience_store_count': convenience,
        }
    return out


def aggregate_population_rows(rows: Iterable[dict[str, Any]], regions: list[dict], sigungu_code: str | None = None) -> dict[str, dict[str, Any]]:
    """법정동별 주민등록 인구·세대 API를 지역 월간 합계로 변환한다.

    공식 응답은 lv 값에 따라 법정동 1행 또는 통·반 여러 행으로 올 수 있다.
    어떤 경우에도 같은 분석지역으로 매핑된 행은 인구/세대를 합산하고,
    세대당 인구와 남녀비율은 합계에서 다시 계산한다.
    """
    sums: dict[str, dict[str, int]] = defaultdict(lambda: {
        'population_total': 0, 'households': 0, 'population_male': 0, 'population_female': 0, 'source_row_count': 0
    })
    seen: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        rid = map_region_id(row, regions, sigungu_code=sigungu_code)
        if not rid:
            continue

        # 같은 통·반 행이 페이지/재조회 과정에서 중복되는 경우를 방지할 수 있도록 가능한 식별자를 만든다.
        fingerprint = '|'.join(_clean(first(row, k)) for k in ('statsYm', 'stdgCd', 'admmCd', 'tong', 'ban'))
        if fingerprint.strip('|') and fingerprint in seen[rid]:
            continue
        if fingerprint.strip('|'):
            seen[rid].add(fingerprint)

        pop = integer(first(row, 'totNmprCnt', 'totPpltnCnt', '총인구수', '총인구', 'population'))
        hh = integer(first(row, 'hhCnt', 'totHshldCnt', '세대수', '총세대수', 'households'))
        male = integer(first(row, 'maleNmprCnt', 'malePpltnCnt', '남자인구수', '남자인구'))
        female = integer(first(row, 'femlNmprCnt', 'femlPpltnCnt', '여자인구수', '여자인구'))

        bucket = sums[rid]
        if pop is not None:
            bucket['population_total'] += pop
        if hh is not None:
            bucket['households'] += hh
        if male is not None:
            bucket['population_male'] += male
        if female is not None:
            bucket['population_female'] += female
        bucket['source_row_count'] += 1

    out: dict[str, dict[str, Any]] = {}
    for rid, bucket in sums.items():
        pop = bucket['population_total']
        hh = bucket['households']
        male = bucket['population_male']
        female = bucket['population_female']
        patch: dict[str, Any] = {
            'population_total': pop,
            'households': hh,
            'population_male': male,
            'population_female': female,
            'population_source_rows': bucket['source_row_count'],
        }
        if hh > 0:
            patch['persons_per_household'] = round(pop / hh, 4)
        if female > 0:
            patch['sex_ratio'] = round(male / female, 4)
        out[rid] = patch
    return out

def _age_bucket_value(row: dict[str, Any], lo: int, hi: int) -> int | None:
    """10세 연령구간 값을 읽는다.

    15108074 공식 응답은 ``male0AgeNmprCnt``/``feml0AgeNmprCnt``부터
    ``male90AgeNmprCnt``/``feml90AgeNmprCnt`` 형태를 사용한다.
    다른 상세기능/한글 필드명도 fallback alias로 계속 지원한다.
    """
    total_aliases = [
        f'age{lo}_{hi}', f'age_{lo}_{hi}', f'age{lo}To{hi}', f'cnt{lo}To{hi}',
        f'만{lo}~{hi}세', f'만{lo}_{hi}세', f'{lo}~{hi}세',
        f'만{lo}세~{hi}세', f'{lo}세~{hi}세',
    ]
    direct = integer(first(row, *total_aliases))
    if direct is not None:
        return direct

    male_aliases = [
        f'male{lo}AgeNmprCnt',  # 15108074 공식 필드
        f'maleAge{lo}_{hi}', f'male_age_{lo}_{hi}', f'maleAge{lo}To{hi}',
        f'manAge{lo}_{hi}', f'manAge{lo}To{hi}', f'm{lo}_{hi}',
        f'만{lo}~{hi}세남자', f'만{lo}~{hi}세 남자', f'{lo}~{hi}세남자', f'{lo}~{hi}세 남자',
        f'만{lo}세~{hi}세남자', f'만{lo}세~{hi}세 남자',
    ]
    female_aliases = [
        f'feml{lo}AgeNmprCnt',  # 15108074 공식 필드
        f'femaleAge{lo}_{hi}', f'female_age_{lo}_{hi}', f'femaleAge{lo}To{hi}',
        f'femlAge{lo}_{hi}', f'femlAge{lo}To{hi}', f'f{lo}_{hi}',
        f'만{lo}~{hi}세여자', f'만{lo}~{hi}세 여자', f'{lo}~{hi}세여자', f'{lo}~{hi}세 여자',
        f'만{lo}세~{hi}세여자', f'만{lo}세~{hi}세 여자',
    ]
    male = integer(first(row, *male_aliases))
    female = integer(first(row, *female_aliases))
    if male is None and female is None:
        return None
    return (male or 0) + (female or 0)


def aggregate_age_rows(rows: Iterable[dict[str, Any]], regions: list[dict], sigungu_code: str | None = None) -> dict[str, dict[str, Any]]:
    """15108074 성·연령별 주민등록 자료를 지역 월간 지표로 변환한다.

    공식 Swagger는 남/여 10세 구간(0~9 ... 90~99)과 100세 이상을 제공한다.
    따라서 20~39세와 60세 이상은 정확히 계산할 수 있지만 65세 이상은 직접 계산할 수 없다.
    같은 분석지역으로 여러 행(통·반/리)이 들어오면 모두 합산한다.
    """
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    row_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        rid = map_region_id(row, regions, sigungu_code=sigungu_code)
        if not rid:
            continue
        row_counts[rid] += 1
        for lo in range(0, 100, 10):
            hi = lo + 9
            v = _age_bucket_value(row, lo, hi)
            if v is not None:
                buckets[rid][f'{lo}_{hi}'] += v
        male100 = integer(first(row, 'male100AgeNmprCnt', 'maleAge100Plus', 'manAge100Plus', '만100세이상남자', '만100세 이상 남자'))
        female100 = integer(first(row, 'feml100AgeNmprCnt', 'femaleAge100Plus', 'femlAge100Plus', '만100세이상여자', '만100세 이상 여자'))
        direct100 = integer(first(row, 'age100Plus', 'age_100_plus', '만100세이상', '100세이상', '만100세이상남녀', 'age100AndOver'))
        age100 = direct100 if direct100 is not None else ((male100 or 0) + (female100 or 0) if male100 is not None or female100 is not None else None)
        if age100 is not None:
            buckets[rid]['100_plus'] += age100

    out: dict[str, dict[str, Any]] = {}
    for rid, vals in buckets.items():
        patch: dict[str, Any] = {f'age_{k}': v for k, v in vals.items()}
        patch['age_20_39'] = vals.get('20_29', 0) + vals.get('30_39', 0)
        patch['age_60_plus'] = sum(vals.get(k, 0) for k in ('60_69','70_79','80_89','90_99','100_plus'))
        patch['age_100_plus'] = vals.get('100_plus', 0)
        patch['age_source_rows'] = row_counts[rid]
        # 이 API는 60~69세가 하나의 묶음이므로 65+ 정확값은 만들지 않는다.
        out[rid] = patch
    return out

def _single_hh_age_bucket_value(row: dict[str, Any], lo: int, hi: int) -> int | None:
    """15108085 공식 10세 구간 1인세대 필드(…AgeHhCnt)를 남녀 합산한다."""
    male_aliases = [
        f'male{lo}AgeHhCnt',
        f'만{lo}~{hi}세남자', f'만{lo}~{hi}세 남자', f'{lo}~{hi}세남자', f'{lo}~{hi}세 남자',
    ]
    female_aliases = [
        f'feml{lo}AgeHhCnt',
        f'만{lo}~{hi}세여자', f'만{lo}~{hi}세 여자', f'{lo}~{hi}세여자', f'{lo}~{hi}세 여자',
    ]
    male = integer(first(row, *male_aliases))
    female = integer(first(row, *female_aliases))
    if male is None and female is None:
        return None
    return (male or 0) + (female or 0)


def aggregate_single_household_rows(rows: Iterable[dict[str, Any]], regions: list[dict], sigungu_code: str | None = None) -> dict[str, dict[str, Any]]:
    """15108085 성·연령별 주민등록 1인세대 자료를 지역 월간 지표로 변환한다.

    공식 필드는 totHhCnt/maleHhCnt/femlHhCnt와 남녀 10세 구간 *AgeHhCnt이다.
    lv에 따라 여러 통·반/리가 들어와도 같은 분석지역은 합산한다.
    이 자료는 통계청의 '1인가구'가 아니라 주민등록상의 '1인세대'이므로 UI/문서에서 구분한다.
    """
    sums: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    row_counts: dict[str, int] = defaultdict(int)
    saw_total: set[str] = set()
    saw_male: set[str] = set()
    saw_female: set[str] = set()

    for row in rows:
        rid = map_region_id(row, regions, sigungu_code=sigungu_code)
        if not rid:
            continue
        row_counts[rid] += 1

        total = integer(first(row, 'totHhCnt', 'tot1HshldCnt', '총1인세대수', '총1인세대', 'singleHouseholds'))
        male_total = integer(first(row, 'maleHhCnt', 'male1HshldCnt', '남자세대수', '남자1인세대수'))
        female_total = integer(first(row, 'femlHhCnt', 'feml1HshldCnt', '여자세대수', '여자1인세대수'))
        if total is not None:
            sums[rid]['single_households'] += total
            saw_total.add(rid)
        if male_total is not None:
            sums[rid]['single_male_households'] += male_total
            saw_male.add(rid)
        if female_total is not None:
            sums[rid]['single_female_households'] += female_total
            saw_female.add(rid)

        for lo in range(0, 100, 10):
            hi = lo + 9
            v = _single_hh_age_bucket_value(row, lo, hi)
            if v is not None:
                sums[rid][f'single_age_{lo}_{hi}'] += v

        male100 = integer(first(row, 'male100AgeHhCnt', '만100세이상남자'))
        female100 = integer(first(row, 'feml100AgeHhCnt', '만100세이상여자'))
        if male100 is not None or female100 is not None:
            sums[rid]['single_age_100_plus'] += (male100 or 0) + (female100 or 0)

    out: dict[str, dict[str, Any]] = {}
    for rid, vals in sums.items():
        total = vals.get('single_households') if rid in saw_total else None
        male_total = vals.get('single_male_households') if rid in saw_male else None
        female_total = vals.get('single_female_households') if rid in saw_female else None
        if total is None and (male_total is not None or female_total is not None):
            total = (male_total or 0) + (female_total or 0)

        patch: dict[str, Any] = {
            'single_source_rows': row_counts[rid],
            'single_age_20_39': vals.get('single_age_20_29', 0) + vals.get('single_age_30_39', 0),
            'single_age_60_plus': sum(vals.get(k, 0) for k in (
                'single_age_60_69','single_age_70_79','single_age_80_89','single_age_90_99','single_age_100_plus'
            )),
            'single_age_100_plus': vals.get('single_age_100_plus', 0),
        }
        for lo in range(0, 100, 10):
            key=f'single_age_{lo}_{lo+9}'
            if key in vals:
                patch[key]=vals[key]
        if total is not None:
            patch['single_households'] = total
            patch['one_person_households'] = total
        if male_total is not None:
            patch['single_male_households'] = male_total
        if female_total is not None:
            patch['single_female_households'] = female_total
        out[rid] = patch
    return out

def aggregate_apartment_basic(rows: Iterable[dict[str, Any]], regions: list[dict]) -> dict[str, dict[str, Any]]:
    """K-APT 공동주택 기본정보를 법정읍면동별 현재 재고로 집계한다."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    code_to_region = {str(r.get('bjd_code') or r.get('id')): r['id'] for r in regions}
    for row in rows:
        bjd = _clean(first(row, 'bjdCode', '법정동코드'))
        rid = code_to_region.get(bjd)
        if not rid:
            sig = bjd[:5] if bjd else None
            # 상세정보의 kaptAddr 또는 목록의 읍면동명을 활용
            synthetic = {
                'sggCd': sig,
                'umdNm': first(row, 'as3', '읍면동'),
                'lnoAdr': first(row, 'kaptAddr', '주소'),
            }
            rid = map_region_id(synthetic, regions, sigungu_code=sig)
        if rid:
            grouped[rid].append(row)
    out: dict[str, dict[str, Any]] = {}
    for rid, items in grouped.items():
        units = buildings = 0
        total_area = 0.0
        for x in items:
            units += integer(first(x, 'kaptdaCnt', 'hoCnt', '세대수'), 0) or 0
            buildings += integer(first(x, 'kaptDongCnt', '동수'), 0) or 0
            total_area += number(first(x, 'kaptTarea', '연면적'), 0) or 0
        out[rid] = {
            'apartment_complex_count': len(items),
            'apartment_units': units or None,
            'apartment_building_count': buildings or None,
            'apartment_total_area_m2': round(total_area, 2) if total_area else None,
        }
    return out


def aggregate_other_real_estate(
    rows: Iterable[dict[str, Any]],
    regions: list[dict],
    *,
    kind: str,
    sigungu_code: str | None = None,
) -> dict[str, dict[str, Any]]:
    """연립다세대·단독다가구·상업업무용 거래를 지역별 보조지표로 집계한다."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        rid = map_region_id(row, regions, sigungu_code=sigungu_code)
        if rid:
            grouped[rid].append(row)
    out: dict[str, dict[str, Any]] = {}
    for rid, items in grouped.items():
        patch: dict[str, Any] = {}
        if kind == 'rowhouse':
            patch['rowhouse_sale_count'] = len(items)
        elif kind == 'single_house':
            patch['single_house_sale_count'] = len(items)
        elif kind == 'commercial':
            patch['commercial_transaction_count'] = len(items)
        else:
            patch[f'{kind}_transaction_count'] = len(items)
        out[rid] = patch
    return out


def aggregate_household_size_rows(rows: Iterable[dict[str, Any]], regions: list[dict], sigungu_code: str | None = None) -> dict[str, dict[str, Any]]:
    """세대원수별 세대수. 1~4인과 5인 이상을 공통 지표로 만든다.

    상세 API가 5,6,7,8,9,10+를 나눠 주는 경우 합산하고, 이미 5+ 필드가 있으면 직접값을 쓴다.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        rid=map_region_id(row,regions,sigungu_code=sigungu_code)
        if not rid:
            continue
        one=integer(first(row,'onePersonHouseholds','1인세대수','1인세대','oneHshldCnt'))
        two=integer(first(row,'twoPersonHouseholds','2인세대수','2인세대','twoHshldCnt'))
        three=integer(first(row,'threePersonHouseholds','3인세대수','3인세대','threeHshldCnt'))
        four=integer(first(row,'fourPersonHouseholds','4인세대수','4인세대','fourHshldCnt'))
        fiveplus=integer(first(row,'fivePlusHouseholds','5인이상세대수','5인이상세대','fiveOverHshldCnt'))
        detailed=[]
        if fiveplus is None:
            aliases={
                5:('fivePersonHouseholds','5인세대수','5인세대','fiveHshldCnt'),
                6:('sixPersonHouseholds','6인세대수','6인세대','sixHshldCnt'),
                7:('sevenPersonHouseholds','7인세대수','7인세대','sevenHshldCnt'),
                8:('eightPersonHouseholds','8인세대수','8인세대','eightHshldCnt'),
                9:('ninePersonHouseholds','9인세대수','9인세대','nineHshldCnt'),
                10:('tenPlusPersonHouseholds','10인이상세대수','10인이상세대','tenOverHshldCnt'),
            }
            for names in aliases.values():
                v=integer(first(row,*names))
                if v is not None:
                    detailed.append(v)
            if detailed:
                fiveplus=sum(detailed)
        total=integer(first(row,'totHshldCnt','총세대수','세대수','households'))
        if total is None and any(v is not None for v in (one,two,three,four,fiveplus)):
            total=sum(v or 0 for v in (one,two,three,four,fiveplus))
        patch={k:v for k,v in {
            'households':total,
            'one_person_households':one,'two_person_households':two,'three_person_households':three,
            'four_person_households':four,'five_plus_households':fiveplus,
        }.items() if v is not None}
        if patch:
            out[rid]={**out.get(rid,{}),**patch}
    return out

def aggregate_birth_death_rows(rows: Iterable[dict[str, Any]], regions: list[dict], sigungu_code: str | None = None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]]={}
    for row in rows:
        rid=map_region_id(row,regions,sigungu_code=sigungu_code)
        if not rid: continue
        births=integer(first(row,'birthCount','출생등록자수','출생자수','출생등록'))
        deaths=integer(first(row,'deathCount','사망말소자수','사망자수','사망말소'))
        patch={}
        if births is not None: patch['birth_count']=births
        if deaths is not None: patch['death_count']=deaths
        if births is not None and deaths is not None: patch['natural_change']=births-deaths
        if patch: out[rid]={**out.get(rid,{}),**patch}
    return out


def aggregate_onbid_rows(rows: Iterable[dict[str, Any]], regions: list[dict], *, result_rows: bool=False) -> dict[str, dict[str, Any]]:
    """온비드 물건/입찰결과를 주소 기반으로 법정읍면동에 집계한다.

    차세대 온비드 API별 필드명이 다를 수 있어 대표 alias를 넓게 수용한다. 실제 활용신청 후
    `scripts/probe_api.py` 출력으로 alias를 확인하는 것을 전제로 한다.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        address=first(row,'ldnmAdrs','lndAddr','addr','address','rdnmAdrs','cltrAddr','소재지','주소')
        synthetic={'lnoAdr':address or ''}
        rid=map_region_id(synthetic,regions)
        if rid: grouped[rid].append(row)
    out={}
    for rid,items in grouped.items():
        if not result_rows:
            appraisal=[]; minimum=[]
            for x in items:
                a=number(first(x,'apslAmt','apprAmt','감정평가금액','감정가'))
                m=number(first(x,'minBidPrc','minBidAmt','최저입찰금액','최저입찰가'))
                if a is not None: appraisal.append(a)
                if m is not None: minimum.append(m)
            out[rid]={
              'auction_listing_count':len(items),
              'auction_appraisal_median':round(median(appraisal),2) if appraisal else None,
              'auction_min_bid_median':round(median(minimum),2) if minimum else None,
            }
        else:
            successful=failed=0; ratios=[]
            for x in items:
                status=_clean(first(x,'bidRsltNm','resultNm','입찰결과','결과'))
                if any(k in status for k in ('낙찰','매각')): successful+=1
                if any(k in status for k in ('유찰','무응찰')): failed+=1
                win=number(first(x,'scsbidPrc','winningPrice','낙찰가격','낙찰가'))
                app=number(first(x,'apslAmt','apprAmt','감정평가금액','감정가'))
                if win is not None and app not in (None,0): ratios.append(win/app*100)
            out[rid]={
              'auction_result_count':len(items),
              'auction_success_count':successful,
              'auction_failed_count':failed,
              'auction_award_price_ratio':round(median(ratios),2) if ratios else None,
            }
    return out
