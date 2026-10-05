"""첨부 미션 요구사항을 프로젝트 코드/설정 기준으로 자동 역점검한다.

실제 계정 화면/실데이터/배포는 사람이 캡처해야 하므로 이 스크립트는
'코드에 구현돼 있는가'와 '실행 증빙이 아직 필요한가'를 구분한다.

사용:
  python scripts/submission_audit.py
  python scripts/submission_audit.py --write docs/SUBMISSION_AUDIT.md
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKS = [
    ('최종결과물', '데이터 기반 AI 채팅', ['backend/routers/chat.py', 'backend/openai_agent.py'], True),
    ('최종결과물', '(date,value,memo) CRUD', ['backend/routers/data.py', 'frontend/app.js'], True),
    ('최종결과물', '대화 저장/목록/불러오기', ['backend/routers/conversations.py', 'frontend/app.js'], True),
    ('최종결과물', '배포/문서화', ['render.yaml', 'vercel.json', 'README.md'], False),
    ('과제목표', 'FastAPI router/service 구조', ['backend/main.py', 'backend/routers', 'backend/analysis.py'], True),
    ('과제목표', 'Pydantic 입력검증', ['backend/models.py'], True),
    ('과제목표', 'Firestore CRUD', ['backend/db.py'], False),
    ('과제목표', '컨텍스트 주입', ['backend/openai_agent.py'], True),
    ('기능요구', 'FastAPI+CORS+Swagger', ['backend/main.py'], True),
    ('기능요구', 'CRUD 4 + summary', ['backend/routers/data.py'], True),
    ('기능요구', 'Conversation API', ['backend/routers/conversations.py'], True),
    ('기능요구', 'POST /api/chat + 자동저장', ['backend/routers/chat.py'], True),
    ('기능요구', 'Vanilla HTML/CSS/JS', ['frontend/index.html', 'frontend/style.css', 'frontend/app.js'], True),
    ('보너스A', 'OpenAI Function Calling', ['backend/openai_agent.py', 'backend/tooling.py'], False),
    ('보너스A', 'MCP 외부채널', ['mcp_server/server.py', '.cursor/mcp.json.example'], False),
    ('보너스B', '추가지표/통계', ['backend/metrics.py', 'backend/indexes.py'], True),
    ('보너스B', '그래프 시각화', ['frontend/app.js'], True),
    ('보너스B', 'CSV/JSON 내보내기', ['backend/routers/analytics.py', 'frontend/app.js'], True),
    ('보너스B', '다크모드', ['frontend/style.css', 'frontend/app.js'], True),
    ('개발환경', 'FastAPI backend', ['backend/main.py'], True),
    ('개발환경', 'Firestore DB', ['backend/db.py'], False),
    ('개발환경', 'GPT API', ['backend/openai_agent.py'], False),
    ('제약', 'Render 배포설정', ['render.yaml'], False),
    ('제약', 'Vercel 배포설정', ['vercel.json'], False),
    ('제약', '환경변수/키 비노출', ['.env.example', '.gitignore'], True),
    ('제약', '예외/입력검증', ['backend/models.py'], True),
]


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def build_rows():
    rows=[]
    for group, item, paths, locally_verifiable in CHECKS:
        code_ok=all(exists(p) for p in paths)
        if not code_ok:
            status='❌ 코드 누락'
        elif locally_verifiable:
            status='✅ 코드 구현'
        else:
            status='🟡 코드 구현 · 실제 계정/실행 증빙 필요'
        rows.append((group,item,status,', '.join(f'`{p}`' for p in paths)))
    return rows


def render() -> str:
    rows=build_rows()
    lines=[
        '# 최종 제출 요구사항 자동 역점검', '',
        '> 이 문서는 코드 존재 여부를 자동 점검한다. Firestore 실제 쓰기, OpenAI 실제 Tool Calling, Cursor MCP, Render/Vercel, GitHub Actions 등은 **사용자 계정에서 실제 실행·캡처**해야 최종 완료다.', '',
        '|구분|요구사항|현재 상태|구현 위치|', '|---|---|---|---|',
    ]
    for row in rows:
        lines.append('|'+ '|'.join(row) +'|')
    lines += ['', '## 실제 증빙이 완료되어야 최종 체크할 항목',
              '- Firestore 실제 컬렉션/실데이터 적재',
              '- OpenAI 실제 Function Calling (`tools_used` 포함)',
              '- Cursor MCP Tool 실호출',
              '- GitHub Actions daily/monthly 수동 실행 성공',
              '- Render `/docs` 실제 URL',
              '- Vercel 실제 서비스 URL 및 Render API 연결',
              '- CRUD/대화불러오기/그래프/다운로드/다크모드 실제 화면',
              '', '상세 캡처 목록은 `EVIDENCE_CHECKLIST.md` 참고.']
    return '\n'.join(lines)+'\n'


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--write')
    args=ap.parse_args()
    text=render()
    if args.write:
        out=Path(args.write)
        if not out.is_absolute(): out=ROOT/out
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(text,encoding='utf-8')
        print(f'작성 완료: {out}')
    else:
        print(text)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
