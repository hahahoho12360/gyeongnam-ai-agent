# 데이터 소스 명세 — 실제 활용신청 체크리스트

> 이 프로젝트는 **필수 8종 + 확장 4종**을 목표로 한다. 각 API의 상세기능 호출 URL은 공공데이터포털에서 **활용신청 후 제공되는 실제 명세**를 `.env`에 넣는다. 서비스키/키는 Git에 저장하지 않는다.

|구분|공식 데이터|포털 ID/링크|원자료 주기|프로젝트 저장|환경변수|
|---|---|---|---|---|---|
|Master|행정안전부 행정표준코드 법정동코드 / 국토부 전국 법정동 CSV|15077871 / 15063424|수시(API) / 연간(CSV)|`regions`|API 또는 `LEGAL_DONG_CSV_PATH`|
|필수1|행정안전부 법정동별 주민등록 인구·세대|15108071|월말 집계(API 메타는 실시간)|월별 Aggregate|POPULATION_API_URL|
|필수2|법정동별 성·연령별 인구|15108074|월말 집계|월별 Aggregate|AGE_POPULATION_API_URL|
|필수3|법정동별 성·연령별 1인세대|15108085|월말 집계|월별 Aggregate|SINGLE_HOUSEHOLD_API_URL|
|필수4|국토부 공동주택 기본정보|15058453|변경/조회 스냅샷|월 Snapshot|APARTMENT_BASIC_API_URL|
|필수5|국토부 건축HUB 건축물대장|15134735|월간/기관 갱신|월 Aggregate|BUILDING_REGISTER_API_URL|
|필수6|국토부 아파트 매매 실거래|15126469|신고 반영|일갱신 + 월 Aggregate|APT_SALE_API_URL|
|필수7|국토부 아파트 전월세 실거래|15126474|신고/확정일자 반영|일갱신 + 월 Aggregate|APT_RENT_API_URL|
|필수8|소진공 상가(상권)정보|15012005|업소 DB 갱신|주/월 Snapshot|COMMERCE_API_URL|
|확장1|세대원수·출생·사망|주민등록통계 관련 API|월말 집계|월 Aggregate|HOUSEHOLD_SIZE_API_URL + BIRTH_DEATH_API_URL 또는 BIRTH_API_URL/DEATH_API_URL|
|확장2|기타 주택·상업용 실거래|국토부 실거래 관련 API|신고 반영|월 Aggregate|ROWHOUSE_SALE_API_URL / SINGLE_HOUSE_SALE_API_URL / COMMERCIAL_SALE_API_URL|
|확장3|온비드 공매 입찰결과 + 선택적 상세|15157252 (주) / 15157247 (상세) / 15157757 (통계)|입찰결과 매시간 / 통계 월간|결과 주소 기반 월 Aggregate + Live|ONBID_RESULT_API_URL (+ 선택적 PROPERTY)|
|확장4|KOSIS 주택 통계|KOSIS|공표주기|Benchmark|CSV import 또는 KOSIS_API_URL|

## 반드시 직접 해야 하는 선행 작업
1. data.go.kr 로그인 → 위 API 각각 `활용신청`. 지역 Master는 법정동코드 API(15077871)를 신청하거나, 로그인 없이 내려받을 수 있는 전국 법정동 CSV(15063424)를 사용할 수 있다.
2. 승인된 프로젝트 서비스키 또는 개인 서비스키 확인.
3. 각 API의 **상세기능** 화면에서 호출 URL, 파라미터, 응답 필드명을 확인한다.
4. `.env` 또는 GitHub/Render Secret에만 저장한다.
5. 처음에는 대표 지역 1~3곳으로 호출 결과를 확인한 뒤 경남 전체로 확대한다.

## 시간의 의미를 분리한다
- `source_as_of`: 원자료 기준시점
- `fetched_at`: 우리 시스템 수집시점
- `is_provisional`: 최근 실거래처럼 잠정치 여부
- 최근 실거래 2~3개월은 매일 **upsert 재계산**한다.

## 경남 지역 Master 자동 생성

공식 법정동코드 API의 요청주소는 `https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList`이며, 프로젝트의 `scripts/bootstrap_regions.py`가 `locatadd_nm=경상남도`로 조회해 법정 읍·면·동 행만 `regions`에 저장한다. `리`는 분석단위에서 제외되어 자연스럽게 부모 읍·면 수준으로 Roll-up된다. 인접지역은 경계 Polygon 데이터 결합 후 별도로 채운다.


## 보조 공간데이터 — 실제 인접지역 계산
- 국토교통부 **법정구역정보(WMS/WFS)** 또는 공식 법정구역 경계 파일을 사용한다.
- 이 자료는 필수 8+확장4의 분석 원천과 별개인 **공간 보조자료**이다.
- 내려받은 GeoJSON을 `scripts/build_neighbors.py`에 넣으면 `regions.neighbors`와 centroid를 계산한다.

```powershell
pip install -r requirements-spatial.txt
python scripts/build_neighbors.py gyeongnam_legal.geojson --code-field EMD_CD
```

실제 코드 필드명(`EMD_CD` 등)은 내려받은 공식 파일의 properties를 보고 지정한다. 법정리 geometry는 부모 읍·면으로 합쳐서 인접성을 계산한다.

## 주민등록 API 호출량 최적화
기본 `*_QUERY_SCOPE=region`은 가장 안전하지만 경남 전체 Backfill 시 호출량이 커진다. 활용승인 Swagger가 시군구 또는 전체 단위 검색을 허용하면 다음처럼 줄일 수 있다.

```env
POPULATION_QUERY_SCOPE=sigungu
AGE_POPULATION_QUERY_SCOPE=sigungu
SINGLE_HOUSEHOLD_QUERY_SCOPE=sigungu
```

허용값은 `region | sigungu | global`. **Swagger가 실제로 그 범위를 지원할 때만** 변경한다.

### 서비스키 없이 지역 Master 만들기
- 공식 파일: https://www.data.go.kr/data/15063424/fileData.do
- 파일데이터는 로그인 없이 내려받을 수 있다.
- `.env`: `LEGAL_DONG_CSV_PATH=C:\...\전국법정동.csv`
- 실행: `python scripts/bootstrap_regions.py`
- 또는 `python scripts/bootstrap_regions_file.py <csv> --dry-run`으로 먼저 행 개수/예시를 확인한다.

### KOSIS OpenAPI 참고
KOSIS Benchmark는 CSV import를 기본으로 유지하지만, KOSIS 공유서비스 API도 확장 가능하다. 공식 통계자료 API는 `https://kosis.kr/openapi/statisticsData.do?method=getList`이며 인증키가 필요하다. 이 프로젝트에서는 Benchmark가 월간 live source가 아니므로 우선 CSV import를 권장한다.

### 온비드 API 선택 주의
- `15157252` 입찰결과목록은 기간 조건으로 결과 목록을 가져올 수 있어 **지역 월간 집계의 핵심**이다.
- `15157247` 부동산 물건상세는 물건관리번호(`cltrMngNo`)가 필수이므로 목록 수집용으로 사용하지 않는다. 목록에서 특정 물건번호를 얻은 뒤 상세 보강할 때만 사용한다.
- `15157757` 용도별 입찰통계는 월별 낙찰률/경쟁률/평균낙찰가율 참고에는 유용하지만 법정읍면동 공간키가 없는 통계이므로 지역 Aggregate와 직접 섞지 않는다.
