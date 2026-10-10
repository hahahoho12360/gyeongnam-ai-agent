# 창원 Vercel · MCP 병행 준비

인구 보완 Actions와 병행 가능. 프론트는 Render 저장값을 읽으며 재수집하지 않는다. 과거 48개월 보완과 지수 재계산이 끝나기 전 과거 추세는 최종 검증 완료로 표시하지 않는다.

## Vercel 최초 배포
1. https://vercel.com/new 에 로그인하여 Import Git Repository에서 hahahoho12360/gyeongnam-ai-agent 선택. 보이지 않으면 GitHub 연결의 저장소 접근 권한에 해당 저장소 추가.
2. Project Name: changwon-ai-agent (사용 가능할 때). Framework Preset: Other. Root Directory: 저장소 최상위(기본값), frontend로 바꾸지 않는다.
3. Build Command: node scripts/build-config.mjs. Output Directory: frontend. Install Command: 비워 둔다. 저장소 vercel.json에 동일 설정 있음. Python 백엔드는 Render에서 실행한다.
4. Environment Variables에 API_BASE_URL=https://gyeongnam-ai-agent.onrender.com 추가. Production/Preview에 적용. Firebase/API 비밀키는 넣지 않는다.
5. Deploy 클릭, Ready 확인, 실제 Production URL 복사.
6. Render 서비스 Environment에서 기존 ALLOWED_ORIGINS 목록에 위 URL의 origin(https://호스트명, 끝 / 없음)을 쉼표로 추가. 기존 값 유지. Save/redeploy 후 Live 확인.
7. Vercel 화면 새로고침, 지역 목록 표시 확인. 가포동 질문을 보내 최신 2026-09 인구 5307과 기준월 확인. 차트·CSV·JSON·대화 불러오기 직접 확인. 인구 보완 완료 후 신규 23개 지역과 읍·면의 과거 추세 재검증.

환경변수 수정 뒤 Vercel Redeploy 필요. 정적 config.js는 빌드 때 생성된다. 현재 세션에는 Vercel/Render 계정 설정을 수정할 연결 도구가 없어 1~6번은 사용자가 수행한다.

## MCP: 실제 Render 데이터를 읽는 로컬 stdio 연결
기존 mcp_server/server.py는 Firebase 직접 연결. 새 remote_server.py는 Render의 읽기 전용 API를 호출하며 Firebase 키 없이 작동한다. 두 방식은 별도이다. 새 서버는 요약·인구 추세·지수 3개 도구를 제공한다. 원격 HTTP MCP 주소 /mcp를 배포한 것은 아니다.

1. 로컬 프로젝트 터미널에서 git pull origin main. 로컬 변경이 있으면 먼저 보관한다.
2. 기존 가상환경에서 python -m pip install -r requirements.txt 실행.
3. python scripts/verify_remote_mcp.py 실행. passed는 MCP 초기 연결, 도구 목록, 가포동 최신 인구 실제 호출 성공을 뜻한다.
4. Codex CLI에서 아래 경로를 본인 실제 절대경로로 바꿔 실행한다. Python 경로는 가상환경 Python, 서버 경로는 프로젝트 파일이다.

```powershell
codex mcp add changwon-area-ai --env MCP_API_BASE_URL=https://gyeongnam-ai-agent.onrender.com -- "C:\실제경로\gyeongnam-ai-agent\.venv\Scripts\python.exe" "C:\실제경로\gyeongnam-ai-agent\mcp_server\remote_server.py"
codex mcp list
```

5. Codex를 재시작하고 'changwon-area-ai의 get_population_trend 도구로 지역코드 4812510100, months=1을 조회하고 기준월과 인구를 알려줘'라고 요청. 도구 호출 기록과 2026-09 / 5307 확인. 터미널에서 python remote_server.py만 실행하고 대기하는 것은 stdio 입력 대기로 정상이며 연결 증빙은 아니다.
6. ChatGPT 웹 커넥터에는 이 stdio 파일 경로를 그대로 넣을 수 없다. 웹 원격 MCP는 HTTPS transport와 인증을 별도로 준비해야 한다. 우선 로컬 Codex MCP 채널을 증빙한다.

## 완료 범위
Vercel 빌드 준비와 MCP 프로토콜 검증은 실제 배포/사용자 PC 호스트 연결과 구분한다. ⑫는 실제 Vercel URL의 브라우저 검증 후 완료, ⑬은 사용자 Codex에서 MCP 도구 호출 후 연결 증빙 완료로 표시한다.
