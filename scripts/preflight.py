"""비밀값을 출력하지 않고 실데이터 실행 준비상태를 점검한다.

예:
  python scripts/preflight.py
  python scripts/preflight.py --json
  python scripts/preflight.py --network

--network는 DATA_GO_KR_SERVICE_KEY가 있을 때 법정동코드 API를 1건 호출해
인증/네트워크를 확인한다. OpenAI 유료 생성 호출은 하지 않는다.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from scripts.collect.catalog import source_statuses


def _check_module(name: str) -> dict:
    try:
        importlib.import_module(name)
        return {'name': name, 'ok': True}
    except Exception as exc:
        return {'name': name, 'ok': False, 'detail': f'{type(exc).__name__}: {exc}'}


def _firebase_config() -> dict:
    raw = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON', '').strip()
    gac = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '').strip()
    if raw.startswith('{'):
        try:
            obj = json.loads(raw)
            ok = bool(obj.get('project_id') and obj.get('private_key') and obj.get('client_email'))
            return {'configured': ok, 'mode': 'json_secret', 'detail': 'JSON secret 구조 확인' if ok else '필수 서비스계정 필드 누락'}
        except Exception:
            return {'configured': False, 'mode': 'json_secret', 'detail': 'FIREBASE_SERVICE_ACCOUNT_JSON이 JSON 형식이 아님'}
    path = raw or gac
    if path:
        p = Path(path)
        return {'configured': p.exists(), 'mode': 'file', 'detail': str(p) if p.exists() else '지정 파일을 찾을 수 없음'}
    return {'configured': False, 'mode': None, 'detail': '서비스계정 JSON 또는 GOOGLE_APPLICATION_CREDENTIALS 미설정'}


def _network_probe() -> dict:
    key = os.getenv('DATA_GO_KR_SERVICE_KEY', '')
    if not key:
        return {'attempted': False, 'ok': False, 'detail': 'DATA_GO_KR_SERVICE_KEY 미설정'}
    try:
        import requests
        url = os.getenv('LEGAL_DONG_CODE_API_URL') or 'https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList'
        params = {'ServiceKey': key, 'pageNo': 1, 'numOfRows': 1, 'type': 'json', 'locatadd_nm': '경상남도'}
        r = requests.get(url, params=params, timeout=20)
        # URL/키는 절대 결과에 넣지 않는다.
        ok = r.ok and ('StanReginCd' in r.text or 'response' in r.text)
        return {'attempted': True, 'ok': ok, 'http_status': r.status_code, 'detail': '법정동코드 API 응답 확인' if ok else '응답 형식/승인상태 확인 필요'}
    except Exception as exc:
        return {'attempted': True, 'ok': False, 'detail': f'{type(exc).__name__}: {exc}'}


def build_report(network: bool = False) -> dict:
    py_ok = sys.version_info >= (3, 10)
    modules = [_check_module(x) for x in ('fastapi', 'uvicorn', 'firebase_admin', 'openai', 'dotenv', 'pydantic', 'requests')]
    required_paths = [
        'backend/main.py', 'frontend/index.html', 'scripts/pipeline.py', 'mcp_server/server.py',
        'render.yaml', 'vercel.json', 'README.md'
    ]
    paths = [{'path': x, 'ok': (ROOT / x).exists()} for x in required_paths]
    src = source_statuses()
    report = {
        'python': {'ok': py_ok, 'version': '.'.join(map(str, sys.version_info[:3]))},
        'dependencies': modules,
        'project_files': paths,
        'firebase': _firebase_config(),
        'openai': {
            'configured': bool(os.getenv('OPENAI_API_KEY')),
            'model': os.getenv('OPENAI_MODEL', 'gpt-6-luna'),
            'max_output_tokens': int(os.getenv('OPENAI_MAX_OUTPUT_TOKENS', '1200')),
            'note': '키 존재 여부만 점검. 유료 생성 호출은 수행하지 않음.',
        },
        'data_go_kr': {'configured': bool(os.getenv('DATA_GO_KR_SERVICE_KEY'))},
        'legal_dong_csv': {'configured': bool(os.getenv('LEGAL_DONG_CSV_PATH')), 'path': os.getenv('LEGAL_DONG_CSV_PATH','')},
        'sources': src,
    }
    if network:
        report['network_probe'] = _network_probe()
    report['ready_for_demo'] = py_ok and all(x['ok'] for x in modules if x['name'] != 'firebase_admin') and all(x['ok'] for x in paths)
    report['ready_for_live_backfill'] = (
        report['firebase']['configured'] and report['data_go_kr']['configured'] and
        next((s['configured'] for s in src if s['key'] == 'region_master'), False)
    )
    return report


def _print_human(report: dict) -> None:
    def flag(v): return 'OK' if v else 'NEEDS ACTION'
    print(f"Python {report['python']['version']}: {flag(report['python']['ok'])}")
    print(f"Firebase: {flag(report['firebase']['configured'])} ({report['firebase']['detail']})")
    print(f"OpenAI key: {flag(report['openai']['configured'])} / model={report['openai']['model']} / max_output_tokens={report['openai']['max_output_tokens']}")
    print(f"data.go.kr key: {flag(report['data_go_kr']['configured'])}")
    print('\n[Data source readiness]')
    for s in report['sources']:
        missing=[]
        missing += s['missing_all']
        missing += [' OR '.join(g) for g in s['missing_any']]
        suffix = '' if s['configured'] else f" -> {', '.join(missing) or 'manual benchmark'}"
        print(f"- {s['key']}: {flag(s['configured'])}{suffix}")
    if 'network_probe' in report:
        p=report['network_probe']; print(f"\nNetwork probe: {flag(p['ok'])} ({p['detail']})")
    print(f"\nDemo code ready: {flag(report['ready_for_demo'])}")
    print(f"Live backfill minimum ready: {flag(report['ready_for_live_backfill'])}")


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--json', action='store_true', dest='as_json')
    p.add_argument('--network', action='store_true')
    args=p.parse_args()
    report=build_report(args.network)
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
