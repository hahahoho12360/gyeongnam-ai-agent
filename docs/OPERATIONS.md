# 설정·운영·MCP 안내

문서 갱신: **2026-10-17** · [서비스 사용 안내](../README.md) · [검증 증빙](EVIDENCE.md)

## 1. 실행과 배포

Python3.10+ 가상환경에 requirements.txt와 requirements-dev.txt를 설치한다. README의 로컬 실행 절차를 따른다. 비밀값은 .env/Render Environment/GitHub Secrets에 두며 프론트에 넣지 않는다.

Render: 저장소 루트, Python, Build `pip install -r requirements.txt`, Start `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`, Health `/health`. Vercel: Framework Other, 루트 최상위, Build `node scripts/build-config.mjs`, Output `frontend`. 환경변수 API_BASE_URL은 Render HTTPS 주소다. 루트 vercel.json에 동일 설정이 있다.

백엔드 최소값은 README 환경변수 표 참고. ALLOWED_ORIGINS에는 `https://gyeongnam-ai-agent.vercel.app`과 필요한 로컬 origin을 쉼표로 넣는다. ADMIN_REFRESH_TOKEN은 임의의 충분히 긴 비밀값으로 설정한다. 실제 서비스 계정 개인키나 공공데이터키를 웹 apiKey 대신 입력하지 않는다.

## 2. Firebase 개인 기록 인증

1. Firebase Authentication의 익명 로그인 활성화.
2. 웹 앱 생성 후 FIREBASE_WEB_API_KEY·FIREBASE_PROJECT_ID·필요하면 FIREBASE_AUTH_DOMAIN 설정. 서비스 계정과 동일 프로젝트인지 확인.
3. 승인 도메인에 홈페이지 도메인 등록. firestore.rules는 브라우저 직접 접근을 차단한다.
4. Render 저장/재배포 후 `/api/auth/config`의 enabled 확인, 홈페이지 익명 인증 연결 상태 확인.

브라우저는 Firebase ID 토큰을 개인 API에 보낸다. 서버는 verify_id_token(check_revoked=True)와 owner_uid를 검사한다. 무인증401, 타인/없는 문서404. 인증 갱신 후1회 재시도하며 인증 검사를 제거하지 않는다. Admin SDK는 Firestore 규칙을 우회하므로 서버 소유자 검사가 필요하다. 익명 계정은 같은 브라우저 저장정보에 의존하며 다른 기기에서 기존 기록에 접근하지 못할 수 있다.

Swagger의 Authorize에는 본인 Firebase ID 토큰을 사용한다. 공공데이터 서비스키나 관리자 토큰으로 개인 API에 인증하지 않는다. 토큰을 README·스크린샷에 노출하지 않는다.

## 3. 수집 설정

`DATA_GO_KR_SERVICE_KEY`는 GitHub Secrets에만 저장한다. 기존 수집을 처음부터 재실행하지 말고 Firebase 감사·완료 기록으로 남은 항목을 확인한다. 다음 설정은 공공데이터 호출용이며 프론트 환경변수가 아니다.

| 설정 | 공식 상세기능 |
|---|---|
| POPULATION_API_URL | https://apis.data.go.kr/1741000/stdgPpltnHhStus/selectStdgPpltnHhStus |
| AGE_POPULATION_API_URL | https://apis.data.go.kr/1741000/stdgSexdAgePpltn/selectStdgSexdAgePpltn |
| SINGLE_HOUSEHOLD_API_URL | https://apis.data.go.kr/1741000/stdgSexdAgeOneHh/selectStdgSexdAgeOneHh |
| APT_LIST_API_URL | https://apis.data.go.kr/1613000/AptListService4/getLegaldongAptList4 |
| APARTMENT_BASIC_API_URL | https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5 |
| BUILDING_REGISTER_API_URL | https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo |
| APT_SALE_API_URL | https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev |
| APT_RENT_API_URL | https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent |
| COMMERCE_API_URL | https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong |
| LEGAL_DONG_CODE_API_URL | https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList |

API 개편 시 승인 명세와 실제 응답을 우선한다. 인구3소스 QUERY_JSON 예시(각 POPULATION/AGE_POPULATION/SINGLE_HOUSEHOLD_QUERY_JSON에 적용):

