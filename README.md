# 경상남도 법정읍·면·동 생활·주거·부동산·상권 변화 AI 비서

> 인구·주택·실거래·상권·공매 통합 시계열 분석 + 데이터 기반 대화형 AI Agent

## 1. 미션 대응
첨부 과제의 핵심인 **시계열 분석 → Firestore 저장 → AI 컨텍스트/도구 호출 → 웹 대화**를 구현한다. 필수 기능은 데이터 기반 채팅, `(date,value,memo)` CRUD, 대화 저장/불러오기, 배포/문서화이며, 보너스 두 묶음을 모두 포함한다.

### 필수
- FastAPI + CORS + `/docs`
- Pydantic 입력 검증
- Firebase Firestore (`data`, `conversations`, `monthly_data`, `regions`)
- CRUD 4개 + `/api/data/summary`
- `/api/chat`: OpenAI 데이터 기반 답변 + 대화 자동저장
- Vanilla HTML/CSS/JavaScript
- Render 백엔드 / Vercel 프론트

### 보너스 A — Function Calling + 멀티채널
- OpenAI Responses API Function Calling
- 동일 `backend/tooling.py` 기능을 MCP Server로 노출
- Cursor stdio MCP 예제 포함 (`.cursor/mcp.json.example`)

### 보너스 B — Insight/UX
- 16개 파생지표 + 4개 Composite Index 설계
- 시계열 SVG 그래프
- CSV/JSON 내보내기
- 다크 모드
- 간단/기본/상세 답변 모드
- 인접 2 + Peer 2 + seeded random 1 비교 설계
- `source_as_of`, `fetched_at`, `is_provisional`, `sample_size`, `data_confidence`
- 데이터 소스 준비/갱신상태 패널

## 2. 데이터 범위
- 상세공간: 경상남도 전체
- 도시: 법정동
- 읍면: 법정리를 부모 읍·면으로 Roll-up
- 공통기간 목표: 2022-10 ~ 최신월
- 부동산 장기추세: 가능한 경우 2015-01 ~ 최신월
- 원시 대용량 이벤트는 Firestore에 전부 보존하지 않고 Python에서 `지역×월`로 사전집계한다.
- 최신성은 Scheduled + On-demand + Manual Refresh 구조로 유지한다.

데이터 12종과 활용신청 체크는 [`DATA_SOURCES.md`](DATA_SOURCES.md).
실제 인접지역은 공식 법정구역 GeoJSON을 `scripts/build_neighbors.py`로 계산해 `regions.neighbors`에 저장한다.

## 3. 빠른 로컬 실행 (데모)
> 데모 데이터는 실제 통계가 아니다. 기능 테스트 전용이다.

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
copy .env.example .env
```

`.env`에서 우선:

```env
USE_MEMORY_DB=true
DEMO_SEED_ON_START=true
OPENAI_API_KEY=본인키  # AI 채팅을 시험할 때만
```

데모 서버:

```powershell
uvicorn backend.main:app --reload
```

`DEMO_SEED_ON_START=true`이면 서버 시작 시 144개의 데모 시계열이 같은 프로세스에 자동 적재된다. **데모값은 실제 통계가 아니므로 최종 제출 증빙에는 사용하지 않는다.** 최종 제출은 반드시 `USE_MEMORY_DB=false` + Firestore + 실제 공공데이터로 수행한다.

API 문서: `http://127.0.0.1:8000/docs`

프론트는 별도 정적 서버로 연다.

```powershell
python -m http.server 5500 -d frontend
```

`http://127.0.0.1:5500`

## 4. Firestore 실사용
`.env`:

```env
USE_MEMORY_DB=false
FIREBASE_PROJECT_ID=...
FIREBASE_SERVICE_ACCOUNT_JSON=C:\\ai-agent-secrets\\firebase-service-account.json
# 또는 Render에서는 JSON 전체를 Secret 문자열로 저장
```

