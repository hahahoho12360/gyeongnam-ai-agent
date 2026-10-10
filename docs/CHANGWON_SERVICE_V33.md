# Checkpoint 3.3 — 창원 실데이터 서비스 연결 검증

## 변경 내용
- Render/환경변수의 ANALYSIS_SCOPE_PREFIX=4812로 서비스 지역 선택·이름 해석·비교·시계열 조회를 창원 범위로 제한한다. 수집 파이프라인 범위는 변경하지 않는다.
- v3.2 index_meta를 요약·지수 API·Function Calling 결과·AI 요약 컨텍스트까지 전달한다.
- 화면에 4개 지수, 비교월, 창원 비교모집단, 비공식 프로젝트 지수와 상권 Proxy 한계를 표시한다.
- 간단 응답에도 12개월 추세 그래프를 생성한다. 인접·Peer·seeded random을 비교 요약/그래프에서 누락하지 않는다.
- /api/meta/changwon-mvp는 rollout_reports/changwon_v32_final 한 문서만 읽는다. 리포트 집계는 generated_at 시점 기준이다.
- 읽기 전용 Firebase 서비스 검증 스크립트와 GitHub Actions workflow를 추가한다.

## 적용
이 ZIP에는 변경 파일만 있다. 기존 저장소 루트에 같은 경로로 덮어쓴다. 기존 .env 및 Firebase 키는 유지한다.

기존 .env에는 아래 한 줄을 추가한다.

```dotenv
ANALYSIS_SCOPE_PREFIX=4812
```

그 뒤 저장소 루트에서 실행한다.

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
git add backend frontend render.yaml .env.example scripts/verify_changwon_service.py .github/workflows/changwon-service.yml tests docs/CHANGWON_SERVICE_V33.md WORK_STATUS.md
git commit -m "Connect Changwon MVP metadata and service verification v3.3"
git push origin main
```

GitHub Actions에서 **Changwon service verify v3.3** → Run workflow를 실행한다. 기존 v3.2와 같은 FIREBASE_SERVICE_ACCOUNT_JSON/FIREBASE_PROJECT_ID Secrets를 사용한다. OpenAI 키는 이 검증에 사용하지 않는다.

성공하면 `changwon-v33-service-report` artifact를 내려받는다. 실패하면 첫 번째 오류를 확인한다. 검증 스크립트는 공공데이터를 다시 수집하거나 Firestore 자료를 수정하지 않는다.

## 검증의 범위
자동테스트는 MemoryStore로 CRUD·대화·API·도구 연결을 점검한다. Firebase 검증은 저장된 v3.2 품질 보고서, 현재 창원 Master, 대표지역 지수 메타데이터, 간단 추세, CSV/JSON 응답을 점검한다. 전체 181개 지역의 값/모든 API 조합을 재검증하는 시험은 아니다.

검증 결과: 자동테스트 49개 통과, Python compile 및 JavaScript 문법 검사 통과.

현재 작업환경에서는 사용자 Firebase 비밀키와 배포 URL을 사용할 수 없어 실데이터 워크플로·OpenAI 실제 호출·Render/Vercel 배포·MCP 실제 호출은 아직 실행하지 않았다. GitHub 연결 도구는 읽기만 제공하므로 원격 push도 수행하지 않았다.

## 다음 실행
위 워크플로 성공 후 Render에 ANALYSIS_SCOPE_PREFIX=4812, USE_MEMORY_DB=false, DEMO_SEED_ON_START=false를 설정하고 기존 Firebase/OpenAI/CORS 설정을 연결한다. Vercel의 API_BASE_URL과 Render의 ALLOWED_ORIGINS를 실제 배포 URL에 맞춘다. /health, /docs, /api/meta/changwon-mvp를 확인한 후 실제 채팅의 tools_used 및 대화 저장/불러오기를 검증한다.
