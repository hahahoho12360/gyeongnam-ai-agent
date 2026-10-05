# Function Calling + MCP 멀티채널

내부 웹 채널과 외부 MCP 채널이 **같은 `backend/tooling.py → backend/analysis.py`** 함수를 사용한다. 계산을 LLM에게 맡기지 않고 Python 결과만 설명하게 하는 것이 원칙이다.

## Function Calling 흐름
1. `/api/chat`가 OpenAI Responses API에 사용자 질문과 Tool schema 전송
2. 모델이 질문에 맞는 Tool 선택
3. 서버가 Python 함수를 실행
4. `function_call_output`을 모델에 반환
5. 모델이 최종 한국어 설명 생성

현재 Tool:
- `get_region_summary`
- `get_population_trend`
- `get_housing_market`
- `get_rental_market`
- `get_commerce_trend`
- `get_auction_market`
- `compare_regions`
- `get_region_indexes`
- `get_live_area_snapshot`

## Stateless Responses 설계
`store=false`를 사용해 OpenAI 응답 자체를 별도 서버 저장하지 않는다. 그래서 Tool 왕복에서 `previous_response_id`에 의존하지 않고 **이전 `response.output`(reasoning/function_call 포함) + `function_call_output` 전체를 다음 요청에 다시 전달**한다. 실제 대화 영속성은 과제 요구대로 Firestore `conversations`가 담당한다.

## MCP 흐름
Cursor → `.cursor/mcp.json` → `mcp_server/server.py`(stdio) → 같은 `dispatch()` → Firestore

웹 Function Calling과 MCP는 별도 분석 코드를 만들지 않는다. 같은 Tool 결과를 사용해야 웹과 Cursor의 수치가 일치한다.

## README 증빙에 남길 것
- 웹 질문/답변 화면
- OpenAI Tool 사용 기록(`tools_used` 응답 또는 개발 로그)
- Cursor에서 MCP Tool이 실제 호출된 화면
- 동일 지역/동일 질의에서 웹과 MCP가 같은 기반 데이터를 반환한다는 설명