서비스계정 JSON은 GitHub/스크린샷/README에 절대 넣지 않는다.

## 5. 실제 공공데이터 연결
현재 사용자가 공공데이터포털 API 서비스키/각 상세기능 URL을 제공하지 않았으므로 **공통 API Client와 갱신 파이프라인까지만 코드화**되어 있다.

1. [`DATA_SOURCES.md`](DATA_SOURCES.md)의 지역 Master + 12개 소스 활용신청
2. `.env`의 `DATA_GO_KR_SERVICE_KEY`, `*_API_URL` 채우기
3. 활용신청 상세명세에 나온 응답 필드명을 collector adapter에 매핑
4. 지역 Master는 다음 둘 중 하나로 생성
   - OpenAPI: `python scripts/bootstrap_regions.py`
   - 공식 전국 법정동 CSV: `.env`에 `LEGAL_DONG_CSV_PATH=...` 설정 후 같은 명령 실행
5. 대표 1~3지역 검증 → 경남 전체 Historical Backfill
6. `monthly_data`에 Aggregate + freshness 저장

## 6. API 핵심
- `POST/GET/PUT/DELETE /api/data`
- `GET /api/data/summary`
- `POST/GET /api/conversations`
- `GET/DELETE /api/conversations/{id}`
- `POST /api/chat`
- `GET /api/analytics/regions`
- `GET /api/analytics/regions/{id}/summary|trend|compare|indexes`
- `GET /api/analytics/export/{id}?format=csv|json`
- `POST /api/admin/refresh`
- `GET /api/meta/readiness` (비밀값 없이 연결 준비상태)
- `GET /api/meta/source-status` (최근 갱신 기록)
- `GET /api/meta/data-quality` (100포인트·지역/월 커버리지·freshness·신뢰도 제출 점검)

## 7. OpenAI Function Calling
Responses API의 function tool schema를 사용한다. 모델은 필요에 따라 다음 도구를 선택한다.

- `get_region_summary`, `get_population_trend`
- `get_housing_market`, `get_rental_market`
- `get_commerce_trend`, `get_auction_market`
- `compare_regions`, `get_region_indexes`, `get_live_area_snapshot`

Python이 실제 수치 계산을 하고 GPT는 해석한다. `store=false`를 사용하므로 Tool 왕복에서는 이전 `response.output`과 `function_call_output`을 전체 재전송하는 stateless 방식으로 구현했다.

기본 모델은 비용을 고려해 `OPENAI_MODEL=gpt-6-luna`로 두었으며 환경변수로 교체 가능하다.

## 8. Cursor MCP
```powershell
copy .cursor\mcp.json.example .cursor\mcp.json
```
절대경로를 본인 프로젝트 경로로 바꾸고 Cursor를 재시작한다. MCP는 `mcp_server/server.py`가 stdio로 실행된다. 웹 Function Calling과 MCP는 **같은 dispatch/analysis 함수**를 호출한다.

## 9. 자동 갱신
- `.github/workflows/update-daily.yml`: 실거래/전월세/온비드
- `.github/workflows/update-monthly.yml`: 인구/연령/1인세대/공동주택/건축물/상권
- 최근 실거래 2~3개월은 upsert 재계산을 목표로 한다.

API별 필드 매핑 완료 후 GitHub Secrets를 넣고 `workflow_dispatch`로 먼저 검증한다.

## 10. 배포
자세한 순서는 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

