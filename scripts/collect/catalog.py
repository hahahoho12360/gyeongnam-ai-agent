from __future__ import annotations

"""공식 데이터 소스와 프로젝트 설정 요구사항의 단일 카탈로그.

비밀값은 저장하지 않는다. 이 모듈은 preflight, 문서화, 운영 상태 화면에서
'어떤 소스가 준비됐는지'만 판정하는 데 사용한다.
"""

import os
from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str
    portal_id: str | None
    portal_url: str | None
    cadence: str
    project_mode: str
    required_all: tuple[str, ...] = ()
    required_any: tuple[tuple[str, ...], ...] = ()
    default_endpoint: str | None = None
    notes: str = ''

    def status(self) -> dict:
        missing_all = [name for name in self.required_all if not os.getenv(name)]
        missing_any: list[list[str]] = []
        for group in self.required_any:
            if not any(os.getenv(name) for name in group):
                missing_any.append(list(group))
        configured = not missing_all and not missing_any
        data = asdict(self)
        data.update({
            'configured': configured,
            'missing_all': missing_all,
            'missing_any': missing_any,
        })
        # tuple는 JSON 친화적으로 바꾼다.
        data['required_all'] = list(self.required_all)
        data['required_any'] = [list(x) for x in self.required_any]
        return data


DATA_GO_KEY = ('DATA_GO_KR_SERVICE_KEY',)

SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        'region_master', '행정표준코드 법정동코드', '15077871',
        'https://www.data.go.kr/data/15077871/openapi.do', '수시', 'master',
        required_any=(('DATA_GO_KR_SERVICE_KEY', 'LEGAL_DONG_CSV_PATH'),),
        default_endpoint='https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList',
        notes='경남 법정 읍·면·동 Master 생성. OpenAPI 또는 로그인 없이 받은 전국 법정동 CSV를 사용. 리는 분석단위에서 부모 읍·면으로 roll-up.',
    ),
    SourceSpec(
        'population', '법정동별 주민등록 인구·세대', '15108071',
        'https://www.data.go.kr/data/15108071/openapi.do', '월말 집계', 'monthly_aggregate',
        required_all=DATA_GO_KEY + ('POPULATION_API_URL', 'POPULATION_QUERY_JSON'),
        notes='포털의 업데이트 표기는 실시간이지만 원통계는 매월 말일 집계.',
    ),
    SourceSpec(
        'age_population', '법정동별 성·연령별 주민등록 인구', '15108074',
        'https://www.data.go.kr/data/15108074/openapi.do', '월말 집계', 'monthly_aggregate',
        required_all=DATA_GO_KEY + ('AGE_POPULATION_API_URL', 'AGE_POPULATION_QUERY_JSON'),
    ),
    SourceSpec(
        'single_household', '법정동별 성·연령별 1인세대', '15108085',
        'https://www.data.go.kr/data/15108085/openapi.do', '월말 집계', 'monthly_aggregate',
        required_all=DATA_GO_KEY + ('SINGLE_HOUSEHOLD_API_URL', 'SINGLE_HOUSEHOLD_QUERY_JSON'),
    ),
    SourceSpec(
        'apartment_basic', '공동주택 기본정보', '15058453',
        'https://www.data.go.kr/data/15058453/openapi.do', '변경 시', 'monthly_snapshot',
        required_all=DATA_GO_KEY,
        default_endpoint='https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5',
        notes='현재 상태 API이므로 프로젝트가 월별 snapshot을 직접 축적.',
    ),
    SourceSpec(
        'building_register', '건축HUB 건축물대장', '15134735',
        'https://www.data.go.kr/data/15134735/openapi.do', '월간', 'monthly_aggregate',
        required_all=DATA_GO_KEY,
        default_endpoint='https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo',
    ),
    SourceSpec(
        'apt_sale', '아파트 매매 실거래 상세', '15126468',
        'https://www.data.go.kr/data/15126468/openapi.do', '신고 반영', 'daily_plus_monthly_aggregate',
        required_all=DATA_GO_KEY,
        default_endpoint='https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev',
        notes='최근 2~3개월은 신고지연/정정 때문에 반복 upsert.',
    ),
    SourceSpec(
        'apt_rent', '아파트 전월세 실거래', '15126474',
        'https://www.data.go.kr/data/15126474/openapi.do', '신고·확정일자 반영', 'daily_plus_monthly_aggregate',
        required_all=DATA_GO_KEY,
        default_endpoint='https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent',
    ),
    SourceSpec(
        'commerce', '상가(상권)정보', '15012005',
        'https://www.data.go.kr/data/15012005/openapi.do', '업소 DB 갱신', 'weekly_monthly_snapshot',
        required_all=DATA_GO_KEY,
        default_endpoint='https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong',
        notes='목록 소실을 즉시 폐업으로 단정하지 않는다.',
    ),
    SourceSpec(
        'household_birth_death', '세대원수 + 출생·사망', None,
        'https://jumin.mois.go.kr/', '월말 집계', 'monthly_aggregate',
        required_all=DATA_GO_KEY,
        required_any=(('HOUSEHOLD_SIZE_API_URL', 'BIRTH_DEATH_API_URL', 'BIRTH_API_URL', 'DEATH_API_URL'),),
        notes='행안부 법정동 주민등록 통계 상세기능을 활용. 출생·사망이 별도 API이면 BIRTH_API_URL/DEATH_API_URL을 각각 설정할 수 있다.',
    ),
    SourceSpec(
        'other_real_estate', '연립·단독·상업용 매매', '15126467/15126465/15126463',
        'https://www.data.go.kr/', '신고 반영', 'monthly_aggregate',
        required_all=DATA_GO_KEY,
        notes='프로젝트 기본 URL에 3개 국토부 실거래 endpoint 포함.',
    ),
    SourceSpec(
        'onbid', '온비드 공매 물건/입찰결과', '15157252/15157757',
        'https://www.data.go.kr/data/15157252/openapi.do', '매시간/월간 통계', 'live_plus_monthly_aggregate',
        required_all=DATA_GO_KEY,
        required_any=(('ONBID_PROPERTY_API_URL', 'ONBID_RESULT_API_URL'),),
        notes='법원경매가 아니라 KAMCO 온비드 공매. 필수 코드조건은 승인 Swagger 기준.',
    ),
    SourceSpec(
        'kosis', 'KOSIS 주택형태 Benchmark', None,
        'https://kosis.kr/', '공표주기', 'benchmark',
        notes='실시간 원천이 아닌 검증용 Benchmark. CSV import 방식 지원.',
    ),
)


def source_statuses(keys: Iterable[str] | None = None) -> list[dict]:
    wanted = set(keys) if keys else None
    return [s.status() for s in SOURCES if wanted is None or s.key in wanted]


def source_spec(key: str) -> SourceSpec | None:
    return next((s for s in SOURCES if s.key == key), None)
