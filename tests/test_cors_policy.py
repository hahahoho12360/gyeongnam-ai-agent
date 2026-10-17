"""Check configured browser origins on success and sanitized error responses."""
import os
import subprocess
import sys
import pytest


@pytest.mark.parametrize('origins,origin,allowed', [
    ('', 'https://untrusted.example', False),
    ('https://gyeongnam-ai-agent.vercel.app', 'https://untrusted.example', False),
    ('https://gyeongnam-ai-agent.vercel.app', 'https://gyeongnam-ai-agent.vercel.app', True),
])
def test_origin_policy(origins, origin, allowed):
    # Import in a fresh process: CORS middleware reads settings at startup.
    script = '''
import asyncio, sys
from fastapi.testclient import TestClient
from starlette.requests import Request
from backend.main import app, safe_server_error
origin, allowed = sys.argv[1], sys.argv[2] == 'True'
with TestClient(app) as client:
    response = client.get('/health', headers={'Origin': origin})
    assert response.status_code == 200
    assert (response.headers.get('access-control-allow-origin') == origin) == allowed
    preflight = client.options('/api/data', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST'})
    assert preflight.status_code == (200 if allowed else 400)
request = Request({'type': 'http', 'method': 'GET', 'path': '/health', 'headers': [(b'origin', origin.encode())]})
error = asyncio.run(safe_server_error(request, RuntimeError('test only')))
assert error.status_code == 503
assert (error.headers.get('access-control-allow-origin') == origin) == allowed
'''
    result = subprocess.run([sys.executable, '-c', script, origin, str(allowed)],
                            env={**os.environ, 'ALLOWED_ORIGINS': origins}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