- Render: `render.yaml`, Start=`uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Vercel: `vercel.json`; 환경변수 `API_BASE_URL`을 build 시 `frontend/config.js`로 생성
- Render의 `ALLOWED_ORIGINS`에 Vercel URL 등록

## 11. 테스트
```powershell
pytest -q
```

## 12. 실제 캡처가 필요한 증빙
[`EVIDENCE_CHECKLIST.md`](EVIDENCE_CHECKLIST.md)를 반드시 따른다. 특히 아래는 사용자가 직접 캡처해야 한다.
- Swagger `/docs`
- Firestore 실제 컬렉션
- CRUD 화면
- AI 질문+답변+그래프+freshness
- 대화 불러오기
- Function Calling 도구 호출
- Cursor MCP 호출
- CSV/JSON 다운로드
- 다크모드
- Render/Vercel 배포 URL
- GitHub Actions 데이터 갱신 성공

## 13. 요구사항 역점검
|과제 항목|구현 위치|
|---|---|
|데이터 기반 AI 채팅|`backend/routers/chat.py`, `backend/openai_agent.py`|
|CRUD|`backend/routers/data.py`, Frontend|
|대화 저장/불러오기|`backend/routers/conversations.py`, Frontend|
|FastAPI/CORS/Swagger|`backend/main.py`|
|Pydantic|`backend/models.py`|
|Firestore|`backend/db.py`|
|Context/Tool injection|`backend/openai_agent.py`, `backend/tooling.py`|
|그래프|`frontend/app.js` SVG|
|CSV/JSON|analytics export|
|다크모드|Frontend|
|MCP|`mcp_server/server.py`|
|Render|`render.yaml`|
|Vercel|`vercel.json`|
|보안/환경변수|`.env.example`, Secret 방식|

## 14. 현재 체크포인트
현재 완성도와 남은 작업은 [`WORK_STATUS.md`](WORK_STATUS.md)를 참고한다. **Checkpoint 1.4 코드/테스트까지 완료했으며, 실제 공공데이터 승인명세와 사용자 Secret이 필요한 단계만 외부 실행으로 남아 있다.**

---

## 15. Checkpoint 1.1 실제 완성 상태
현재 저장소는 **코드 제작 단계의 Checkpoint 1.3**이다. 자동 테스트에서는 데모 메모리 DB로 필수 기능과 보너스 UI/API를 검증했다. 최종 제출본에서 실데이터로 인정받으려면 `docs/PUBLIC_DATA_SETUP.md`의 활용신청을 완료하고 실제 Firestore에 경남 데이터를 적재해야 한다.

### 자동 검증 완료
```powershell
python -m compileall -q backend scripts mcp_server
pytest -q
node --check frontend/app.js
node --check scripts/build-config.mjs
```
Checkpoint 1.4 작성 시 `pytest` 결과는 **20 passed**였다. 상세 내용은 [`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md).

### 실데이터 연결 후 권장 실행 순서
```powershell
# 0) .env에 Firebase/OpenAI/data.go.kr 설정
python scripts/preflight.py


# 1) 경남 법정지역 Master
python scripts/bootstrap_regions.py

# 2) 대표 시군구 1곳에서 필드 확인
python scripts/probe_api.py --source apt_sale --month 2026-09 --sigungu 48123
python scripts/probe_api.py --source apt_rent --month 2026-09 --sigungu 48123

# 3) 최신 증분 갱신
python scripts/update_data.py --scope daily
python scripts/update_data.py --scope monthly

# 4) 대표지역 결과가 맞으면 Historical Backfill
python scripts/backfill.py --start 2022-10 --end 2026-09 --source population --source age_population --source single_household
python scripts/backfill.py --start 2015-01 --end 2026-09 --source apt_sale --source apt_rent

# 5) 서버
uvicorn backend.main:app --reload
```

## 16. 반드시 사용자가 직접 캡처해야 하는 화면과 캡처 시점
아래 항목은 계정 로그인/실데이터/실배포를 실제로 확인해야 하므로 자동 생성 이미지로 대체하지 않는다. **Secret/API Key/서비스계정 private key는 캡처에 절대 포함하지 않는다.**

