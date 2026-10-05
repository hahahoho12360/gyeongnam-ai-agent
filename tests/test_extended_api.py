from fastapi.testclient import TestClient
from backend.main import app


def test_analytics_compare_export_and_live():
    with TestClient(app) as client:
        regions = client.get('/api/analytics/regions').json()
        assert regions
        rid = regions[0]['id']
        c = client.get(f'/api/analytics/regions/{rid}/compare?answer_mode=detail')
        assert c.status_code == 200
        body = c.json()
        assert 'summary' in body and body.get('charts')
        live = client.get(f'/api/analytics/regions/{rid}/live')
        assert live.status_code == 200
        assert live.json()['policy']['cache_first'] is True
        csv = client.get(f'/api/analytics/export/{rid}?format=csv')
        assert csv.status_code == 200
        assert 'text/csv' in csv.headers.get('content-type','')
        js = client.get(f'/api/analytics/export/{rid}?format=json')
        assert js.status_code == 200


def test_conversation_lifecycle_without_openai_key():
    with TestClient(app) as client:
        rid = client.get('/api/analytics/regions').json()[0]['id']
        r = client.post('/api/chat', json={'message':'최근 추세를 알려줘','region_id':rid,'answer_mode':'basic'})
        assert r.status_code == 200
        body = r.json(); cid = body['conversation_id']
        assert cid
        detail = client.get(f'/api/conversations/{cid}')
        assert detail.status_code == 200
        assert len(detail.json().get('messages',[])) >= 2
        assert client.delete(f'/api/conversations/{cid}').status_code == 200
