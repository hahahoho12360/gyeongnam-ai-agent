import time
import pytest
import requests
from scripts import population_one_month as m


def test_budget_stops_before_new_request_and_opens_circuit(monkeypatch):
    monkeypatch.setattr(m,'save',lambda *a:None)
    b=m.Budget(1)
    with pytest.raises(m.StopCollection,match='deadline'):b.check()
    b=m.Budget(100,threshold=2)
    b.record({'outcome':'connection_error'},True)
    b.record({'outcome':'connection_error'},True)
    with pytest.raises(m.StopCollection,match='circuit'):b.check()


def test_http_429_classified_without_key(monkeypatch):
    monkeypatch.setattr(m,'save',lambda *a:None)
    class Response:status_code=429
    monkeypatch.setattr(m.requests,'get',lambda *a,**kw:Response())
    m.BoundedClient.budget=m.Budget(100)
    with pytest.raises(RuntimeError,match='http_rate_limit'):
        m.BoundedClient(service_key='sensitive-test-value').get('https://example.org',{'stdgCd':m.SAMGYE})
    assert 'sensitive-test-value' not in str(m.BoundedClient.budget.events)


def test_connect_failure_has_two_bounded_attempts(monkeypatch):
    monkeypatch.setattr(m,'save',lambda *a:None)
    monkeypatch.setattr(m.time,'sleep',lambda *a:None)
    def failed(*a,**kw):raise requests.exceptions.ConnectTimeout('URL with secret')
    monkeypatch.setattr(m.requests,'get',failed)
    m.BoundedClient.budget=m.Budget(100)
    with pytest.raises(RuntimeError,match='connect_timeout'):
        m.BoundedClient(service_key='sensitive-test-value').get('https://example.org')
    assert len(m.BoundedClient.budget.events)==2
    assert 'secret' not in str(m.BoundedClient.budget.events)
