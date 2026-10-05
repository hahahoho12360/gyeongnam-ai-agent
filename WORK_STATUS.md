## Checkpoint 2.3
- 공동주택 기본정보를 현재 Swagger의 `AptBasisInfoServiceV5/getAphusBassInfoV5`로 전환
- `DataGoKrClient.get(..., add_paging=False)` 지원 추가
- 공동주택 기본정보 probe/본 수집에서 `pageNo`, `numOfRows`를 보내지 않도록 수정
- 자동 테스트 27개 통과

## Checkpoint 2.1
- 공동주택 단지목록 구버전 `AptListService2/getTotalAptList` HTTP 400 실제 확인 후 `AptListService3/getSidoAptList3`로 전환
- 경상남도만 조회하도록 `sidoCode=48` 기본 적용 (`APT_LIST_SIDO_CODE`)
- 공동주택 기본정보를 국토부 변경 공지의 `AptBasisInfoServiceV5/getAphusBassInfoV5`로 전환
- 사용자 활용신청 Swagger 값이 다를 경우 Swagger를 최우선으로 재검증

## Checkpoint 1.8
- 15108074 성·연령별 주민등록 인구 Swagger 실제 필드명/URL 반영
- male0AgeNmprCnt~male100AgeNmprCnt, feml0AgeNmprCnt~feml100AgeNmprCnt 파싱 지원
- 통·반/리 다중 행을 법정분석지역 단위로 합산
- age_20_39, age_60_plus 및 10세 구간별 metric 저장

# 작업 상태 — Checkpoint 1.4

## 현재 구현 완료
- [x] 미션 필수 API: `(date,value,memo)` CRUD 4 + summary
- [x] 대화 저장/목록/상세/삭제 + 채팅 자동저장
- [x] FastAPI / CORS / Pydantic / Swagger `/docs`
- [x] Firestore 실제 연결 코드 + Memory test mode
- [x] `regions` / `monthly_data` / `region_latest` / `source_status` / `benchmarks` 구조
- [x] 경남 법정지역 Master bootstrap 코드
- [x] 공식 전국 법정동 CSV로 서비스키 없이 경남 지역 Master 생성하는 대안 경로
- [x] 필수 8종 + 확장 4종 데이터 파이프라인 골격 및 주요 국토부·상권 API adapter
- [x] 주민등록/확장 API는 승인된 명세의 URL·파라미터 JSON을 환경변수로 주입하는 범용 adapter
- [x] 주민등록 query scope `region/sigungu/global` 선택 지원(승인 Swagger가 허용할 때 호출량 절감)
- [x] 성·연령 API의 남/여 10세 구간을 자동 합산하고 20~39, 60+ 계산
- [x] 65+ 직접값이 없을 때 `60_plus_proxy`임을 명시하는 고연령 비율 처리
- [x] 성·연령별 1인세대의 청년/고연령 1인세대 보조지표
- [x] 세대원수 1~10+ 대응 및 출생/사망 통합·분리 API 방식 모두 지원
- [x] Historical Backfill + `.backfill-state.json` 재개
- [x] 최근 3개월 실거래 재조회(upsert) Incremental Update
- [x] 오래된 실거래월은 provisional 해제, 실시간/잠정자료 `source_as_of`는 실제 조회일로 기록
- [x] 16개 핵심 파생지표 + 보조 파생지표
- [x] Composite Index 4종 및 경남 동일월 percentile 계산
- [x] freshness / provisional / sample size / data confidence
- [x] 실제 경계 GeoJSON 기반 `neighbors` 생성 도구 (`scripts/build_neighbors.py`)
- [x] 인접/Peer/seeded random 비교 구조
- [x] 간단·기본·상세 능동분석 bundle + 1~2개 그래프
- [x] OpenAI Responses API Function Calling 루프
- [x] `store=false` stateless Tool Calling 시 reasoning/function_call/output 전체 재전송 방식 적용
- [x] 도메인 Tool: 인구/주택매매/전월세/상권/공매/비교/Composite/Live
- [x] Cache-First Live Overlay + 선택적 TTL 최신 실거래/온비드 재조회
- [x] MCP stdio Server(Cursor) — 동일 tooling dispatch 공유
- [x] Vanilla HTML/CSS/JS: 채팅/로딩/요약/비교근거/그래프/CRUD/대화/CSV·JSON/다크모드/최신상태 확인
- [x] Secret을 노출하지 않는 `/api/meta/readiness` + 갱신 이력 `/api/meta/source-status` + 프론트 데이터 소스 상태 패널
- [x] `/api/meta/data-quality` 실데이터 커버리지·100포인트·freshness·confidence 제출 점검
- [x] Daily 갱신에 온비드(설정 시) 포함 + 미설정 소스 안전 skip
- [x] GitHub Actions daily/monthly 갱신 workflow
- [x] Render/Vercel 설정
- [x] README, 데이터 연결, 아키텍처, Function Calling, 지표, 데이터사전, 배포, 증빙 문서
- [x] 첨부 미션 요구사항 자동 역점검 스크립트 + `docs/SUBMISSION_AUDIT.md`
- [x] 자동테스트 **20개 통과** + Python compile + JS syntax check

