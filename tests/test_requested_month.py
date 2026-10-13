from backend import tooling

def test_explicit_month_cannot_return_latest_month(monkeypatch):
 monkeypatch.setattr(tooling.analysis,'resolve_region',lambda q:{'id':'4812912400','name':'광화동'})
 monkeypatch.setattr(tooling.analysis,'series',lambda *a:[{'month':'2025-09','metrics':{'population_total':727,'households':333}},{'month':'2026-09','metrics':{'population_total':700}}])
 result=tooling.dispatch('get_region_summary',{'region':'광화동','months':1},'광화동 2025년 9월 인구와 세대 수')
 assert result['period']=='2025-09 ~ 2025-09'
 assert result['metrics']['population_total']==727
 assert result['metrics']['households']==333
 result=tooling.dispatch('get_region_month',{'region':'광화동','month':'2025-09'})
 assert result['requested_month']=='2025-09'
 assert tooling.dispatch('get_region_month',{'region':'광화동','month':'2022-09'})['error']=='invalid_month'