1. **Swagger 증빙** — 서버 실행 후 `/docs`에서 CRUD, conversation, chat, analytics, live/export endpoint가 함께 보이게 캡처.
2. **Firestore 증빙** — `regions`, `monthly_data`, `region_latest`, `data`, `conversations`, `source_status` 컬렉션이 생성된 Console 화면.
3. **CRUD 증빙** — 프론트에서 `date/value/memo`를 추가한 뒤 목록이 갱신된 화면과 삭제 또는 수정 동작.
4. **AI 채팅 증빙** — 실데이터 지역을 선택하고 질문 → 로딩 → 답변 → 그래프 → 기준시점/신뢰도가 한 화면에 보이게 캡처.
5. **능동 비교 증빙** — 인접/Peer/Seeded random 비교군과 선정 근거가 표시된 데이터 요약 화면.
6. **대화 불러오기 증빙** — 새로고침 또는 재접속 후 과거 대화를 선택해 메시지가 복원된 화면.
7. **Function Calling 증빙** — `/api/chat` 응답의 `tools_used` 또는 서버 로그에서 `get_region_summary`, `compare_regions`, `get_live_area_snapshot` 등 실제 호출 도구가 보이는 화면.
8. **Cursor MCP 증빙** — `.cursor/mcp.json`을 설정하고 Cursor Agent가 `get_population_trend` 또는 `compare_regions` MCP Tool을 호출한 화면. 웹과 동일 지역의 기반 수치가 일치하는지 확인.
9. **보너스 UX 증빙** — 그래프 + CSV/JSON 다운로드 + 다크모드 중 요구 기능이 실제 동작하는 장면.
10. **최신성 증빙** — `최신 상태 확인` 버튼 또는 `source_status`에서 `source_as_of`, `fetched_at`, provisional/confidence가 보이는 화면.
11. **GitHub Actions 증빙** — `Daily data refresh`/`Monthly data refresh`를 `workflow_dispatch`로 먼저 실행해 초록색 성공 표시를 캡처.
12. **Render 증빙** — 배포 성공 + 실제 Render `/docs` URL.
13. **Vercel 증빙** — Vercel URL에서 실제 앱 접속 및 Render API 통신 성공.

전체 체크박스는 [`EVIDENCE_CHECKLIST.md`](EVIDENCE_CHECKLIST.md)에 있다.

## 17. 최종 제출 전 금지사항
- 데모 지역(`DEMO_*`) 화면을 실데이터 증빙으로 제출하지 않는다.
- `OPENAI_API_KEY`, `DATA_GO_KR_SERVICE_KEY`, Firebase private key를 GitHub/README/화면에 노출하지 않는다.
- 상가 API에서 사라진 업소를 곧바로 `폐업`으로 단정하지 않는다.
- 공동주택 공급비율 Proxy와 Composite Index를 공식 통계처럼 표현하지 않는다.
- 거래가 0인 것과 지표 적용 불가 `N/A`를 혼동하지 않는다.

## 18. 자동 제출 역점검
첨부 미션의 필수/보너스 요구가 코드에 어디 구현됐는지 자동 확인할 수 있다.

```powershell
python scripts/submission_audit.py --write docs/SUBMISSION_AUDIT.md
```

실제 계정 실행이 필요한 항목은 `🟡 코드 구현 · 실제 계정/실행 증빙 필요`로 표시한다.

## 19. 서비스키 없이 지역 Master 만드는 대안
공공데이터포털의 `국토교통부_전국 법정동` 파일데이터는 로그인 없이 CSV 다운로드가 가능하다. 해당 CSV를 받은 뒤:

```powershell
python scripts/bootstrap_regions_file.py "C:\path\전국_법정동.csv" --dry-run
```

결과가 정상이라면 `--dry-run`을 빼고 실행한다. 도시 법정동과 읍·면 행만 저장하고 리 행은 분석단위에서 제외하여 부모 읍·면 roll-up 원칙을 유지한다.


