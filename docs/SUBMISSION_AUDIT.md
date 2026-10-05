# 최종 제출 요구사항 자동 역점검

> 이 문서는 코드 존재 여부를 자동 점검한다. Firestore 실제 쓰기, OpenAI 실제 Tool Calling, Cursor MCP, Render/Vercel, GitHub Actions 등은 **사용자 계정에서 실제 실행·캡처**해야 최종 완료다.

|구분|요구사항|현재 상태|구현 위치|
|---|---|---|---|
|최종결과물|데이터 기반 AI 채팅|✅ 코드 구현|`backend/routers/chat.py`, `backend/openai_agent.py`|
|최종결과물|(date,value,memo) CRUD|✅ 코드 구현|`backend/routers/data.py`, `frontend/app.js`|
|최종결과물|대화 저장/목록/불러오기|✅ 코드 구현|`backend/routers/conversations.py`, `frontend/app.js`|
|최종결과물|배포/문서화|🟡 코드 구현 · 실제 계정/실행 증빙 필요|`render.yaml`, `vercel.json`, `README.md`|
|과제목표|FastAPI router/service 구조|✅ 코드 구현|`backend/main.py`, `backend/routers`, `backend/analysis.py`|
|과제목표|Pydantic 입력검증|✅ 코드 구현|`backend/models.py`|
|과제목표|Firestore CRUD|🟡 코드 구현 · 실제 계정/실행 증빙 필요|`backend/db.py`|
|과제목표|컨텍스트 주입|✅ 코드 구현|`backend/openai_agent.py`|
|기능요구|FastAPI+CORS+Swagger|✅ 코드 구현|`backend/main.py`|
|기능요구|100개 이상 데이터 포인트 실검증|🟡 점검 API 구현 · 실데이터 적재 후 확인|`/api/meta/data-quality`|
|기능요구|CRUD 4 + summary|✅ 코드 구현|`backend/routers/data.py`|
|기능요구|Conversation API|✅ 코드 구현|`backend/routers/conversations.py`|
|기능요구|POST /api/chat + 자동저장|✅ 코드 구현|`backend/routers/chat.py`|
|기능요구|Vanilla HTML/CSS/JS|✅ 코드 구현|`frontend/index.html`, `frontend/style.css`, `frontend/app.js`|
|보너스A|OpenAI Function Calling|🟡 코드 구현 · 실제 계정/실행 증빙 필요|`backend/openai_agent.py`, `backend/tooling.py`|
|보너스A|MCP 외부채널|🟡 코드 구현 · 실제 계정/실행 증빙 필요|`mcp_server/server.py`, `.cursor/mcp.json.example`|
|보너스B|추가지표/통계|✅ 코드 구현|`backend/metrics.py`, `backend/indexes.py`|
|보너스B|그래프 시각화|✅ 코드 구현|`frontend/app.js`|
|보너스B|CSV/JSON 내보내기|✅ 코드 구현|`backend/routers/analytics.py`, `frontend/app.js`|
|보너스B|다크모드|✅ 코드 구현|`frontend/style.css`, `frontend/app.js`|
|개발환경|FastAPI backend|✅ 코드 구현|`backend/main.py`|
|개발환경|Firestore DB|🟡 코드 구현 · 실제 계정/실행 증빙 필요|`backend/db.py`|
|개발환경|GPT API|🟡 코드 구현 · 실제 계정/실행 증빙 필요|`backend/openai_agent.py`|
|제약|Render 배포설정|🟡 코드 구현 · 실제 계정/실행 증빙 필요|`render.yaml`|
|제약|Vercel 배포설정|🟡 코드 구현 · 실제 계정/실행 증빙 필요|`vercel.json`|
|제약|환경변수/키 비노출|✅ 코드 구현|`.env.example`, `.gitignore`|
|제약|예외/입력검증|✅ 코드 구현|`backend/models.py`|

## 실제 증빙이 완료되어야 최종 체크할 항목
- Firestore 실제 컬렉션/실데이터 적재
- OpenAI 실제 Function Calling (`tools_used` 포함)
- Cursor MCP Tool 실호출
- GitHub Actions daily/monthly 수동 실행 성공
- Render `/docs` 실제 URL
- Vercel 실제 서비스 URL 및 Render API 연결
- CRUD/대화불러오기/그래프/다운로드/다크모드 실제 화면

상세 캡처 목록은 `EVIDENCE_CHECKLIST.md` 참고.
