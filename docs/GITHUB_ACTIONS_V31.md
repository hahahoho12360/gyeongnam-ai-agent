# GitHub Actions Cloud Rollout v3.1

## 변경 이유
v3.0에서는 공공데이터포털의 `NODATA_ERROR`를 치명적 오류로 해석해 첫 지역에서 자료가 없으면 전체 Cloud Rollout을 `blocked`로 중단했다.

v3.1에서는 `NODATA_ERROR`를 인증/서버 장애가 아닌 **조회 결과 없음(no data)** 으로 분리한다.

## 동작 정책
- `NODATA_ERROR`: 정상 결측으로 처리하고 계속 진행
- 빈 응답 또는 지역 매핑 행 없음: 해당 source/month/region에 `freshness.sources.<source>.status=no_data` 기록
- timeout / 429 / 5xx: 제한 재시도
- 400 / 401 / 403 / 잘못된 서비스 설정: `blocked`
- `blocked`: GitHub Actions 자체도 빨간 X로 종료해 사람이 쉽게 인지
- 이전 v2.9/Cloud 작업에서 이미 완료된 지역은 같은 Batch 안에서도 제외하고 미완료 지역만 다시 호출

## Firestore 진행 문서
v3.1은 v3.0 상태와 분리해 다음 문서를 사용한다.

- 창원: `rollout_jobs/cloud_changwon_v31`
- 경남: `rollout_jobs/cloud_gyeongnam_v31`

기존 `monthly_data`는 그대로 재사용한다. 이미 source freshness가 있는 지역은 재수집하지 않는다.

## 실행
GitHub Actions에서 `Gyeongnam AI Cloud Rollout v3.1`을 선택한다.

창원 검증:
- scope: `changwon`
- reset: `false`
- batch_size: `10`

창원 완료 후 경남:
- scope: `gyeongnam`
- reset: `false`
- batch_size: `10`
