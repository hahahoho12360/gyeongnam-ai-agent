# 데이터·지수 정의

제출 범위는 창원204개 법정읍·면·동, 인구 기간2022-10~2026-09이다. 이 문서는 현재 구현만 설명하며 확장 예정 API를 실제 수집자료로 표시하지 않는다.

## 승인받은 11개 API와 저장 소스 연결

| 승인 API | 프로젝트 소스·역할 |
|---|---|
| 공동주택 단지 목록 | apartment_basic 목록→단지 기본정보 연결 |
| 아파트 매매 실거래가 | apt_sale 대체 경로. 상세 거래와 중복 합산하지 않음 |
| 행정표준코드 법정동코드 | regions 공식 지역 Master |
| 상가(상권)정보 | commerce 현재 업소 스냅샷 |
| 아파트 전월세 실거래가 | apt_rent 월별 집계 |
| 아파트 매매 상세 자료 | apt_sale 기본 수집 경로 |
| 건축HUB 건축물대장 | building_register 현재 스냅샷 |
| 공동주택 기본정보 | apartment_basic 목록 코드로 상세 조회 |
| 성·연령별 1인세대 | single_household 월별 집계 |
| 성·연령별 인구 | age_population 월별 집계 |
| 주민등록 인구·세대 | population 월별 집계 |

승인 API11개는 저장 소스11개를 뜻하지 않는다. 인구3개, 비인구5개, 지역Master로 연결한다. 출생·사망/세대원수, 연립·단독·상업용 거래, 온비드, KOSIS 주택형태는 제출 화면에서 제외한 별도 확장 항목이다.

## 저장 구조와 결측

| 컬렉션 | 역할 |
|---|---|
| regions | 법정코드·명칭·구·분석지역 |
| monthly_data | `<지역코드>_<YYYY-MM>` 월별 metrics/derived/indexes/freshness/index_meta |
| region_latest | 최신 조회용 문서. monthly_data의 최신월과 대조 |
| data | 개인 날짜·지역·항목·값·메모·owner_uid |
| conversations | 개인 messages·분석지역·도구기록·owner_uid |
| source_status / rollout·repair 작업 컬렉션 | 수집·완료·재개 기록. 개인 자료와 구분 |

시계열은 주민등록·거래를 지역×월로 집계한다. 읍·면은 하위 법정리 응답을 부모로 합산한다. 대용량 원시 이벤트 전체를 Firestore에 보존하지 않는다. 진단 원본은 키 제거 후 Actions artifact 등에 별도 보존한다.

`stored`는 유효 집계 저장, `no_data`는 정상 조회를 끝냈지만 자료 없음, 미조회/오류는 별도다. 결측을0으로 대체하지 않는다. 홈페이지 ‘유효193/204’는 사용 가능한 값의 수이며 나머지11곳을0명으로 확정한 것이 아니다.

## 주요 값

| 표시 | 정의 |
|---|---|
| 주민등록 인구 | 법정지역의 해당월 주민등록 인구. 행정동/생활권 인구와 구분 |
| 청년 비율 | age_20_39 / population_total ×100. 분자 결측/분모0이면 미산출 |
| 1인세대 비율 | single_households / households ×100. 통계청 1인가구와 같은 개념으로 단정하지 않음 |
| 아파트 전용면적 ㎡당 중앙가격 | 개별 매매 거래금액(원)/전용면적(㎡)의 월 중앙값. 총거래금액/총면적이나 전체주택 평균가격이 아님 |
| 가격 전년 대비 | 같은 법정지역 현재월 중앙가격 / 전년 동월 중앙가격 -1, ×100 |
| 인구1천명당 업소수 | 업소수 / 인구 ×1000. 작은 인구에서 크게 나타날 수 있음 |
| 창원 평균 | 해당월 유효 법정지역 값의 단순 산술평균. 창원 전체 인구로 가중한 비율이 아님 |

가격 화면만 원 미만 절사한다. 저장·내보내기 원값을 임의 변경하지 않는다. 실제0은 유지하고 작은 양수 비율의 반올림0 오해를 줄인다. 100명·세대 미만 안내는 프로젝트 화면 설명 기준이며 자료 제거 기준이 아니다.

## 4개 프로젝트 지수

같은 월 창원 유효지역에서 구성 지표를 백분위0~100으로 변환하고 가중평균한다. 결측 가중치는 제외·재정규화하며 유효 구성요소2개 미만은 미산출이다. 공식 통계가 아니며 비교범위·비교월·방법 버전을 저장한다.


### 지역활력지수

`population_yoy_pct` 35%, `young_population_share` 30%, `housing_turnover_pct` 20%, `businesses_per_1000_people` 15%

### 주거시장압력지수

`sale_price_yoy_pct` 35%, `rent_count_yoy_pct` 20%, `monthly_rent_share` 20%, `old_building_share` 15%, `housing_turnover_pct` 10%

### 생활편의지수

`businesses_per_1000_people` 30%, `business_diversity_index` 25%, `health_businesses_per_1000_people` 20%, `education_businesses_per_1000_people` 15%, `apartment_supply_proxy` 10%

### 상권활력 대리지수

`businesses_per_1000_people` 30%, `business_diversity_index` 25%, `restaurant_businesses_per_1000_people` 20%, `cafe_businesses_per_1000_people` 15%, `convenience_businesses_per_1000_people` 10%

상권활력은 현재 업소 구성·밀도를 사용하는 대리지수이며 장기 상권 변화/폐업을 직접 측정하지 않는다. 과거 스냅샷이 없으면 해당월 지수가 비어 있을 수 있다. 비교군은 유사 지역2곳과 무작위1곳이며 질문 주제에 맞춰 유사 지역을 선정한다. 인접지역 비교는 제공하지 않는다.

## 검증 근거

- 인구 완료: Actions 38236688877
- 비인구 완료: Actions 38256567484
- 최종 저장값·지수 감사: Actions 38327373901, `evidence/final_data_index_audit.json`
- 홈페이지/API/내보내기: `evidence/live_api_checks.json`
- 청년0%/소규모 인구 공식 원본13지역: Actions38337713559, `evidence/small_population_original_202609.json`
- 23개월 예전 수집 방법 메타데이터 경고는 값 불일치가 아닌 원본 추적성 제한이다.