## 외부 계정/실데이터 때문에 남은 실행 작업
Firebase/OpenAI/Render/Vercel/Cursor 준비는 되었지만, **공공데이터포털 서비스키/필수 활용승인 상세명세를 실제 프로젝트 `.env`에 입력해야 실데이터 단계로 넘어갈 수 있다.**

- [ ] data.go.kr 필수 8종 + 확장 API 활용신청 및 `DATA_GO_KR_SERVICE_KEY` 설정
- [ ] 주민등록 계열 URL/필수 파라미터 JSON을 승인된 Swagger에 맞춰 `.env`에 설정
- [ ] 공식 법정구역 경계 GeoJSON 준비 → `scripts/build_neighbors.py`로 실제 인접지역 생성
- [ ] 온비드 필수 검색코드/URL 설정
- [ ] 실제 `python scripts/bootstrap_regions.py` 실행 → 경남 지역 Master 적재
- [ ] 대표 시군구 1~3곳 API probe로 응답 필드 최종 검증
- [ ] 2022-10~최신월 Historical Backfill (부동산은 2015+ 선택)
- [ ] 실데이터 분포에서 Composite Index와 Peer Group 검증
- [ ] Firebase 실제 Firestore 모드 전환
- [ ] OpenAI 실제 Function Calling 질의 검증
- [ ] Cursor에서 MCP Tool 실호출
- [ ] GitHub 저장소 Push → GitHub Actions 수동 갱신 성공
- [ ] Render/Vercel 실제 배포
- [ ] `EVIDENCE_CHECKLIST.md`의 실제 화면 캡처

## 현재 산출물의 의미
Checkpoint 1.4는 **비밀키/사용자 계정이 없어도 작성 가능한 코드·문서·테스트를 최대한 완료한 중간 산출물**이다. 데모 데이터는 UI/API 자동시험 전용이며 실제 통계가 아니다. 최종 제출본은 공공데이터포털 승인키로 실제 데이터를 적재하고 사용자 계정에서 배포/증빙을 완료해야 한다.

## 다음 이어받기 시작점
1. `python scripts/preflight.py`로 설정 준비상태 확인
2. `docs/PUBLIC_DATA_SETUP.md`대로 data.go.kr 활용신청
3. `.env`에 서비스키/승인 명세 입력
4. `python scripts/bootstrap_regions.py`
5. 대표 지역 API probe → adapter alias 검증
6. 공식 경계 GeoJSON로 `scripts/build_neighbors.py`
7. 대표 지역 갱신 → Historical Backfill
8. Firestore/Function Calling/MCP/GitHub Actions/배포 실검증 및 증빙

- 2026-10-05: 국토교통부 아파트 매매 상세 API가 XML `resultCode=000`으로 정상 응답하는 경우를 성공 코드로 인식하도록 `DataGoKrClient.error_message()`를 수정함. 실제 HTTP 200 + resultMsg=OK 응답 확인 후 probe parser 오류를 보정함.

- Checkpoint 1.6: building probe에 --bjdong(법정동코드 뒤 5자리) 인자를 추가하고, 아파트 매매 소스 ID를 실제 사용 중인 상세자료 15126468로 정정했습니다.


### Checkpoint 1.7
- 주민등록 인구 API의 실제 `<Response><head>...<items>` 대문자/비표준 봉투와 `head.totalCount` 파싱 지원
- 주민등록 인구·세대 15108071 공식 Swagger 파라미터 반영
- `stdgCd`, `totNmprCnt`, `hhCnt`, `maleNmprCnt`, `femlNmprCnt` 공식 응답 필드 지원
- 통·반 여러 행이 오더라도 지역별 합산 후 세대당 인구/남녀비율 재계산
- 법정리 코드를 부모 읍·면 Master로 roll-up하는 매핑 추가
- `type=JSON`을 명시하면 공통 client가 `_type=json`을 중복 전송하지 않도록 수정
- 도시 법정동 초기 probe는 `lv=7`, `regSeCd=1` 사용. 읍·면 부모코드 동작은 실 API 추가 검증 필요

### Checkpoint 1.9
- 15108085 성·연령별 주민등록 1인세대 Swagger 공식 URL/필드 대응
- `totHhCnt`, `maleHhCnt`, `femlHhCnt`, `male0AgeHhCnt`~`feml100AgeHhCnt` 파싱 지원
- 통·반/리 다중 행도 법정분석지역 단위로 합산
- `single_age_20_39`, `single_age_60_plus`, 성별 1인세대수 및 10세 구간별 metric 저장
- 주민등록 `1인세대`와 통계청 `1인가구` 개념 차이를 데이터사전/UI에 명시

