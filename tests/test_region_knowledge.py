from types import SimpleNamespace
from backend import region_knowledge as knowledge
from backend.openai_agent import _compact_context, SYSTEM

def region():return {'id':'4812110100','name':'명서동','sigungu':'창원시 의창구','full_name':'창원시 의창구 명서동'}

def test_external_background_source_budget_and_cached(monkeypatch):
    knowledge._CACHE.clear();calls=[]
    def get(*args,**kwargs):
        calls.append(args)
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'query':{'pages':{'1':{'title':'명서동 (창원시)','extract':'명서동은 창원시 의창구의 법정동이다. 동네 배경을 소개한다.'}}}})
    monkeypatch.setattr(knowledge.requests,'get',get)
    a=knowledge.introduction_context(region(),'simple');b=knowledge.introduction_context(region(),'detail')
    assert a['sentence_limit']==1 and b['sentence_limit']==3 and len(calls)==1
    assert a['status']=='external_background'
    assert a['sources'][0]['url'].startswith('https://ko.wikipedia.org/wiki/')
    compact=_compact_context({'summary':{},'region_introduction':a})
    assert compact['region_introduction']==a

def test_other_city_administrative_dong_or_district_rejected(monkeypatch):
    for title,text in [('명서동','부산의 명서동이다.'),('명곡동 (창원시)','창원시 의창구 명서동을 관할한다.'),('명서동','창원시 마산합포구의 법정동이다.')]:
        knowledge._CACHE.clear()
        monkeypatch.setattr(knowledge.requests,'get',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'query':{'pages':{'1':{'title':title,'extract':text}}}}))
        assert knowledge.introduction_context(region())['status']=='no_external_match'

def test_network_failure_does_not_abort_chat(monkeypatch):
    knowledge._CACHE.clear()
    def fail(*args,**kwargs):raise knowledge.requests.Timeout()
    monkeypatch.setattr(knowledge.requests,'get',fail)
    assert knowledge.introduction_context(region())['status']=='external_unavailable'
    assert '확신이 없는' in SYSTEM and '최대 3문장' in SYSTEM
    assert '인근·인접 지역 비교는 제공하지 않으며' in SYSTEM
