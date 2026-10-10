"""Write a compact Actions summary without exposing API credentials or raw responses."""
import json
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/population_repair'

def summary_text(out=OUT):
    path=out/'history_status.json'
    status=json.loads(path.read_text()) if path.exists() else {'status':'report_unavailable'}
    lines=['## 창원 과거 인구 수집 결과',f"- 실행 상태: {status.get('status')}",
           f"- 검증 정책: {status.get('validation_policy',os.getenv('VALIDATION_POLICY','unknown'))}",
           '- totals_first: 시 전체·5개 구 인구, 성별, 세대 총계 대조를 유지합니다. 개별 인구 결측은 null로 보존합니다.',
           '- 수집 진행 완료와 모든 지역의 자료 완전성은 별도로 판단합니다.',
           '', '| 기준월 | 총계 검증 | 알려진 인구 / 지역 수 | 미확정 결측 경고 |', '|---|---|---|---|']
    for file in sorted(out.glob('staged_validation_*.json')):
        data=json.loads(file.read_text());check=data['reconciliation'];coverage=check.get('population_coverage',{})
        lines.append(f"| {file.stem.removeprefix('staged_validation_')} | {check['status']} | {coverage.get('known','—')} / {coverage.get('master','—')} | {len(check.get('warnings',[]))} |")
        if check['status']=='failed':
            lines.append(f"\n실패 상세는 `{file.name}`의 `problems`에서 확인하세요.\n")
    lines.extend(['','개별 지역의 0명 확정·최신월 값을 과거로 복사·API 실패 무시는 수행하지 않습니다.'])
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    text=summary_text();print(text)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:f.write(text)
