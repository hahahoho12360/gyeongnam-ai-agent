"""Initialize an actual MCP stdio session and call the deployed population tool."""
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT = Path(__file__).resolve().parents[1]

async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'mcp_server/remote_server.py')], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            result = await session.call_tool('get_population_trend', {'region': '4812510100', 'months': 1})
            if result.isError:
                raise RuntimeError('MCP tool returned an error')
            payload = json.loads(next(c.text for c in result.content if c.type == 'text'))
            rows = payload['rows']
            latest = rows[-1]
            assert latest['region_id'] == '4812510100'
            assert latest['month'] == '2026-09'
            assert latest['metrics']['population_total'] == 5307
            report = {'status': 'passed', 'transport': 'stdio', 'backend': os.getenv('MCP_API_BASE_URL', 'https://gyeongnam-ai-agent.onrender.com'), 'tools': [t.name for t in listed.tools], 'region_id': latest['region_id'], 'month': latest['month'], 'population_total': latest['metrics']['population_total'], 'note': 'One live region checked; historical completeness and desktop host integration not verified.'}
            out = ROOT / 'artifacts/deployment/remote_mcp_verification.json'
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    asyncio.run(main())