## Checkpoint 2.2 공동주택 목록 API v4 정합화

- 공공데이터포털 현재 Swagger 기준 단지목록 Base URL을 `AptListService4`로 갱신했습니다.
- 법정동 목록 상세기능 `getLegaldongAptList4`의 필수 `bjdCode`를 사용합니다.
- probe는 `python scripts/probe_api.py --source apt_list --bjd-code 4812313300` 형식으로 검증합니다.
- 공동주택 기본정보는 반드시 목록 API에서 얻은 실제 `kaptCode`로 검증해야 하며 예시/임의 코드는 사용하지 않습니다.
- 기본정보 API 상세 URL/필드 구조는 해당 서비스의 현재 Swagger를 최종 기준으로 확인합니다.

## Checkpoint 2.4 - Dedicated single-region Smoke Test
- Added `scripts/smoke_test.py`.
- Added process-local `REGION_FILTER_ID` support in `scripts/pipeline.py` so collectors can be safely scoped to one legal-dong without changing `.env`.
- Default smoke test is DRY-RUN and does not write `monthly_data`.
- `--write` writes only one `monthly_data/{region}_{month}` document and marks `freshness.smoke_test=true`.
- `--cleanup` only deletes documents carrying the smoke-test marker; it refuses to delete unmarked production data.
- Composite Index is intentionally skipped in one-region smoke tests because Gyeongnam-wide same-month percentile population is required.
- Core source order: population, age_population, single_household, apartment_basic, apt_sale, apt_rent, building_register, commerce.
- Validation: `pytest -q` => 27 passed.


## Checkpoint 2.6
- data.go.kr 일시적 timeout/연결오류/429/5xx 자동 재시도 추가
- 기본 timeout 60초, 최대 3회 재시도, 지수형 backoff 적용
- Smoke Test write 중 일부 API의 순간 지연으로 전체가 실패하는 문제 완화
- pytest 27 passed


## Checkpoint 2.7
- 단일지역 Pilot에서 regions 523건 전체 scan 제거: REGION_FILTER_ID이면 직접 document get
- Firestore 최신 FieldFilter 문법 적용
- DEFER_INDEX_RECOMPUTE로 Pilot 중 Composite Index 재계산/추가 읽기·쓰기 지연 가능
- ResourceExhausted/Quota exceeded 감지 시 backfill 즉시 중단, resume 보존
- pytest 27 passed

## Checkpoint 2.8 — Batch 안전장치

- 남양동 13개월 Historical Pilot 및 MoM/YoY 검증 완료 이후 확장 단계.
- `backfill.py`에 지역 범위 필수 지정, 최대 지역 수, offset, batch-size, Historical/Snapshot 분리, 계획 전용 dry-run을 추가.
- `pipeline.all_regions()`에 `REGION_FILTER_IDS`와 프로세스 내 region cache를 추가하여 Batch별 Firestore 반복 읽기를 감소.
- Snapshot(`apartment_basic`, `building_register`, `commerce`)을 여러 과거 월에 복제하는 실행을 차단.
- Resume key에 Batch scope hash를 포함해 서로 다른 지역 Batch 완료 이력이 충돌하지 않도록 변경.
- 다음 실행 권장: 창원권 5개 지역 × 13개월 Historical `--dry-run-plan` → 실제 Batch.

## Checkpoint 2.9
- 남양동 Historical Pilot 성공 이후 수동 Batch 반복 피로도를 줄이기 위한 자동 Rollout 추가.
- `scripts/auto_rollout.py --scope changwon|gyeongnam` 한 명령으로 Historical → Snapshot → (경남일 때) Composite Index → 품질리포트 수행.
- Resume/재시도/로그/상태파일/요약 JSON 지원.
- Windows 원클릭용 `scripts/run_changwon_v29.bat`, `scripts/run_gyeongnam_v29.bat` 추가.
- 실제 비밀키는 포함하지 않음. 실행은 사용자의 기존 `.env`를 사용.

## Checkpoint 3.0

- GitHub Actions 기반 PC-off Cloud Rollout 추가
- Firestore `rollout_jobs`에 source-month-batch 단위 cursor 영속화
- GitHub hosted runner 6시간 한도를 고려한 270분 자체 time budget
- `workflow_dispatch` 자동 재호출로 여러 Actions run에 걸쳐 무인 연속 수행
- 완료된 monthly_data source는 재시작 시 API 재호출 skip
- retryable 오류와 non-retryable 오류 분리, 무한 비용 루프 방지
- Historical → Snapshot → Composite Index(경남) → Data Quality 단계 자동화
- Snapshot source의 `source_as_of`를 실제 조회일로 기록하도록 보완
