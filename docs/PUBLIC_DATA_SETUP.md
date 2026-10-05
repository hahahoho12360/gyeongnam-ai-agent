# 공공데이터 실데이터 연결 선행작업

> 확인 기준: 2026-10-05. API 페이지/필드명은 기관 개편으로 바뀔 수 있으므로 **활용신청 후 본인 화면의 Swagger 명세를 최종 기준**으로 삼는다.

이 프로젝트에서 Firebase/OpenAI/Render/Vercel/Cursor 계정만으로는 실데이터를 만들 수 없다. **공공데이터포털(data.go.kr) 로그인 + 서비스키 + 각 OpenAPI 활용승인**이 추가로 필요하다.

## 1. 먼저 할 일

1. https://www.data.go.kr 로그인
2. 아래 표의 API를 하나씩 열고 `활용신청`
3. 같은 프로젝트 서비스키를 사용할 수 있으면 같은 키로 신청
4. `마이페이지 → OpenAPI → 개발계정`에서 승인 상태 확인
5. 서비스키를 `.env`의 `DATA_GO_KR_SERVICE_KEY`에 저장
6. **서비스키를 README/GitHub/스크린샷/채팅에 붙이지 않는다.**

## 1-A. 법정지역 Master는 서비스키 없이도 가능
공공데이터포털의 `국토교통부_전국 법정동` 파일데이터는 로그인 없이 CSV를 다운로드할 수 있다.

- 공식 페이지: https://www.data.go.kr/data/15063424/fileData.do
- `.env`: `LEGAL_DONG_CSV_PATH=C:\\path\\전국법정동.csv`
- 실행: `python scripts/bootstrap_regions.py`
- 먼저 점검만 할 때: `python scripts/bootstrap_regions_file.py <csv> --dry-run`

이 방법은 지역 Master 준비를 빠르게 할 수 있지만, 인구·실거래·상권 등 실제 시계열 수집에는 여전히 각 OpenAPI의 서비스키/활용승인이 필요하다.

## 2. 핵심 8종

|구분|공식 데이터|data.go.kr ID|프로젝트 상태|
|---|---|---:|---|
|1|행안부 법정동별 주민등록 인구·세대|15108071|환경변수 명세형 adapter 준비|
|2|법정동별 성·연령별 인구|15108074|환경변수 명세형 adapter 준비|
|3|법정동별 성·연령별 1인세대|15108085|환경변수 명세형 adapter 준비|
|4|국토부 공동주택 기본정보|15058453|단지목록→기본정보 snapshot adapter 준비|
|5|건축HUB 건축물대장|15134735|`getBrTitleInfo` adapter 준비|
|6|아파트 매매 실거래 상세|15126468/15126469|실행 adapter 준비|
|7|아파트 전월세 실거래|15126474|실행 adapter 준비|
|8|소진공 상가(상권)정보|15012005|실행 adapter 준비|

### 현재 코드에 기본값이 들어간 요청 URL

```text
아파트 매매 상세
https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev

아파트 전월세
https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent

건축물대장 표제부
https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo

상가(상권)정보 - 행정구역 단위 업소
https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong

공동주택 단지목록
https://apis.data.go.kr/1613000/AptListService3/getSidoAptList3

공동주택 기본정보
https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5
```

> 공동주택 API는 기관 개편 시 요청 URL이 달라질 수 있으므로 본인 승인 화면에서 실제 URL을 다시 확인한다.

## 3. 확장 4종

### A. 세대원수 + 출생·사망
행안부 주민등록 계열에서 법정동 단위 상세기능을 승인받은 뒤 아래를 채운다.

```env
HOUSEHOLD_SIZE_API_URL=
HOUSEHOLD_SIZE_QUERY_JSON={}
BIRTH_DEATH_API_URL=
BIRTH_DEATH_QUERY_JSON={}
# 출생/사망이 별도 상세기능이면 아래 방식도 지원
BIRTH_API_URL=
BIRTH_QUERY_JSON={}
DEATH_API_URL=
DEATH_QUERY_JSON={}
```

### B. 기타 주택·상업용 실거래
현재 코드는 아래 3종을 한 번에 집계할 수 있다.

- 연립·다세대 매매: data.go.kr `15126467`, Base `/1613000/RTMSDataSvcRHTrade`
- 단독·다가구 매매: `15126465`, Base `/1613000/RTMSDataSvcSHTrade`
- 상업·업무용 매매: `15126463`, Base `/1613000/RTMSDataSvcNrgTrade`

`.env.example`에 기본 호출 URL이 포함되어 있다.

### C. 온비드 공매
추천 활용신청:

