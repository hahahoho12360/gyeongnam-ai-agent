import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import required_user
from backend.db import get_store

@pytest.fixture
def clients(monkeypatch):
    app.dependency_overrides.pop(required_user,None)
    from firebase_admin import auth
    def verify(token,check_revoked=False):
        assert check_revoked
        if token not in ('alice','bob'):raise ValueError('invalid token')
        return {'uid':token}
    monkeypatch.setattr(auth,'verify_id_token',verify)
    client=TestClient(app)
    return client,{'Authorization':'Bearer alice'},{'Authorization':'Bearer bob'}


def test_missing_and_invalid_tokens_are_rejected(clients):
    c,a,b=clients
    for path in ('/api/data','/api/data/summary','/api/conversations'):
        assert c.get(path).status_code==401
        assert c.get(path,headers={'Authorization':'Bearer invalid'}).status_code==401
    assert c.post('/api/chat',json={'message':'hi'}).status_code==401
    assert c.get('/api/data/metrics').status_code==200
    assert c.get('/health').status_code==200


def test_data_isolation_and_owner_forgery(clients):
    c,a,b=clients
    data={'date':'2026-10-11','value':10,'memo':'alice record'}
    created=c.post('/api/data',headers=a,json=data)
    assert created.status_code==200
    id=created.json()['id']
    assert created.json()['owner_uid']=='alice'
    assert all(r['owner_uid']=='bob' for r in c.get('/api/data',headers=b).json())
    assert id not in {r['id'] for r in c.get('/api/data',headers=b).json()}
    assert c.put('/api/data/'+id,headers=b,json={'value':99}).status_code==404
    assert c.delete('/api/data/'+id,headers=b).status_code==404
    assert c.post('/api/data',headers=b,json={**data,'owner_uid':'alice'}).status_code==422
    assert c.put('/api/data/'+id,headers=a,json={'value':12}).status_code==200
    assert c.delete('/api/data/'+id,headers=a).status_code==200


def test_legacy_ownerless_records_are_not_exposed(clients):
    c,a,b=clients
    store=get_store();row=store.create('data',{'date':'2026-10-11','value':999999,'memo':'legacy'})
    conv=store.create('conversations',{'title':'legacy','messages':[]})
    assert row['id'] not in {r['id'] for r in c.get('/api/data',headers=a).json()}
    assert c.get('/api/conversations/'+conv['id'],headers=a).status_code==404
    assert c.delete('/api/data/'+row['id'],headers=a).status_code==404


def test_conversations_and_chat_reuse_are_owner_checked_before_ai(clients,monkeypatch):
    c,a,b=clients
    r=c.post('/api/conversations',headers=a,json={'title':'private','messages':[{'role':'user','content':'private'}]})
    id=r.json()['id']
    assert c.get('/api/conversations/'+id,headers=a).status_code==200
    assert c.get('/api/conversations/'+id,headers=b).status_code==404
    assert id not in {r['id'] for r in c.get('/api/conversations',headers=b).json()}
    import importlib
    chat=importlib.import_module('backend.routers.chat')
    def forbidden(*args):raise AssertionError('AI must not run for another owner')
    monkeypatch.setattr(chat,'run_agent',forbidden)
    assert c.post('/api/chat',headers=b,json={'message':'reuse','conversation_id':id}).status_code==404
    assert c.delete('/api/conversations/'+id,headers=b).status_code==404
    assert c.delete('/api/conversations/'+id,headers=a).status_code==200


def test_metric_validation_and_separate_summary_groups(clients,monkeypatch):
    c,a,b=clients
    monkeypatch.setattr('backend.personal_records.analysis.resolve_region',lambda id:{'id':id,'name':'테스트동'})
    base={'date':'2026-10-11','region_id':'4812110100','memo':'observation'}
    assert c.post('/api/data',headers=a,json={**base,'metric_type':'young_population_share','value':101}).status_code==422
    assert c.post('/api/data',headers=a,json={**base,'metric_type':'population_total','value':1.5}).status_code==422
    records=[]
    for metric,value in [('population_total',100),('sale_price_per_m2',1000000)]:
        r=c.post('/api/data',headers=a,json={**base,'metric_type':metric,'value':value})
        assert r.status_code==200;records.append(r.json()['id'])
    summary=c.get('/api/data/summary',headers=a).json()
    assert len(summary['groups'])>=2 and summary['metrics']=={}
    assert c.put('/api/data/'+records[0],headers=a,json={'value':None}).status_code==422
    for id in records:c.delete('/api/data/'+id,headers=a)


def test_personal_ai_context_has_only_current_users_records(clients,monkeypatch):
    c,a,b=clients
    c.post('/api/data',headers=b,json={'date':'2026-10-11','value':888888,'memo':'bob private'})
    import importlib
    chat=importlib.import_module('backend.routers.chat');seen={}
    def agent(message,context):seen.update(context);return 'personal answer',[]
    monkeypatch.setattr(chat,'run_agent',agent)
    response=c.post('/api/chat',headers=a,json={'message':'personal','analysis_target':'personal'})
    assert response.status_code==200
    assert '888888' not in str(seen)
    assert get_store().get('conversations',response.json()['conversation_id'])['owner_uid']=='alice'
