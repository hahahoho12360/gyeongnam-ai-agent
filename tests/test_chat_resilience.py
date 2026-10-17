import importlib
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.main import app
from backend.openai_agent import contains_english_prose, korean_answer

chat = importlib.import_module('backend.routers.chat')

def test_english_translation_preserves_numbers():
    source='This neighborhood has a population of 154 people.'
    def client(text):
        return SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:SimpleNamespace(output_text=text,status='completed')))
    assert contains_english_prose(source)
    assert not contains_english_prose('API 자료로 확인한 인구는 154명입니다.')
    assert korean_answer(source,client('이 지역의 인구는 154명입니다.'))=='이 지역의 인구는 154명입니다.'
    assert '오류' in korean_answer(source,client('이 지역의 인구는 155명입니다.'))

def test_retry_is_idempotent_and_preserves_history(monkeypatch):
    calls=[]
    monkeypatch.setattr(chat,'data_summary',lambda uid:{})
    monkeypatch.setattr(chat,'run_agent',lambda message,context:(calls.append((message,context)) or '한국어 답변',[]))
    payload={'message':'내 자료 분석','analysis_target':'personal','request_id':uuid4().hex}
    with TestClient(app) as client:
        first=client.post('/api/chat',json=payload)
        second=client.post('/api/chat',json=payload)
        assert first.status_code==200 and first.json()==second.json()
        assert len(calls)==1
        response=client.post('/api/chat',json={**payload,'message':'더 설명해줘','request_id':uuid4().hex,'conversation_id':first.json()['conversation_id']})
        assert response.status_code==200
        assert calls[-1][1]['conversation_history'][0]['content']=='내 자료 분석'
        assert client.post('/api/chat',json={**payload,'message':'다른 질문'}).status_code==409

def test_unhandled_failure_has_korean_body_and_cors(monkeypatch):
    def fail(*args): raise RuntimeError('private internal details')
    monkeypatch.setattr(chat,'data_summary',fail)
    request_id=uuid4().hex
    from backend.config import settings
    origin=(settings.allowed_origins or ['http://localhost:8000'])[0]
    if origin=='*': origin='http://localhost:8000'
    with TestClient(app,raise_server_exceptions=False) as client:
        response=client.post('/api/chat',headers={'Origin':origin},json={'message':'내 자료','analysis_target':'personal','request_id':request_id})
        assert response.status_code==503
        assert response.json()['request_id']==request_id
        assert 'private' not in response.text
        assert response.headers['access-control-allow-origin']==origin

def test_ambiguous_region_retains_original_question(monkeypatch):
    rows=[{'id':'a','name':'신포동1가'},{'id':'b','name':'신포동2가'}]
    monkeypatch.setattr('backend.chat_selection.analysis.list_regions',lambda:rows)
    monkeypatch.setattr(chat.analysis,'resolve_region',lambda rid:next((r for r in rows if r['id']==rid),None))
    monkeypatch.setattr(chat.analysis,'proactive_bundle',lambda *args:{})
    monkeypatch.setattr(chat,'introduction_context',lambda *args:{})
    monkeypatch.setattr(chat,'recent_news',lambda *args:{'status':'unavailable','items':[]})
    seen=[]
    monkeypatch.setattr(chat,'run_agent',lambda message,context:(seen.append(message) or '여성 1인세대 분석입니다.',[]))
    with TestClient(app) as client:
        first=client.post('/api/chat',json={'message':'신포동 여성 1인세대 분석해줘'}).json()
        assert len(first['region_candidates'])==2
        second=client.post('/api/chat',json={'message':'신포동1가','conversation_id':first['conversation_id']})
        assert second.status_code==200
        assert '여성 1인세대' in seen[0] and '신포동1가' in seen[0]