- **지역별 월간 집계의 1순위:** 물건 입찰결과목록 `15157252` — 매시간 갱신, 결과의 주소를 법정지역에 매핑
- 부동산 물건상세 `15157247`은 `cltrMngNo`(물건관리번호)가 필수이므로 **전국/경남 목록을 한 번에 긁는 API가 아니다.** 목록 서비스에서 번호를 확보했을 때 상세 보강용으로만 사용한다.
- 용도별 입찰 통계 `15157757` — 월간 통계, Base `/B010003/OnbidUsgBidStatsSrvc`; 공간범위가 지역 법정동 단위가 아니므로 경남 전체 Benchmark/참고지표 성격으로 사용한다.

온비드는 물건유형/재산유형/개찰일 등의 **필수 코드 파라미터**가 있으므로 승인된 Swagger에서 값을 확인한 뒤:

```env
ONBID_PROPERTY_API_URL=
ONBID_RESULT_API_URL=
ONBID_PROPERTY_QUERY_JSON={}
ONBID_RESULT_QUERY_JSON={}
```

에 넣는다. 템플릿 placeholder는 `{month}`, `{yyyymm}`, `{start_date}`, `{end_date}`를 쓸 수 있다.

### D. KOSIS Benchmark
KOSIS는 월간 live source가 아니라 주택종류·거처형태를 검증하는 Benchmark로 분리한다.

1. KOSIS에서 필요한 표를 CSV로 다운로드
2. `docs/KOSIS_BENCHMARK_TEMPLATE.csv` 형식으로 정리
3. 실행:

```powershell
python scripts/import_kosis_benchmark.py my_kosis.csv
```

`benchmarks` 컬렉션에 저장되며 월간 `monthly_data`와 섞지 않는다.

### E. KOSIS OpenAPI(선택)
KOSIS Benchmark는 CSV import가 가장 단순하지만, 자동화가 필요하면 KOSIS 공유서비스 인증키를 별도로 발급받아 통계자료 API를 사용할 수 있다.

- 공식 소개: https://kosis.kr/openapi/index/index.jsp
- 통계자료 API: `https://kosis.kr/openapi/statisticsData.do?method=getList`
- KOSIS는 2026년 기준 분당 호출 제한을 운영하므로 대량 반복호출보다 등록 통계표/CSV Benchmark가 과제에는 안전하다.

## 4. 주민등록 3종의 URL/파라미터 설정법

행안부 법정동 통계 API는 상세기능별 요청 파라미터가 달라질 수 있어 코드에 임의로 고정하지 않았다. 본인의 Swagger에서 **실제 파라미터 이름을 그대로** 복사한다.

예를 들어 승인 명세가 `statMonth`, `bjdCd`라는 이름을 요구한다고 가정하면(예시일 뿐):

```env
POPULATION_API_URL=https://apis.data.go.kr/.../select...
POPULATION_QUERY_JSON={"statMonth":"{yyyymm}","bjdCd":"{bjd_code}"}
```

지원 placeholder:

- `{month}` → `2026-09`
- `{yyyymm}` → `202609`
- `{bjd_code}` → 10자리 법정동코드
- `{sigungu_code}` → 앞 5자리
- `{bjdong_code}` → 뒤 5자리
- `{region_name}`
- `{full_name}`

연령/1인세대도 같은 방법이다.


### 호출량 줄이기: QUERY_SCOPE
주민등록 상세기능은 처음에는 `region`으로 검증한다. 승인 Swagger가 시군구 전체행을 한 번에 반환할 수 있다면 `sigungu`, 경남 전체를 한 번에 검색할 수 있다면 `global`로 바꿀 수 있다.

```env
POPULATION_QUERY_SCOPE=region
AGE_POPULATION_QUERY_SCOPE=region
SINGLE_HOUSEHOLD_QUERY_SCOPE=region
```

허용값: `region | sigungu | global`. 지원하지 않는 범위를 억지로 사용하면 잘못된 결과가 되므로 본인 Swagger를 기준으로 한다.

### 실제 인접지역 구축
인접지역 2곳을 실제 경계 기준으로 추천하려면 법정구역 경계가 필요하다. 국토교통부 **법정구역정보(WMS/WFS)** 또는 공식 경계 파일을 GeoJSON으로 준비한 뒤:

```powershell
pip install -r requirements-spatial.txt
python scripts/build_neighbors.py gyeongnam_legal.geojson --code-field 실제코드필드명
```

을 실행한다. 법정리는 부모 읍·면 geometry로 합쳐지며 `regions.neighbors`가 채워진다.

## 5. 키 설정 후 첫 검증 순서

```powershell
# 1) 경남 법정읍면동 Master
python scripts/bootstrap_regions.py

# 2) API 한 개의 응답 구조 probe (민감정보 출력 주의)
python scripts/probe_api.py --source apt_sale --month 2026-09 --sigungu 48123

# 3) 최근 실거래 증분 갱신
python scripts/update_data.py --scope daily

# 4) 직전월 공식/스냅샷 데이터
python scripts/update_data.py --scope monthly
```

