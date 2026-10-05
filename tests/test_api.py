from fastapi.testclient import TestClient
from backend.main import app
client=TestClient(app)
def test_root_and_crud():
    assert client.get('/').status_code==200
    c=client.post('/api/data',json={'date':'2026-10-01','value':10,'memo':'x'}); assert c.status_code==200
    doc=c.json()['id']; assert client.get('/api/data').json()
    assert client.put('/api/data/'+doc,json={'value':12}).status_code==200
    assert client.get('/api/data/summary').json()['count']>=1
    assert client.delete('/api/data/'+doc).status_code==200
