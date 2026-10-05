# 데이터 사전 (Data Dictionary)

> v1.1. 실제 API 필드명은 활용승인 Swagger를 최종 기준으로 한다. 아래는 서비스 내부의 **정규화된 필드명**이다.

## 공통 키
|필드|의미|
|---|---|
|`region_id`|프로젝트 지역 식별자. 원칙적으로 법정지역 코드 기반|
|`month`|분석 월 `YYYY-MM`|
|`source_as_of`|원자료 기준시점|
|`fetched_at`|우리 시스템이 수집한 시점|
|`is_provisional`|최근 신고자료 등 잠정치 여부|
|`sample_size`|가격/거래 등 해당 소스의 관측 표본수|
|`data_confidence`|`low / medium / high / unknown`|

## 인구·가구 정규화 필드
- `population_total`, `households`, `population_male`, `population_female`
- `age_20_39`: 20~29 + 30~39 남녀 합계
- `age_65_plus`: API가 65+ 직접값을 제공할 때만 정확값
- `age_60_plus`: 10세 구간 API에서 계산 가능한 60+ 합계
- `single_households`, `single_male_households`, `single_female_households`, `single_age_20_39`, `single_age_60_plus`
  - `single_households`는 15108085의 **주민등록 1인세대수**이다. 통계청 인구주택총조사의 `1인가구`와 동일 개념이 아니므로 화면에서는 `1인세대 비율` 또는 `1인가구비율 Proxy(주민등록 1인세대 기준)`로 표시한다.
- `one_person_households`, `two_person_households`, `three_person_households`, `four_person_households`, `five_plus_households`
- `birth_count`, `death_count`, `natural_change`

`older_population_share`는 `age_65_plus`가 있으면 이를 사용하고, 없으면 `age_60_plus`를 Proxy로 사용한다. 이때 `older_population_basis=60_plus_proxy`와 `older_population_is_proxy=true`를 반드시 함께 저장한다.

## 주택·건축
- `apartment_complex_count`, `apartment_units`, `apartment_building_count`, `apartment_total_area_m2`
- `building_count`, `old_buildings_30y`, `building_total_area_m2`, `residential_building_area_m2`
- `apartment_like_building_count`, `building_register_household_units`

## 아파트 매매
- `sale_count`
- `sale_total_amount`
- `sale_median_price`
- `sale_price_per_m2`: 개별 거래의 `거래금액/전용면적`을 계산한 뒤 월 중앙값
- `sale_mean_area_m2`

## 전월세
- `rent_count`, `jeonse_count`, `monthly_rent_count`
- `jeonse_price`: 월 전세보증금 중앙값
- `jeonse_price_per_m2`
- `monthly_deposit_median`, `monthly_rent_median`

## 상권
- `business_count`
- `business_category_counts`
- `health_business_count`, `education_business_count`
- `restaurant_count`, `cafe_count`, `convenience_store_count`

업소가 Snapshot에서 사라졌다고 즉시 `폐업`으로 단정하지 않는다. 프로젝트 지표는 `상가 순증감` 또는 `목록 순증감`으로 표현한다.

## 기타 부동산·공매
- `rowhouse_sale_count`, `single_house_sale_count`, `commercial_transaction_count`
- `auction_listing_count`, `auction_appraisal_median`, `auction_min_bid_median`
- `auction_result_count`, `auction_success_count`, `auction_failed_count`, `auction_award_price_ratio`

## 핵심 파생지표
- `population_mom_pct`, `population_yoy_pct`
- `young_population_share`, `older_population_share`
- `single_household_share`, `small_household_share`
  - `single_household_share = 주민등록 1인세대수 / 주민등록 세대수`. 공식 `1인가구비율`이 아니라 주민등록 기반 Proxy임을 명시한다.
- `apartment_supply_proxy`
- `old_building_share`
- `sale_price_yoy_pct`, `housing_turnover_pct`
- `jeonse_price_yoy_pct`, `rent_count_yoy_pct`, `monthly_rent_share`
- `businesses_per_1000_people`, `business_net_change`, `business_diversity_index`

추가 보조지표:
- `young_single_household_share`, `older_single_household_share`
- `health_businesses_per_1000_people`, `education_businesses_per_1000_people`
- `auction_listings_per_1000_households`, `commercial_transaction_yoy_pct`

## Composite Index
- `vitality_index`
- `housing_pressure_index`
- `living_convenience_index`
- `commerce_change_index`

모두 프로젝트 자체 정의 지표이며 공식 통계가 아니다. 결측치는 0으로 바꾸지 않고 해당 가중치를 제외해 재정규화한다.