```json
{"stdgCd":"{bjd_code}","srchFrYm":"{yyyymm}","srchToYm":"{yyyymm}","lv":"7","regSeCd":"1","type":"JSON"}
```

최종 Actions:

- `Changwon population follow-up and ratios v3.7.6`: 월별 조회→총계 검증→저장→재조회, 완료월 재사용. 정상 월 우선 저장, 실패 월 별도 보류.
- `Changwon non-population audit and repair v3.9.2`: 승인11API/비인구5소스 감사, 페이지·기준월·지역 연결 검증, 남은 조합만 수집, 마지막 지수 재계산.
- `Changwon final data and index audit v1.1`: 실제 문서·파생지표·지수·최신 조회자료 대조. 쓰기 옵션은 목적을 확인하고 사용.

지역×소스×월의 확정 문서 ID와 작업 완료 기록을 사용한다. 매매 일반/상세를 중복 합산하지 않는다. API 실패/미연결을 no_data로 처리하지 않는다. 요청·재시도 시간 예산을 검사하고, 실패 원본과 진단에서 키를 제거한다. 구 단위 저장 그룹·월별 배치 완료 후 재조회한다.

Daily/Monthly refresh는 과거 48개월 보완 작업과 별도의 일반 갱신 경로다. 10월 17일 확인된 `_missing_config`·`_skip_row` 누락은 `scripts/update_data.py`에서 복원되어 있고 `tests/test_update_data.py`로 회귀 검증한다. 함수 복원만으로 실제 외부 수집 완료를 확정하지 않는다.

자동 갱신은 **실행 상태 → 소스별 저장/자료 없음/오류/건너뜀 → 기준월 → 파생지표·지수 → 화면 조회** 순서로 확인한다. 워크플로 성공과 모든 소스의 자료 확보는 같은 의미가 아니다. 완료된 48개월 자료를 삭제하거나 전체 재수집하지 않는다. 과거 수집완료 증빙은 해당 작업의 감사 JSON을 사용한다.

## 4. MCP 재현

`mcp_server/remote_server.py`는 로컬 stdio 서버이며 Render 읽기 API를 이용한다. Firebase 서비스 계정 없이 사용한다. 제공 도구: get_region_summary/get_population_trend/get_region_indexes. 웹 Function Calling 도구 전체를 MCP에 노출한 것은 아니지만 동일 지역 요약/추세/지수를 조회한다.

```powershell
python -m pip install -r requirements.txt
python scripts/verify_remote_mcp.py
codex mcp add changwon-area-ai --env MCP_API_BASE_URL=https://gyeongnam-ai-agent.onrender.com -- "C:\gyeongnam-ai-agent\.venv\Scripts\python.exe" "C:\gyeongnam-ai-agent\mcp_server\remote_server.py"
codex mcp list
```

Python·서버 경로는 본인의 절대경로로 바꾼다. Codex 재시작 후 요청: “changwon-area-ai의 get_population_trend로 region=4812510100, months=1을 실제 호출하고 기준월·인구를 알려줘.” 2026-09 기준5,307명이다. 기준월은 새 자료 수집 후 바뀔 수 있다. verify_remote_mcp.py는 배포 API와 결과를 대조한다. 서버만 실행해 입력을 기다리는 화면이나 ‘Added server’만으로 호출 성공이라 하지 않는다.

## 5. 증빙·문서 유지

사용·제출·운영 설명은 README·SUBMISSION_REPORT·DATA_METHODS·OPERATIONS·EVIDENCE의 5개 문서로 나누고, 지도 출처는 frontend/data/BOUNDARIES.md에서 별도로 관리한다. 과거 버전 문서는 현재 브랜치에서 제거하며 Git 커밋 이력으로 복구할 수 있다. API 코드·원자료·수집 캐시·완료 기록은 문서 정리 대상으로 삭제하지 않는다. 증빙 JSON에는 인증 토큰·개인키가 없어야 한다. 홈페이지 응답 속도·지연·오류는 별도로 기록하고 실제 정상 응답을 확인한다.

## 6. 지도 운영

