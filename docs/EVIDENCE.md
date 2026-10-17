# 제출 증빙 안내

문서 갱신: **2026-10-17**. 아래 이미지는 **기존 기능 실증 당시의 실제 실행 화면**이다. 최신 화면과 디자인이 다를 수 있으며, 10월 17일 기능의 새 캡처로 간주하지 않는다.

모든 이미지는 실제 실행 화면이다. 목업·오류 화면·중간 실패 Actions는 최종 성공 증빙에서 제외했다. 사용자 제공 shot.zip의 Codex MCP 화면과 Firestore 화면, 새로 생성한 기능 실증 화면을 선별했다.

## 필수 화면

| 파일 | 보여주는 사실 |
|---|---|
| [conversation_restored.jpg](evidence/conversation_restored.jpg) | 실제 질문·GPT 답변18,425명/청년3,908명/21.21% 및 명서동 요약 |
| [personal_crud.jpg](evidence/personal_crud.jpg) | 날짜·지역·항목·21.21%·메모 저장/수정, 새로고침 후 유지, 별도 버튼 |
| [conversation_list.png](evidence/conversation_list.png) | 사용자 제공 대화 목록·불러오기 버튼(2026-10-11). 실제 10-13 복원은 아래 ui_live.json과 conversation_restored.jpg로 확인 |
| [historical_chat.jpg](evidence/historical_chat.jpg) | 사용자 제공 과거월 광화동2025-09 질문·같은 월 결과 |
| [firestore_console.png](evidence/firestore_console.png) | 사용자 Firestore Console의 실제 지역 Master. 전체 데이터 규모는 감사 JSON로 별도 확인 |

## 보너스·검증 기록

| 파일 | 의미·범위 |
|---|---|
| [mcp_codex_trend.png](evidence/mcp_codex_trend.png) | 사용자 Codex MCP 연결과 get_population_trend 호출, 가포동5,307명 |
| [mcp_codex_summary.png](evidence/mcp_codex_summary.png) | Codex get_region_summary 동일 결과 |
| [mcp_live.json](evidence/mcp_live.json) | 실제 MCP ClientSession 초기화·목록·실호출. 단순 HTTP 조회와 구분 |
| [personal_api_live.json](evidence/personal_api_live.json) | 실제 Firebase 익명 인증 API CRUD·평균/최대/최소·삭제 후 재조회·두 계정 소유자 분리 |
| [system_context_live.json](evidence/system_context_live.json) | 시스템 요약 주입 보완 후 실제 GPT 개인 기록 분석200·21.21%·1건·공식 통계 구분 |
| [api_contract_live.json](evidence/api_contract_live.json) | 실제 배포 OpenAPI 필수경로 확인 |
| [ui_live.json](evidence/ui_live.json) | 실제 UI 저장/수정/새로고침·대화/지역 복원·도구 입력 기록 |
| [final_data_index_audit.json](evidence/final_data_index_audit.json) | 48개월 실제 Firestore 값·파생지표·4지수 최종 감사 |
| [live_api_checks.json](evidence/live_api_checks.json) | 4지역×48개월 API/CSV/JSON 수치 대조 |
| [small_population_original_202609.json](evidence/small_population_original_202609.json) | 청년0%12곳과 귀현동의 원본 API·저장값 대조 |
| [historical_comparison_checks.json](evidence/historical_comparison_checks.json) | 광화동2025-09의 같은 월 비교값 대조 |

## 확정 Actions

- [인구 완료 38236688877](https://github.com/hahahoho12360/gyeongnam-ai-agent/actions/runs/38236688877)
- [비인구 완료 38256567484](https://github.com/hahahoho12360/gyeongnam-ai-agent/actions/runs/38256567484)
- [최종 감사 38327373901](https://github.com/hahahoho12360/gyeongnam-ai-agent/actions/runs/38327373901)
- [소규모 인구 원본 대조 38337713559](https://github.com/hahahoho12360/gyeongnam-ai-agent/actions/runs/38337713559)

Actions artifact에는 보관기한이 있으므로 핵심 감사·대조 JSON은 저장소에 함께 보존한다. 개인기록 숫자10·20·30은 CRUD 실증용 가상값이며 공식 통계 증빙으로 쓰지 않는다. 생성/수정 UI 캡처와 삭제 API 검증은 서로 구분한다. 과거 화면·데이터 실증과 최신 코드 자동 검증은 아래처럼 구분한다.

## 2026-10-17 최종 구현 검증

| 구분 | 근거 | 입증 범위 |
|---|---|---|
| 구현 기준 | 커밋 `74b92d02f2a460b5bf39f287a39b7cf0d3d02fb9` | 문서 개정 직전 서비스 코드 |
| 자동 검증 | [CI 실행 39009687179](https://github.com/hahahoho12360/gyeongnam-ai-agent/actions/runs/39009687179) | Python 211개 + 하위 테스트 2개 통과, 실행 결과 success |
| 지수 설명·복구 | `tests/test_index_evidence.py`, `tests/test_index_recovery.py` | 구성자료와 재계산, 결측·메타데이터 처리 |
| 그래프·기간 비교 | `tests/test_dashboard.py`, `tests/frontend/trends.test.cjs` | 8종 항목, 시작·종료값, 결측 처리 |
| 채팅·질문 예시 | `tests/test_chat_resilience.py`, `tests/test_comparison_evidence.py`, `tests/test_question_catalog.py` | 한국어 처리, 질문 주제별 비교, 데이터 기반 후보 |
| 지도 | `tests/frontend/region-map.test.cjs` | 204지역 경계, 선택·투영·표시 타일 계산 |
| 실제 화면 확인 | 10월 17일 배포 홈페이지에서 도로·건물 및 지형·등고선 전환 확인 | 해당 시점의 배경 표시 확인. 상시 가용성 시험은 아님 |

**제출 자료 해석:** 10월 13일 DB 감사 수치를 10월 17일 전체 DB 재감사 결과로 표기하지 않는다. 자동 테스트 통과는 실서비스의 모든 외부 API·네트워크 상태를 보장하지 않는다. 최종 UI를 별도 촬영할 경우 질문·기준월·배경 선택을 함께 보이게 하고 촬영일을 기록한다.