## 16. 데이터 최신화 운영정책
- 원시 이벤트를 Firestore에 무제한 보존하지 않아도 **Scheduled Refresh + Incremental Upsert + Live Overlay**로 최신성을 유지한다.
- daily: 최근 3개월 매매/전월세/기타부동산 + 설정된 경우 온비드 결과를 재수집해 신고지연·정정을 반영한다.
- monthly: 주민등록/연령/1인세대/세대원수·출생사망/공동주택/건축물/상권을 직전 확정월 중심으로 갱신한다.
- `GET /api/meta/data-quality`에서 실제 Firestore 기준 100개 포인트, 최신월 지역 커버리지, provisional/confidence를 확인한다.

> 참고: 일부 국토교통부 OpenAPI는 정상 응답 코드를 `000`으로 반환하므로 클라이언트는 `00`, `0`, `000`, `0000`, `NORMAL_CODE`를 정상 코드로 처리합니다.

- Checkpoint 1.6: building probe에 --bjdong(법정동코드 뒤 5자리) 인자를 추가하고, 아파트 매매 소스 ID를 실제 사용 중인 상세자료 15126468로 정정했습니다.


### Checkpoint 1.9
- 행정안전부 15108085 성·연령별 주민등록 1인세대 공식 Swagger 필드 반영
- `totHhCnt`, `maleHhCnt`, `femlHhCnt`, `male/feml{0..100}AgeHhCnt` 지원
- 청년(20~39), 고연령(60+) 1인세대 및 성별/10세 구간 지표 생성
- 주민등록 `1인세대`와 통계청 `1인가구`를 구분하여 UI에 `1인세대 비율`로 표시


### Checkpoint 2.1 — 공동주택 API 최신 버전 대응
- 2026-10 실제 호출에서 구버전 `AptListService2/getTotalAptList`가 HTTP 400을 반환하여 단지목록을 `AptListService3/getSidoAptList3`로 전환했습니다.
- 경남만 조회하도록 `APT_LIST_SIDO_CODE=48`을 사용합니다.
- 공동주택 기본정보는 국토부 변경 공지에 맞춰 `AptBasisInfoServiceV5/getAphusBassInfoV5`로 전환했습니다.
- 실제 활용신청 Swagger에서 Base URL/상세기능명이 다르면 Swagger 값을 최우선으로 사용합니다.

## Checkpoint 2.2 공동주택 목록 API v4 정합화

- 공공데이터포털 현재 Swagger 기준 단지목록 Base URL을 `AptListService4`로 갱신했습니다.
- 법정동 목록 상세기능 `getLegaldongAptList4`의 필수 `bjdCode`를 사용합니다.
- probe는 `python scripts/probe_api.py --source apt_list --bjd-code 4812313300` 형식으로 검증합니다.
- 공동주택 기본정보는 반드시 목록 API에서 얻은 실제 `kaptCode`로 검증해야 하며 예시/임의 코드는 사용하지 않습니다.
- 기본정보 API 상세 URL/필드 구조는 해당 서비스의 현재 Swagger를 최종 기준으로 확인합니다.

### Dedicated 1-region × 1-month Smoke Test
After all 8 core APIs are individually validated, do not run the Gyeongnam-wide monthly job immediately. First run a single-region dry run:

```powershell
python scripts/smoke_test.py --month 2026-09 --region 4812313300
```

If all eight sources are `ok`, write exactly one test document to Firestore:

```powershell
python scripts/smoke_test.py --month 2026-09 --region 4812313300 --write
```

The saved document is marked `freshness.smoke_test=true`. After screenshots and verification, remove only that marked test document with:

```powershell
python scripts/smoke_test.py --month 2026-09 --region 4812313300 --cleanup
```

Do not use the one-region smoke test to interpret Composite Index scores. Composite Index is recalculated only after same-month Gyeongnam-wide data is loaded.


## Checkpoint 2.7 - Firestore free quota safety

