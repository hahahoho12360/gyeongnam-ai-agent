# Checkpoint 1.4 검증 보고서

검증 대상: 코드 구조·데모모드 기능·문법·수집 adapter·Function Calling orchestration·자동화 설정

## 자동 검증 결과
- `python -m compileall -q backend scripts mcp_server` : **PASS**
- `pytest -q` : **20 passed**
- `node --check frontend/app.js` : **PASS**
- `node --check scripts/build-config.mjs` : **PASS**

테스트 범위:
- FastAPI root
- CRUD 생성/조회/수정/삭제
- 데이터 summary
- 능동 분석 compare/detail + chart 반환
- Cache-First live endpoint
- CSV/JSON export
- 채팅/대화 저장/상세/삭제(키 미설정 시 안전한 안내 응답)
- 시계열 분석·비교 로직
- 주요 API XML parser/실거래·상권·건축물 adapter
- 성별 분리 10세 연령대 → 20~39 / 60+ 합산
- 성·연령별 1인세대 합산
- 1~10+ 세대원수 합산, 출생-사망 자연증감
- 고연령 65+ 정확값 / 60+ Proxy 구분
- 도메인별 Function Tool이 동일 analysis backend를 사용함
- `store=false` Responses Function Calling의 stateless replay 구조
- 공식 전국 법정동 CSV의 경남 법정동/읍·면 추출 및 리 제외(roll-up) 규칙
- Secret 비노출 readiness/source-status endpoint
- 데이터 품질 리포트: 100포인트, 지역/월 커버리지, freshness/confidence

## 이번 Checkpoint에서 해결한 중요 오류/위험
1. 일부 지표가 `None`일 때 `share()`가 TypeError를 낼 수 있던 sparse-data 오류를 수정.
2. 성·연령 원자료가 남/여 분리 컬럼만 줄 때 청년인구가 계산되지 않는 문제를 보완.
3. 10세 구간만으로 65+를 정확 계산할 수 없는 경우 60+를 **Proxy라고 명시**하도록 수정.
4. 최근 실거래만 잠정치로 표시하고 오래된 과거월까지 영구 `is_provisional=true`가 되는 문제를 수정.
5. 현재월 실거래의 `source_as_of`가 미래 월말로 기록될 수 있는 문제를 수정.
6. OpenAI `store=false`와 `previous_response_id`를 함께 쓰는 상태관리 위험을 제거하고 stateless sequence replay 방식으로 변경.
7. 같은 동명이 여러 시군에 있을 때 첫 후보를 임의 선택하지 않고 ambiguity를 반환하도록 유지.

## 현재 환경에서 미검증인 항목
1. **실 공공데이터 호출**: 사용자 승인 서비스키/상세명세가 이 작업환경에 없으므로 실제 네트워크 수집은 수행하지 않음.
2. **실 Firestore 쓰기**: 사용자 서비스계정 비밀값을 이 작업환경에 복사하지 않았으므로 실제 계정 쓰기는 수행하지 않음.
3. **실 OpenAI 과금 호출**: 사용자 비밀키를 파일에 넣지 않았으므로 실제 Function Calling 호출은 수행하지 않음. 대신 가짜 SDK 응답으로 orchestration unit test를 통과함.
4. **MCP runtime**: 로컬 사용자의 `.venv`에서 `pip install -r requirements.txt` 후 Cursor로 실제 stdio Tool 호출을 검증해야 함.
5. **실 경계 adjacency**: `scripts/build_neighbors.py` 구현/컴파일 완료. 공식 법정구역 GeoJSON을 받은 뒤 실제 경남 경계로 실행해야 함.
6. Render/Vercel/GitHub Actions: 사용자 로그인/Secret 입력이 필요한 실제 배포는 사용자 환경에서 수행하고 캡처해야 함.

## 보안 검증
- `.env`, Firebase service account 패턴, `frontend/config.js`, backfill state는 Git 제외 대상.
- 실제 API Key/서비스 계정키를 코드·README에 넣지 않도록 예제값만 제공.
- `preflight.py`는 키 값이 아니라 존재/구조/준비 여부만 출력.
- 최종 증빙은 Secret 값이 보이지 않도록 캡처한다.

## 실제 Uvicorn 런타임 Smoke Test
Checkpoint 1.4에서 메모리 데모 모드로 Uvicorn을 실제 구동해 HTTP 요청까지 확인했다.

- `/health` → 200
- `/api/analytics/regions` → 데모 지역 반환
- `/api/analytics/regions/{id}/compare?answer_mode=detail` → summary + 2 charts
- `POST /api/data` → `/api/data/summary` → `DELETE` CRUD round-trip
- `POST /api/chat` → OpenAI 키 미설정 시 안전 fallback + conversation 자동 생성
- `/openapi.json` → `/api/chat`, `/api/data/summary` 포함 확인

실 OpenAI/Firestore/공공데이터 네트워크 검증은 Secret이 필요한 별도 단계이다.
