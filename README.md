# 창원 생활 변화 AI 비서

창원시 204개 법정읍·면·동의 인구·주거·상권 자료를 질문으로 살펴보고, 개인 관찰 기록과 대화를 저장하는 AI 웹 서비스입니다. **이번 제출 범위는 창원시**이며 경남 전체 확장은 후속 과제입니다.

문서 갱신: **2026-10-17** · 기능 확인 기준: `ac03808` · 사전평가 보완: 아래 안내 참고 · 데이터 감사 기준: **2026-10-13**

## 서비스와 제출 자료

- [홈페이지](https://gyeongnam-ai-agent.vercel.app/)
- [백엔드 API](https://gyeongnam-ai-agent.onrender.com/)
- [Swagger](https://gyeongnam-ai-agent.onrender.com/docs)
- [최종 제출 보고서](docs/SUBMISSION_REPORT.md): 요구사항 대응·실증 결과·한계
- [증빙 안내](docs/EVIDENCE.md): 실제 화면과 검증 JSON
- [데이터·지수 정의](docs/DATA_METHODS.md)
- [설정·운영·MCP 안내](docs/OPERATIONS.md)

## 구현 기능

| 미션 | 구현·검증 |
|---|---|
| 데이터 기반 AI 채팅 | 저장 요약을 시스템 지침에 주입하고 OpenAI Responses API로 답변. 로딩 표시·Markdown 렌더링·조회 도구 호출 |
| 개인 기록 CRUD | 날짜·지역·자료 항목·수치·메모의 추가/목록/수정/삭제. 공식 통계와 분리 저장 |
| 대화 저장·불러오기 | 자동 저장·대화 목록·특정 대화 메시지와 분석 지역 복원·삭제 |
| 배포·문서화 | FastAPI/Render, Vanilla HTML·CSS·JS/Vercel, Firestore, Swagger |
| 보너스: 도구·멀티채널 | Function Calling + Codex stdio MCP 실제 호출 |
| 보너스: 인사이트·UX | 4개 지수 해설·산출근거, 8종 추세 그래프, 기간 비교, 경계·배경지도, CSV·JSON, 다크 모드 |

기술: Python 3.10+, FastAPI, Pydantic, firebase-admin, OpenAI, python-dotenv, MCP Python SDK. 프론트는 프레임워크 없이 구현했습니다.

## AI 일일 사용 한도

전체 이용자를 합쳐 **한국 시간 하루 최대 200회의 실제 AI API 호출**을 허용합니다. 질문 한 번에 도구 후속 답변이나 한국어 재작성 등 여러 호출이 발생할 수 있어, 질문 200개를 보장하는 뜻은 아닙니다. 한도는 한국 시간 자정에 새로 시작하며 Firestore에 저장되어 서버 재시작·재배포나 브라우저 변경으로 초기화되지 않습니다.

채팅창에서 오늘 사용량을 확인할 수 있습니다. 한도 소진 시 AI 요청은 429로 안내하고, 통계·그래프·지도·기록 조회는 계속 제공합니다. 실패·시간 초과 호출도 보수적으로 횟수에 포함합니다. 데이터베이스에서 한도를 확인·예약하지 못하면 AI 호출을 차단합니다. 이 한도는 호출 횟수 제한이며 금액·토큰 예산의 정확한 상한은 아닙니다.

## 데이터 범위와 검증

- 인구 분석 기간: **2022-10~2026-09, 48개월**. 창원 204지역 × 48개월 = **9,792개 월별 문서**.
- 인구·세대 총계: 48개월 시·5개 구 기준 대조 통과. 모든 문서에 모든 지표가 있다는 뜻은 아닙니다.
- 비인구 감사 대상 20,196개 소스·지역·월 조합: 저장 7,871 / 정상 조회 후 자료 없음 12,325 / 미조회 0.
- 매매·전월세는 월별 거래, 공동주택·건축물·상권은 현재 스냅샷입니다. 현재 스냅샷을 과거 48개월로 복제하지 않습니다.
- 4개 지수는 공식 통계가 아닌 같은 월 창원 지역 간 상대평가입니다. 구성자료 부족 시 빈 값입니다.
- 실제 0과 결측 `—`를 구분합니다. 소규모 법정동은 비율의 분자·분모를 같이 표시합니다.
- 2026-10-17 [코드 검증](https://github.com/hahahoho12360/gyeongnam-ai-agent/actions/runs/39009687179): **211개 테스트 및 하위 테스트 2개 통과**. 개인 API·화면·MCP의 기존 실증은 [증빙 목록](docs/EVIDENCE.md)에서 검증일과 범위를 확인할 수 있습니다.

위 데이터 건수는 10월 13일 보존 감사 결과입니다. 이후 자동 수집으로 바뀔 수 있으므로 현재 DB 전체 건수와 동일하다고 단정하지 않습니다.

## 홈페이지 사용 방법

1. **메인**에서 창원시 구와 법정읍·면·동을 선택하거나 자연어로 질문합니다. 예: “가포동은 어떤 동네이고, 상점과 생활환경은 어떤가요?”
2. 지역 소개와 데이터 설명, 조회된 지역 소식을 확인합니다. 비교 대상은 **선택 지역 + 유사 지역 2곳 + 무작위 비교 지역 1곳**입니다. 유사 지역은 인접 지역을 뜻하지 않습니다.
3. 시작월·종료월을 바꾸어 표의 두 시점 값과 증감을 비교합니다. 창원 평균·최대·최소는 표에 표시된 종료월 기준입니다.
4. 추세 그래프의 항목을 선택합니다. 선의 양 끝에는 각 지역의 해당 시작월·종료월 값을 표시하며, 결측을 다른 달의 값으로 대체하지 않습니다.
5. 표의 지수 이름을 누르면 **지수해설**의 해당 설명으로 이동합니다. 지수 값에 마우스를 올리거나 초점을 맞추면 구성자료·분모·가중치 등 산출근거를 확인할 수 있습니다.
6. 경계 참고도의 **배경**에서 경계만 / 도로·건물 / 지형·등고선을 선택합니다. 지역별 경계·참고 면적, 확대·이동·크게 보기를 제공합니다.
7. 개인 기록을 저장하고, 이전 대화를 불러오거나 CSV·JSON을 내려받습니다.

**그래프 8종:** 주민등록 인구, 청년 비율(20~39세), 1인세대 비율, 주민등록 세대 수, 청년 인구 수(20~39세), 1인세대 수, 60세 이상 인구 수, 20세 미만 인구 수.

아파트 ㎡당 가격·가격 전년 대비는 비교 표에서 확인하며 그래프 선택 항목에서는 제외했습니다. 업소 수는 확보된 현황 스냅샷으로 설명하고, 월별 변화를 입증할 자료가 부족하여 추세 그래프에서 제외했습니다. **20세 미만은 미성년 인구와 같은 뜻으로 사용하지 않습니다.**

지도는 2023-07-29 경계 참고자료입니다. 배경지도·통계와 기준시점이 다르며, 위성사진은 포함하지 않았습니다. 자세한 출처와 한계는 [지도 자료 설명](frontend/data/BOUNDARIES.md)을 참고하세요.

## 로컬 실행 (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env
# .env를 실제 설정으로 채웁니다. 키는 커밋하지 않습니다.
python -m uvicorn backend.main:app --reload
```

Swagger: `http://127.0.0.1:8000/docs`. 별도 터미널에서:

```powershell
$env:API_BASE_URL="http://127.0.0.1:8000"
node scripts/build-config.mjs
python -m http.server 5500 -d frontend
```

프론트: `http://127.0.0.1:5500`. Render가 아니라 로컬 API를 사용할 때 Firebase 익명 인증·서비스 계정·CORS 설정도 필요합니다. 운영 DB를 사용하는 CRUD 실습은 본인의 개인 기록만 변경합니다. `monthly_data` 원자료를 수정하지 않습니다.

## 최소 환경변수

| 변수 | 위치·역할 |
|---|---|
| `OPENAI_API_KEY` | 백엔드만: GPT 호출 비밀키 |
| `AI_DAILY_CALL_LIMIT` | 백엔드: 전체 일일 실제 AI 호출 한도. 기본 200, 0~200 허용(0은 일시 중지) |
| `OPENAI_MODEL` / `OPENAI_MAX_OUTPUT_TOKENS` | 모델·출력 길이 제한. 기본값은 코드 설정 참고 |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | 백엔드·수집 Actions: 서비스 계정 JSON 내용 또는 파일 경로 |
| `FIREBASE_PROJECT_ID` | 백엔드: 서비스 계정·웹 앱과 동일 프로젝트 |
| `FIREBASE_WEB_API_KEY` / `FIREBASE_AUTH_DOMAIN` | 백엔드가 웹 인증 설정을 제공. 서비스 계정 개인키와 다름 |
| `USE_MEMORY_DB=false` / `DEMO_SEED_ON_START=false` | 제출·운영: 실제 Firestore, 데모 자료 제외 |
| `ANALYSIS_SCOPE_PREFIX=4812` | 창원 범위 |
| `ALLOWED_ORIGINS` | Vercel 주소 및 필요한 로컬 주소를 쉼표로 구분 |
| `API_BASE_URL` | Vercel 빌드: `https://gyeongnam-ai-agent.onrender.com` |
| `ADMIN_REFRESH_TOKEN` | 서버 관리자 갱신용 비밀값. 프론트에 넣지 않음 |
| `DATA_GO_KR_SERVICE_KEY` / 소스별 설정 | 수집 Actions용. 상세 예시는 [운영 안내](docs/OPERATIONS.md) |

## 필수 API와 인증

| 기능 | 엔드포인트 |
|---|---|
| 기록 추가·목록·요약 | `POST /api/data`, `GET /api/data`, `GET /api/data/summary` |
| 기록 수정·삭제 | `PUT /api/data/{doc_id}`, `DELETE /api/data/{doc_id}` |
| 대화 저장·목록 | `POST /api/conversations`, `GET /api/conversations` |
| 대화 불러오기·삭제 | `GET /api/conversations/{doc_id}`, `DELETE /api/conversations/{doc_id}` |
| AI | `POST /api/chat` |

개인 API는 Firebase ID 토큰을 `Authorization: Bearer <ID_TOKEN>`으로 검증하고 `owner_uid`로 제한합니다. `{doc_id}`는 미션의 `{id}`와 같은 문서 ID입니다. 홈페이지는 익명 인증을 자동 연결합니다. 공개 지역 통계는 인증 없이 조회할 수 있습니다. 다른 브라우저나 브라우저 저장정보 삭제 후에는 기존 익명 기록을 복구하지 못할 수 있습니다.

## 도구 호출 흐름과 MCP

예: “명서동의 2026년 9월 인구와 청년 비율” → 기준월이 명시되어 `get_region_month` 선택 → Firestore 해당 월 조회 → 18,425명·청년 3,908명으로 계산 → 21.21% 답변 → 대화 자동 저장. 도구 이름·입력은 화면의 ‘최근 도구 호출 확인’에서 확인합니다.

MCP: Codex → 로컬 `mcp_server/remote_server.py`(stdio) → Render 읽기 전용 통계 API → Firestore. 웹과 같은 저장값을 사용하며 Firebase 개인키를 MCP에 넣지 않습니다. `/mcp` 원격 HTTPS 서버를 배포한 것은 아닙니다.

```powershell
python scripts/verify_remote_mcp.py
codex mcp add changwon-area-ai --env MCP_API_BASE_URL=https://gyeongnam-ai-agent.onrender.com -- "C:\gyeongnam-ai-agent\.venv\Scripts\python.exe" "C:\gyeongnam-ai-agent\mcp_server\remote_server.py"
codex mcp list
```

가포동 `get_population_trend(region="4812510100", months=1)`와 `get_region_summary`의 실제 결과는 **2026-09 / 5,307명**으로 일치합니다. 사용자의 Codex 호출 화면과 독립 MCP ClientSession 호출 결과를 함께 증빙합니다.

## 제출 스크린샷

아래는 기존 기능 실증 당시 화면입니다. 10월 17일 추가된 지도·지수해설·8종 그래프의 최종 화면 전체를 보여주는 자료는 아닙니다. 검증 시점과 최신 코드 근거는 [증빙 안내](docs/EVIDENCE.md)를 확인하세요.

질문·답변과 데이터 요약(실제 대화 불러오기 후):

![실제 질문·AI 답변·명서동 요약](docs/evidence/conversation_restored.jpg)

지정월 질문 전체와 답변·요약:

![광화동2025-09 실제 질문과 답변](docs/evidence/historical_chat.jpg)

개인 기록 저장·수정 후 새로고침 보존:

![개인 기록 CRUD](docs/evidence/personal_crud.jpg)

대화 불러오기 버튼·복원 상태:

![대화 목록과 불러오기](docs/evidence/conversation_list.png)

Codex MCP 실제 호출:

![Codex MCP 인구 추세 호출](docs/evidence/mcp_codex_trend.png)

## 테스트·주의점

```powershell
python -m pytest -q
node --check frontend/app.js
node --check frontend/region-map.js
node tests/frontend/index-guide.test.cjs
node tests/frontend/trends.test.cjs
node tests/frontend/region-map.test.cjs
```

Render 무료 서비스의 첫 요청·재배포 때 지연이나 일시 오류가 있을 수 있어 로딩·대기·오류 안내를 제공합니다. 장시간 부하·항상 가용성을 보장한 것은 아닙니다. 자동 갱신의 성공 여부는 실행 기록을 확인해야 하며 과거 수집 완료를 향후 갱신 성공으로 간주하지 않습니다. 저장소는 공개(Public)이며, 홈페이지 주소·저장소·보고서와 증빙을 제출하세요.


## 사전평가 보완: 실제 작동 흐름

2026-10-17 사전평가는 18/19 통과다. 전달받은 평가문에는 #1~#18만 있어 #19 미통과의 상세 사유는 확인되지 않았다. 아래 설명은 코드로 확인한 구현이며, 재평가 통과를 미리 주장하지 않는다.

- **개인 기록:** `frontend/app.js:saveRecord()` → POST/PUT `/api/data` → 인증·입력 검증 → Firestore 저장 → `loadData()`로 목록 재조회. 삭제도 성공 후 목록을 갱신한다.
- **대화 자동 저장:** `/api/chat`이 답변을 만든 뒤 사용자 질문·답변을 `conversations`에 저장한다. 홈페이지는 별도의 수동 저장 버튼이 필요 없다. `POST /api/conversations`는 API 클라이언트가 대화를 명시적으로 저장하는 별도 경로다.
- **요약 재사용:** `GET /api/data/summary`와 개인 기록 채팅이 같은 `data_summary(uid)`를 호출한다. 별도 클라이언트도 본인 인증으로 요약 API를 호출할 수 있다. 지역 채팅은 `analysis.proactive_bundle()`의 지역 요약을 사용한다.
- **오류 복구:** 채팅 실패 시 같은 페이지의 입력칸에 질문을 복원하고 ‘같은 질문 다시 시도’를 제공한다. 같은 요청 ID의 완료 결과를 재사용해 중복 처리를 줄인다. 임시 질문은 메모리에 있으므로 새로고침·탭 종료 후 복구를 보장하지 않는다. 답변 생성 후 저장 실패는 복사 안내를 표시하고, 부가 화면 갱신 실패는 도구 로그에 따로 안내한다.

```mermaid
flowchart TD
    A[본인 인증과 질문 분류] --> B[개인 기록 요약 또는 지역 분석]
    B --> C[요약 압축과 시스템 지침 구성]
    C --> D[AI 답변과 필요한 조회 도구 실행]
    D --> E[대화 저장과 화면 갱신]
```

요약 주입은 공식 자료와 개인 기록을 구분하고 계산값을 재사용하는 장점이 있다. 반면 압축 과정에서 세부 맥락이 빠질 수 있고 개인 기록의 요약·최신 메모가 외부 AI로 전송된다. 민감정보는 메모에 넣지 않는다. `store=False`는 Responses API의 응답 저장 옵션이며 모든 제공자 로그·보존까지 없어진다는 보장은 아니다. 외부 메모는 분석 자료로만 취급하도록 지시하지만 프롬프트 주입을 완전히 차단한다는 뜻은 아니다.

| 수정 목적 | 파일·함수 및 책임 |
|---|---|
| 개인 기록 항목·검증·요약 계산 | `backend/personal_records.py`: `METRICS`, `validate_record`, `summarize` |
| 개인 기록 인증·API 연결 | `backend/routers/data.py`: `list_data`, `data_summary` |
| 지역 요약·비교·채팅 분석 묶음 | `backend/analysis.py`: `summary`, `comparison_regions`, `proactive_bundle` |
| 조회 기간·그래프 | `backend/dashboard.py`: `PERIOD_MIN`, `period_bounds`, `validate_period`, `dashboard`; `frontend/app.js`: `PERIOD_MIN`, `lastClosedMonth`, `setPeriodBounds` |
| AI 컨텍스트·도구 호출 | `backend/openai_agent.py`: `_compact_context`, `run_agent` |
| 소유자 확인 | `backend/auth.py`: `required_user`, `owned` |
| 일일 호출 예약 | `backend/daily_usage.py` 및 `backend/db.py`의 저장소 구현 |

개인 기록 요약은 본인의 전체 기록을 지역·항목별로 묶고 기록 날짜의 최소~최대, 평균·최대·최소와 첫 값 대비 마지막 값의 방향을 계산한다. 지역 화면의 최근 12개월 필터와는 별개다. 지역 기간 하한은 프론트·백엔드 모두 `2022-10`, 상한은 한국 시간 직전 완료월이다. 기간을 바꿀 때 양쪽 상수와 `tests/test_dashboard.py`를 함께 확인한다.

운영 CORS 예시: `ALLOWED_ORIGINS=https://gyeongnam-ai-agent.vercel.app`

로컬 개발 예시: `ALLOWED_ORIGINS=http://127.0.0.1:5500,http://localhost:5500`

여러 출처는 쉼표로 구분하고 URL 끝에 `/`를 붙이지 않는다. 빈 목록을 `*`로 대체하지 않는다. CORS는 브라우저 출처 제어이며 사용자 인증을 대신하지 않는다. [보안·저장 정책과 콜드스타트 대응](docs/OPERATIONS.md#9-사전평가-보완-보안저장오류-정책)을 함께 확인한다.
