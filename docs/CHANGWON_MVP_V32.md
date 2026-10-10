# Checkpoint 3.2 — 창원 MVP 복합지수 + Data Quality 최종검증

## 목적
경남 전체 수집은 보류하고, 이미 수집 완료된 창원시 법정지역 데이터를 1차 MVP의 비교모집단으로 사용한다.

## 4개 프로젝트 정의 Composite Index
- 지역활력지수 `vitality_index`
- 주거시장압력지수 `housing_pressure_index`
- 생활편의지수 `living_convenience_index`
- 상권변화지수 `commerce_change_index`

모든 지수는 공식 통계가 아닌 프로젝트 정의 지수이며, 같은 월의 창원 지역 안에서 각 구성지표를 percentile(0~100)로 표준화한 뒤 가중평균한다.
결측 구성요소는 해당 가중치를 제외하고 재정규화하며, 최소 2개 구성요소가 있어야 지수를 계산한다.

### 상권변화지수 주의
상권 Snapshot은 이번 수집부터 월별 축적되므로 과거 변화 시계열이 충분하지 않다.
따라서 1차 MVP의 `commerce_change_index`는 현시점 상권활력 Proxy로 계산하고 UI/README/보고서에서 이 한계를 명시한다.
향후 월별 Snapshot이 축적되면 사업체 순증감/YoY 중심의 진짜 변화지수로 교체한다.

## 실행
GitHub Actions → **Changwon MVP finalize v3.2** → Run workflow.
월 입력은 비워두면 창원 Firestore 최신월을 자동 선택한다.

Workflow는:
1. 창원 Master 범위 확인
2. 최신월 derived 재계산
3. 창원 비교범위 4개 지수 계산
4. `monthly_data`, `region_latest`에 indexes + index_meta 저장
5. `rollout_reports/changwon_v32_final`에 최종 품질/방법론 리포트 저장
6. `changwon_v32_final_report.json` artifact 업로드

## 최종 확인 항목
- `minimum_100_points_met=true`
- `regions_master_count=181` (현재 Master 기준)
- latest month의 지역 커버리지
- 8개 core source별 processed/no_data 비율
- 4개 index별 coverage
- invalid_numeric_count
- comparison_scope=`changwon`
- official_statistic=false

경남 전체 확장 시 동일 지수 정의를 사용하되 comparison_scope를 `gyeongnam`으로 바꾸고 같은 월 523개 지역(당시 Master 기준)으로 다시 percentile을 계산한다.
