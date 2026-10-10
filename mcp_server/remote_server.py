"""Read-only stdio MCP bridge to the deployed Changwon API; no Firebase keys."""
from __future__ import annotations
import os
from urllib.parse import urlparse
import requests
from mcp.server.fastmcp import FastMCP

BASE = os.environ.get('MCP_API_BASE_URL', 'https://gyeongnam-ai-agent.onrender.com').rstrip('/')
if urlparse(BASE).scheme != 'https' or not urlparse(BASE).netloc:
    raise ValueError('MCP_API_BASE_URL must be an HTTPS URL')
mcp = FastMCP('changwon-area-ai-remote')


def get(path: str, **params):
    response = requests.get(BASE + path, params=params, timeout=(10, 120))
    response.raise_for_status()
    return response.json()


def resolve(region: str) -> str:
    rows = get('/api/analytics/regions')
    matches = [r for r in rows if region in (str(r.get('id')), str(r.get('bjd_code')), r.get('name'), r.get('full_name'))]
    if len(matches) != 1:
        raise ValueError('Use a unique region code or full region name')
    rid = str(matches[0]['id'])
    if not rid.isdigit() or not rid.startswith('4812'):
        raise ValueError('Only Changwon regions are supported')
    return rid


def check_months(months: int):
    if not 1 <= months <= 48:
        raise ValueError('months must be between 1 and 48')


@mcp.tool()
def get_region_summary(region: str, months: int = 12) -> dict:
    """창원 지역의 저장된 실제 인구·주거·상권 요약을 읽습니다. 보완 중인 과거 월은 미완료일 수 있습니다."""
    check_months(months)
    return get(f'/api/analytics/regions/{resolve(region)}/summary', months=months)


@mcp.tool()
def get_population_trend(region: str, months: int = 12) -> dict:
    """창원 지역의 실제 월별 인구와 차트 데이터를 읽습니다. 누락값을 0으로 해석하지 마세요."""
    check_months(months)
    return get(f'/api/analytics/regions/{resolve(region)}/trend', months=months)


@mcp.tool()
def get_region_indexes(region: str) -> dict:
    """실제 저장된 4종 지수와 기준시점·산출 상태를 읽습니다. 미산출 지수는 임의로 만들지 마세요."""
    return get(f'/api/analytics/regions/{resolve(region)}/indexes')


if __name__ == '__main__':
    mcp.run(transport='stdio')
