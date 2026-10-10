from backend.comparison_evidence import append_comparison

def context(period='2025-10 ~ 2026-09',value=120):
    a={'region':{'id':'a'},'period':'2025-10 ~ 2026-09','metrics':{'population_total':100}}
    return {'summary':a,'comparison':{'neighbors':[],'peers':[{'id':'b','full_name':'창원 비교동'}],'seeded_random':[]},'comparison_summaries':{'a':a,'b':{'period':period,'metrics':{'population_total':value}}}}
def test_actual_numbers_and_missing_neighbors():
    s=append_comparison('답변',context());assert '120명' in s and '+20명' in s and '실제 이웃이 없다는 뜻은 아닙니다' not in s

def test_different_period_missing_nan_are_not_computed():
    s=append_comparison('답변',context('2024-01 ~ 2024-12'));assert '+20명' not in s and '차이 계산 제외' in s
    for v in (None,float('nan'),True):assert '수치 비교 불가' in append_comparison('답변',context(value=v))

def test_incomplete_and_unresolved_preserved():
    assert append_comparison('[응답 미완료]',context())=='[응답 미완료]'
    assert append_comparison('오류',{'summary':{'error':'region_ambiguous'}})=='오류'

def test_chat_comparison_is_saved(monkeypatch):
    import importlib
    from fastapi.testclient import TestClient
    from backend.main import app
    module=importlib.import_module('backend.routers.chat')
    monkeypatch.setattr(module.analysis,'proactive_bundle',lambda *args:context())
    monkeypatch.setattr(module,'run_agent',lambda *args:('모델 답변',[]))
    with TestClient(app) as client:
        response=client.post('/api/chat',json={'message':'비교해줘','region_id':'a'})
        assert response.status_code==200
        body=response.json();assert '+20명' in body['answer']
        from backend.db import get_store
        saved=get_store().get('conversations',body['conversation_id'])
        assert saved['messages'][-1]['content']==body['answer']
