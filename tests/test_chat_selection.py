from backend.chat_selection import select_region

def test_explicit_region_overrides_selection(monkeypatch):
    monkeypatch.setattr('backend.chat_selection.analysis.list_regions',lambda:[{'id':'4812311700','name':'적현동'},{'id':'4812311800','name':'가포동'}])
    assert select_region('가포동을 분석해줘','4812311700')==('4812311800',[])
    assert select_region('추세를 설명해줘','4812311700')==('4812311700',[])

def test_duplicate_name_requires_qualification(monkeypatch):
    rows=[{'id':'a','name':'중앙동','sigungu':'성산구'},{'id':'b','name':'중앙동','sigungu':'진해구'}]
    monkeypatch.setattr('backend.chat_selection.analysis.list_regions',lambda:rows)
    assert select_region('중앙동 분석','a')==(None,rows)
    assert select_region('진해구 중앙동 분석','a')==('b',[])

def test_personal_summary_is_used_and_saved(monkeypatch):
    import importlib
    from fastapi.testclient import TestClient
    from backend.main import app
    module=importlib.import_module('backend.routers.chat')
    seen={}
    monkeypatch.setattr(module,'data_summary',lambda:{'count':2,'metrics':{'average':15}})
    def agent(message,context):
        seen.update(context)
        return '기록 분석',[]
    monkeypatch.setattr(module,'run_agent',agent)
    with TestClient(app) as client:
        body=client.post('/api/chat',json={'message':'내 기록 분석','analysis_target':'personal'}).json()
        assert seen['personal_data_summary']['metrics']['average']==15
        assert body['resolved_region'] is None and body['analysis_target']=='personal'
        from backend.db import get_store
        assert get_store().get('conversations',body['conversation_id'])['analysis_target']=='personal'
