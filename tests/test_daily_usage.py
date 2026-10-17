from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
import importlib
import sys
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend import daily_usage as quota
from backend.db import MemoryStore, FirestoreStore
from backend.main import app
from backend import openai_agent as agent

@pytest.fixture
def counter(monkeypatch):
    store=MemoryStore()
    monkeypatch.setattr(quota,'get_store',lambda:store)
    monkeypatch.setattr(quota,'settings',SimpleNamespace(ai_daily_call_limit=200))
    return store


def test_atomic_global_limit_across_concurrent_requests(counter):
    def attempt(_):
        try:quota.reserve_call();return True
        except HTTPException as e:
            assert e.status_code==429 and int(e.headers['Retry-After'])>0
            return False
    with ThreadPoolExecutor(max_workers=24) as pool:
        accepted=list(pool.map(attempt,range(250)))
    assert sum(accepted)==200
    assert quota.usage_status()['used']==200
    assert quota.usage_status()['remaining']==0


def test_kst_midnight_starts_new_bucket(counter):
    before=datetime(2026,10,17,14,59,59,tzinfo=timezone.utc)
    after=datetime(2026,10,17,15,0,0,tzinfo=timezone.utc)
    quota.reserve_call(before)
    assert quota.usage_status(before)['date']=='2026-10-17'
    assert quota.usage_status(before)['used']==1
    assert quota.usage_status(after)['date']=='2026-10-18'
    assert quota.usage_status(after)['used']==0
    assert quota.usage_status(after)['reset_at']=='2026-10-19T00:00:00+09:00'


def test_invalid_counter_or_store_blocks_calls(counter,monkeypatch):
    day=quota.window()[0]
    counter.set(quota.COLLECTION,day,{'used':-1})
    with pytest.raises(HTTPException) as e:quota.reserve_call()
    assert e.value.status_code==503
    monkeypatch.setattr(quota,'get_store',lambda:object())
    with pytest.raises(HTTPException) as e:quota.reserve_call()
    assert e.value.status_code==503


def test_provider_failure_keeps_reservation_and_retry_counts(counter,monkeypatch):
    calls=[]
    def create(**kwargs):calls.append(kwargs);raise TimeoutError('upstream failed')
    client=SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=lambda **kw:client))
    monkeypatch.setattr(agent,'settings',SimpleNamespace(openai_api_key='test',openai_model='test',openai_max_output_tokens=100))
    for _ in range(2):
        with pytest.raises(TimeoutError):agent.run_agent('내 자료',{'personal_data_summary':{}})
    assert len(calls)==2 and quota.usage_status()['used']==2


def test_quota_blocks_initial_and_translation_provider_calls(counter,monkeypatch):
    monkeypatch.setattr(quota,'settings',SimpleNamespace(ai_daily_call_limit=0))
    calls=[]
    client=SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:calls.append(kw)))
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=lambda **kw:client))
    monkeypatch.setattr(agent,'settings',SimpleNamespace(openai_api_key='test',openai_model='test',openai_max_output_tokens=100))
    with pytest.raises(HTTPException) as e:agent.run_agent('내 자료')
    assert e.value.status_code==429
    with pytest.raises(HTTPException) as e:agent.korean_answer('This is a complete English response about the neighborhood.',client)
    assert e.value.status_code==429
    assert calls==[]


def test_followup_tool_call_is_counted_and_stopped(counter,monkeypatch):
    monkeypatch.setattr(quota,'settings',SimpleNamespace(ai_daily_call_limit=1))
    calls=[]
    item=SimpleNamespace(type='function_call',name='get_region_summary',arguments='{}',call_id='call')
    response=SimpleNamespace(output=[item],output_text='',status='completed')
    def create(**kwargs):calls.append(kwargs);return response
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=lambda **kw:SimpleNamespace(responses=SimpleNamespace(create=create))))
    monkeypatch.setattr(agent,'settings',SimpleNamespace(openai_api_key='test',openai_model='test',openai_max_output_tokens=100))
    monkeypatch.setattr(agent,'dispatch',lambda *args:{'population':1})
    with pytest.raises(HTTPException) as e:agent.run_agent('인구')
    assert e.value.status_code==429 and len(calls)==1
    assert quota.usage_status()['used']==1


def test_public_usage_is_read_only_and_chat_returns_429(counter,monkeypatch):
    chat=importlib.import_module('backend.routers.chat')
    monkeypatch.setattr(quota,'settings',SimpleNamespace(ai_daily_call_limit=0))
    monkeypatch.setattr(chat,'data_summary',lambda uid:{})
    monkeypatch.setattr(chat,'run_agent',lambda *args:quota.reserve_call())
    with TestClient(app) as client:
        for _ in range(2):
            status=client.get('/api/chat/usage')
            assert status.status_code==200 and status.json()['used']==0
            assert status.headers['cache-control']=='no-store'
        response=client.post('/api/chat',json={'message':'내 자료','analysis_target':'personal'})
        assert response.status_code==429
        assert 'Retry-After' in response.headers and '통계' in response.json()['detail']


def test_firestore_transaction_shared_across_store_instances(monkeypatch):
    from google.cloud import firestore
    data={}; events=[]
    class Ref:
        def get(self,transaction):
            events.append('read')
            return SimpleNamespace(exists=bool(data),to_dict=lambda:dict(data))
    class Tx:
        def set(self,ref,row):events.append('write');data.update(row)
    client=SimpleNamespace(collection=lambda name:SimpleNamespace(document=lambda day:Ref()),transaction=lambda:Tx())
    first=object.__new__(FirestoreStore);first.client=client
    second=object.__new__(FirestoreStore);second.client=client
    monkeypatch.setattr(firestore,'transactional',lambda fn:fn)
    monkeypatch.setattr(quota,'settings',SimpleNamespace(ai_daily_call_limit=1))
    monkeypatch.setattr(quota,'get_store',lambda:first)
    quota.reserve_call()
    monkeypatch.setattr(quota,'get_store',lambda:second)
    with pytest.raises(HTTPException) as e:quota.reserve_call()
    assert e.value.status_code==429 and data['used']==1
    assert events==['read','write','read']


def test_config_rejects_unbounded_or_negative_limit():
    from backend.config import Settings
    for value in (-1,201):
        with pytest.raises(ValueError):Settings(ai_daily_call_limit=value)
    assert Settings(ai_daily_call_limit=200).ai_daily_call_limit==200
