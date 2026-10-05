from fastapi.testclient import TestClient
from backend.main import app


def test_safe_readiness_endpoint_does_not_expose_secret_values():
    with TestClient(app) as client:
        r=client.get('/api/meta/readiness')
        assert r.status_code==200
        body=r.json()
        assert body['db_mode']=='memory'
        assert isinstance(body['sources'],list) and body['sources']
        text=r.text
        assert 'OPENAI_API_KEY' not in text
        assert 'DATA_GO_KR_SERVICE_KEY' not in text


def test_source_status_endpoint():
    with TestClient(app) as client:
        r=client.get('/api/meta/source-status')
        assert r.status_code==200
        assert isinstance(r.json(),list)
