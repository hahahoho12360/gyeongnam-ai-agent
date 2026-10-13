# 설정·운영·MCP 안내

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

기존 Daily/Monthly refresh 워크플로는 별도의 일반 갱신 경로이며 마지막 실패 이력이 있다. 최종 수집완료 증빙으로 쓰지 않는다. 향후 자동 최신화는 별도 재검증이 필요하다. 완료된48개월 자료를 삭제하거나 재수집할 이유는 아니다.

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

현재 설명은 README·SUBMISSION_REPORT·DATA_METHODS·OPERATIONS·EVIDENCE의5개 Markdown으로 통합한다. 과거 버전 문서는 현재 브랜치에서 제거하며 Git 커밋 이력으로 복구할 수 있다. API 코드·원자료·수집 캐시·완료 기록은 문서 정리 대상으로 삭제하지 않는다. 증빙 JSON에는 인증 토큰·개인키가 없어야 한다. 홈페이지 응답 속도·지연·오류는 별도로 기록하고 실제 정상 응답을 확인한다.