처음부터 2022-10 전체를 돌리지 말고 대표 1~3개 지역/한 달로 결과를 눈으로 확인한 뒤 Backfill한다.

주민등록/온비드처럼 URL·필수 파라미터를 환경변수로 넣는 API는 다음으로 승인 명세를 직접 probe한다.

```powershell
python scripts/probe_configured_api.py --source population --month 2026-09 --bjd-code <10자리 법정동코드>
python scripts/probe_configured_api.py --source age_population --month 2026-09 --bjd-code <10자리 법정동코드>
python scripts/probe_configured_api.py --source single_household --month 2026-09 --bjd-code <10자리 법정동코드>
python scripts/probe_configured_api.py --source onbid_result --month 2026-09 --bjd-code <10자리 법정동코드>
```

## 6. Historical Backfill

```powershell
python scripts/backfill.py --start 2022-10 --end 2026-09 --source population
python scripts/backfill.py --start 2022-10 --end 2026-09 --source age_population
python scripts/backfill.py --start 2022-10 --end 2026-09 --source single_household
```

부동산은 더 긴 기간을 별도로 수행할 수 있다.

```powershell
python scripts/backfill.py --start 2015-01 --end 2026-09 --source apt_sale --source apt_rent
```

`.backfill-state.json`에 성공 구간이 기록되므로 중단 후 같은 명령을 실행하면 성공분을 건너뛴다.

## 7. 사용자 직접 캡처할 것

실데이터 연결 후 다음은 자동 생성 파일로 대체할 수 없고 실제 화면을 직접 캡처해야 한다.

- data.go.kr 활용신청 승인 화면(키 값은 가릴 것, 선택 증빙)
- Firestore `regions`, `monthly_data`, `conversations`, `source_status`
- GitHub Actions 갱신 성공 화면
- README의 공식 데이터 출처와 기준시점 설명

최종 제출용 필수 증빙 전체 목록은 `EVIDENCE_CHECKLIST.md`를 따른다.


## 주민등록 인구·세대(15108071) 확정 설정

공식 Swagger 기준 Base URL은 `https://apis.data.go.kr/1741000/stdgPpltnHhStus`, 상세기능은 `/selectStdgPpltnHhStus`이다.
초기 단일 법정동 probe는 다음 설정을 사용한다.

```env
POPULATION_API_URL=https://apis.data.go.kr/1741000/stdgPpltnHhStus/selectStdgPpltnHhStus
POPULATION_QUERY_JSON={"stdgCd":"{bjd_code}","srchFrYm":"{yyyymm}","srchToYm":"{yyyymm}","lv":"7","regSeCd":"1","type":"JSON"}
POPULATION_QUERY_SCOPE=region
```

- `lv=7`: 단일 리·동 단위 조회. 도시 법정동 단위 probe에 우선 사용한다.
- `regSeCd=1`: 전체(거주자+거주불명자+재외국민).
- `type=JSON`: 응답 파싱을 단순화한다.
- 운영 수집기는 페이지 전체를 자동 순회한다.
- 응답이 통·반 여러 행으로 오는 경우에도 `aggregate_population_rows()`가 `stdgCd` 기준으로 합산하고 `hhNmpr`, `maleFemlRate`는 합계에서 재계산한다.
- 농촌 법정리 응답은 Master의 부모 읍·면으로 roll-up할 수 있도록 `map_region_id()`가 법정리 코드의 부모코드를 처리한다.
- **중요:** `lv=7`이 읍·면 부모 코드에서 직접 1행을 반환하는지는 실제 승인 API로 추가 probe한다. 0건이면 시군구 단위(`lv=3` 등) 조회 전략을 별도 검증해 전환한다.

### 15108074 성·연령별 주민등록 인구 확정 설정
```env
AGE_POPULATION_API_URL=https://apis.data.go.kr/1741000/stdgSexdAgePpltn/selectStdgSexdAgePpltn
AGE_POPULATION_QUERY_JSON={"stdgCd":"{bjd_code}","srchFrYm":"{yyyymm}","srchToYm":"{yyyymm}","lv":"7","regSeCd":"1","type":"JSON"}
AGE_POPULATION_QUERY_SCOPE=region
```
이 API는 10세 구간만 제공하므로 20~39세는 정확 계산하고, 고연령 지표는 60+를 사용한다. 65+ 공식값으로 표기하지 않는다.


### 공동주택 API 버전 주의 (2026-10 확인)
- 단지목록은 `AptListService3/getSidoAptList3` + `sidoCode=48`(경남)을 사용한다.
- 기본정보는 `AptBasisInfoServiceV5/getAphusBassInfoV5`를 사용한다.
- 구버전 `AptListService2/getTotalAptList`, `AptBasisInfoService1/getAphusBassInfo`는 현재 환경에서 400 또는 변경된 서비스와 불일치할 수 있다.