단일지역 Pilot에서 `REGION_FILTER_ID`가 설정되면 `regions` 전체 컬렉션을 읽지 않고 해당 문서만 직접 조회하여 Firestore 읽기 사용량을 절약한다.
`DEFER_INDEX_RECOMPUTE=true`를 사용하면 Pilot 중 Composite Index 재계산을 지연할 수 있다.
`backfill.py`는 `ResourceExhausted / Quota exceeded`를 감지하면 resume 파일을 보존하고 즉시 중단한다.

Pilot 권장 실행 예시(PowerShell):

```powershell
$env:REGION_FILTER_ID="4812313300"
$env:DEFER_INDEX_RECOMPUTE="true"
python scripts/backfill.py --start 2025-09 --end 2026-09 --source population --source age_population --source single_household --source apt_sale --source apt_rent --resume-file .backfill-pilot-namyang.json
Remove-Item Env:REGION_FILTER_ID
Remove-Item Env:DEFER_INDEX_RECOMPUTE
```

## Checkpoint 2.8 — Batch 안전장치

남양동 13개월 Historical Pilot 이후, 경남 전체로 확장하기 전에 `backfill.py`에 지역/Batch 안전장치를 추가했습니다.

주요 기능:
- 지역 범위 미지정 시 실행 거부
- `--region`, `--sigungu-prefix`, `--all-regions`
- `--region-offset`, `--max-regions`, `--batch-size`
- `--historical-only`, `--snapshot-only`
- `--dry-run-plan`
- Snapshot의 다개월 과거복제 차단
- 지역 Batch별 Resume key 분리
- Batch 동안 regions 메모리 cache로 Firestore 반복 read 감소
- Backfill 동안 Composite Index 재계산 자동 지연

처음에는 아무 작업 없이 계획만 확인하세요.

```powershell
python scripts/backfill.py --start 2025-09 --end 2026-09 --historical-only --sigungu-prefix 4812 --max-regions 5 --batch-size 5 --dry-run-plan
```

계획이 맞으면 `--dry-run-plan`만 제거하고 별도 Resume 파일로 실행합니다.

자세한 예시는 `docs/BATCH_SAFETY.md`를 참고하세요.

## Checkpoint 2.9 — 사람 개입을 줄인 자동 Rollout
남양동 Pilot 이후에는 `scripts/auto_rollout.py`를 사용해 창원시 또는 경남 전체 Historical + 최신 Snapshot을 한 번에 진행할 수 있다.

```powershell
# 계획만 확인
python scripts/auto_rollout.py --scope changwon --dry-run

# 창원시 전체 자동 실행
python scripts/auto_rollout.py --scope changwon

# 경남 전체 자동 실행
python scripts/auto_rollout.py --scope gyeongnam
```

자동화 내용: Historical/Snapshot 분리, batch=5, Resume, 제한적 자동 재시도, 창원 단계 Index 보류, 경남 전체 완료 후 Composite Index 재계산, 로그/요약 JSON 저장. 자세한 내용은 `docs/AUTO_ROLLOUT_V29.md` 참고.

---

## Checkpoint 3.0 — GitHub Actions 무인 Cloud Rollout

장시간 경남 전체 Backfill을 로컬 PC가 아닌 GitHub-hosted runner에서 수행할 수 있습니다.
진행상태를 Firestore `rollout_jobs`에 저장하므로 PC를 꺼도 작업이 이어지고, GitHub Actions 한 job의
실행 한도에 닿기 전에 스스로 종료한 뒤 남은 일이 있으면 다음 `workflow_dispatch`를 자동 생성합니다.

- Workflow: `.github/workflows/cloud-rollout.yml`
- Cloud orchestrator: `scripts/cloud_rollout.py`
- 안내: `docs/GITHUB_ACTIONS_V30.md`

최초 1회 GitHub Repository Secrets:
`FIREBASE_PROJECT_ID`, `DATA_GO_KR_SERVICE_KEY`, `FIREBASE_SERVICE_ACCOUNT_JSON`

보안상 서비스계정 JSON이나 `.env`를 저장소에 커밋하지 마세요.
