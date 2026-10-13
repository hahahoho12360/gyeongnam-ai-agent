"""Initialize an actual MCP stdio session and call the deployed population tool."""
import asyncio
import json
import os
from pathlib import Path
import sys
import requests
from datetime import datetime, timezone
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
            base=os.getenv('MCP_API_BASE_URL','https://gyeongnam-ai-agent.onrender.com').rstrip('/')
            direct=requests.get(base+'/api/analytics/regions/4812510100/trend',params={'months':1},timeout=(10,120))
            direct.raise_for_status(); expected=direct.json()['rows'][-1]
            assert latest['month']==expected['month'] and latest['metrics']['population_total']==expected['metrics']['population_total']
            summary_call=await session.call_tool('get_region_summary',{'region':'4812510100','months':1})
            assert not summary_call.isError
            summary=json.loads(next(c.text for c in summary_call.content if c.type=='text'))
            assert summary['metrics']['population_total']==latest['metrics']['population_total']
            report = {'status': 'passed', 'transport': 'stdio', 'backend': os.getenv('MCP_API_BASE_URL', 'https://gyeongnam-ai-agent.onrender.com'), 'tools': [t.name for t in listed.tools], 'region_id': latest['region_id'], 'month': latest['month'], 'population_total': latest['metrics']['population_total'], 'checked_at':datetime.now(timezone.utc).isoformat(),'calls':[{'name':'get_population_trend','arguments':{'region':'4812510100','months':1}},{'name':'get_region_summary','arguments':{'region':'4812510100','months':1}}],'direct_api_matches':True,'note':'Actual initialize/list_tools/call_tool session; two deployed tools verified. Desktop Codex evidence supplied separately; this is not an HTTPS /mcp endpoint.'}
            out = ROOT / 'artifacts/deployment/remote_mcp_verification.json'
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    asyncio.run(main())
