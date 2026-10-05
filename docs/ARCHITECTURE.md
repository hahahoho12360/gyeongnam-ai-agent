# 아키텍처

```text
공공 API ──> Python ETL/집계 ──> Firestore 월별 Aggregate ──> FastAPI ──> Vanilla JS/Vercel
   │                                    │                      │
   └──────── 필요 시 Live Overlay ──────┘                      └─ OpenAI Function Calling
                                                                   │
Cursor ── stdio MCP ── mcp_server/server.py ── 같은 analysis/tool 함수 ┘
```

## 역할 분리
- 공공 API: 사실의 원천
- Python: 정제·통계·파생지표·비교군
- Firestore: 역사 Snapshot과 대화기록
- FastAPI: API 경계, Pydantic 검증, CORS
- GPT: 질문 의도·도구 선택·설명
- Frontend: 입력, 로딩, 그래프, CRUD, 기록, CSV/JSON, 다크모드

## 최신성
Scheduled Refresh + On-demand Refresh + Manual Refresh를 병행한다. Cache-First로 저장자료가 충분히 최신이면 재사용하고, TTL 초과 소스는 원 API 갱신 경로를 탄다.
