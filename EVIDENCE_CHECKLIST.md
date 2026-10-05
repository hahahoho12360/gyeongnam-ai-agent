# 실제 사람이 캡처해야 하는 증빙사진 체크리스트

아래 항목은 ChatGPT가 계정 로그인 화면을 대신 캡처할 수 없으므로 **사용자가 실제 실행 후 캡처**해야 한다. README에도 동일 체크리스트가 있다.

- [ ] 1. FastAPI 로컬 `/docs` — CRUD 5개 + conversation + chat + analytics 엔드포인트가 보이는 화면
- [ ] 2. Firestore Console — `data`, `conversations`, `monthly_data`, `regions` 컬렉션이 실제 생성된 화면 (비밀키 노출 금지)
- [ ] 3. 데이터 CRUD — 웹에서 데이터 추가 후 목록 갱신 + 삭제 또는 수정 장면
- [ ] 4. 데이터 기반 AI 채팅 — 질문, 로딩, 답변, 기준시점/신뢰도, 그래프가 함께 보이는 화면
- [ ] 5. 대화 기록 — 이전 대화 목록에서 특정 대화를 다시 불러온 화면
- [ ] 6. Function Calling — `/api/chat` 응답의 `tools_used` 또는 개발 로그에서 실제 도구명이 확인되는 화면
- [ ] 7. Cursor MCP — Cursor가 `get_region_summary`/`compare_regions` 등 MCP Tool을 호출한 화면
- [ ] 8. CSV 또는 JSON 내보내기 — 다운로드된 파일과 앱 버튼
- [ ] 9. 다크모드 — 토글 전/후 중 한 화면
- [ ] 10. Render — 배포 성공 + `https://.../docs`
- [ ] 11. Vercel — 실제 서비스 URL에서 앱이 열린 화면
- [ ] 12. GitHub Actions — 데이터 갱신 workflow 수동 실행 성공 화면

> 캡처 전에 API키, Firebase private key, 서비스 계정 JSON, 환경변수 Secret 값이 화면에 보이지 않는지 확인한다.