- 경계 JSON은 프론트에서 자체 제공한다. 경계만 보기는 외부 배경 타일을 요청하지 않는다.
- 도로·건물은 OpenStreetMap, 지형·등고선은 OpenTopoMap 타일을 브라우저에서 직접 요청한다. 현재 설정은 별도 지도 API 키를 사용하지 않는다.
- 지도 안의 출처·저작권 표시는 유지한다. 현재 화면 타일만 요청하고 기본 캐시를 사용한다. 대량 사전 다운로드·오프라인 복제 기능은 넣지 않는다.
- 배경 로딩 실패 시 경계만 보기로 전환한다. 기관망에서 차단되면 브라우저 네트워크 오류와 제공자 도메인 접근 가능 여부를 확인한다.
- 위성사진은 미구현이다. 공급자 이용권한·인증·비용 조건을 검토한 후 별도로 연계한다.
- 경계 갱신 시 코드·명칭·좌표계·출처일·섬·내부 홀·면적을 검증한다. [지도 자료 설명](../frontend/data/BOUNDARIES.md)에 재생성 원칙을 기록한다.

## 7. 유지보수 점검 순서

| 증상 | 먼저 확인할 사항 |
|---|---|
| 지수가 비어 있음 | 해당 월 원자료, 유효 구성항목 2개 이상 여부, 방법 버전·비교범위. 결측을 0으로 채우지 않음 |
| 상점 질문에 무관한 비교 | `comparison_evidence.py`의 질문 지표 선택, 업종별 저장값·기준일, 비교지역의 같은 항목 |
| 영어 답변 또는 미완료 | 한국어 후처리·숫자/URL 보존 검사, 응답 시간·출력 길이, API 오류. 기존 저장 대화는 자동 재작성되지 않음 |
| 그래프 끝 값이 없음 | 지정 시작·종료월의 해당 지표 존재 여부. 다른 달로 대체하지 않음 |
| 지도 배경이 없음 | 배경 선택 상태·외부 타일 응답·기관망 차단. 자체 경계 표시와 분리 진단 |
| 데이터가 최신이 아님 | 자료 기준일·수집일·작업 실행일을 구분하고 소스별 저장 결과 확인 |

문서를 고칠 때에는 기능 수, 날짜, 수치, 기준 커밋, 근거 파일 링크를 함께 확인한다. 데이터 감사와 화면·API 검증은 실제 수행한 날짜로 기록한다.

## 8. AI 일일 누적 호출 제한

- 기본값: `AI_DAILY_CALL_LIMIT=200`. 환경변수 미설정 시에도 적용한다. 허용 범위는 0~200이며, 0은 AI 일시 중지다.
- 단위: 전체 이용자의 실제 OpenAI 요청 시도. 최초 요청·도구 호출 후 후속 생성·한국어 재작성 모두 각각 1회다. SDK 자동 재시도는 사용하지 않는다.
- 기간: `Asia/Seoul` 날짜별 `ai_daily_usage/YYYY-MM-DD` 문서. 자정에 새 날짜 문서를 사용하며 별도 초기화 작업은 필요하지 않다.
- 원자성: Firestore 트랜잭션 안에서 기존 횟수를 읽고 한도 미만일 때 증가시킨 뒤 AI를 호출한다. 여러 서버가 동일 문서를 공유한다.
- 실패 처리: AI 오류·시간 초과·서버 중단 후에도 예약 횟수를 환불하지 않는다. 이미 처리된 요청의 비용을 알 수 없기 때문이다. 카운터 확인 실패·잘못된 값은 503으로 차단한다.
- 화면: 채팅창의 오늘 사용량은 `GET /api/chat/usage`로 조회하며 계정·키·메시지를 포함하지 않는다. 조회 자체는 한도를 소모하지 않는다. AI 한도 초과는 429와 `Retry-After`로 알린다.
- 범위: 웹 서비스의 `openai_agent.py`를 통한 요청에 적용한다. 같은 API 키를 다른 프로그램에서 사용하면 그 호출은 이 카운터에 포함되지 않는다.
- 검증: `tests/test_daily_usage.py`에서 동시 예약, 자정 전환, 실패 시 차단, 후속 생성·번역 호출 제한, 공개 상태 조회를 검사한다.
- 최초 도입일에는 배포 이후 호출부터 집계한다. 과거 API 호출을 추정하여 소급 합산하지 않는다. 운영 중 카운터를 삭제하거나 수동으로 낮추지 않는다.

하루 200회는 소규모 사용의 상한이다. 실제 비용은 모델·입력·출력 토큰에 따라 달라지므로 사용량을 관찰한 뒤 필요하면 환경변수로 100회 등으로 낮춘다.
