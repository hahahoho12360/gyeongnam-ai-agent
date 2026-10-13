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


def test_single_reference_month_and_ranges_are_distinct():
 from backend.period_selection import requested_month
 assert requested_month('2025년 9월, 다시 2025년 9월')=='2025-09'
 assert requested_month('2025-09')=='2025-09'
 assert requested_month('2025년 9월부터 2026년 9월') is None


def test_automatic_comparison_uses_same_requested_month(monkeypatch):
 from backend import analysis
 from backend.comparison_evidence import append_comparison
 class Store:
  def get(self,collection,rid):
   if collection=='regions':return {'id':rid,'name':rid}
   return {'metrics':{'population_total':727 if rid.startswith('A_') else 354}}
 monkeypatch.setattr(analysis,'get_store',lambda:Store())
 monkeypatch.setattr(analysis,'resolve_region',lambda q:{'id':'A'})
 seen=[]
 def comparisons(rid,month,question):
  seen.append(month);return {'peers':[{'id':'B','name':'비교 지역'}],'seeded_random':[]}
 monkeypatch.setattr(analysis,'comparison_regions',comparisons)
 monkeypatch.setattr(analysis,'chart_metric',lambda *a,**kw:{'end_month':kw.get('end_month')})
 bundle=analysis.proactive_bundle('A','simple','2025년 9월 인구')
 assert seen==['2025-09']
 assert bundle['summary']['metrics']['population_total']==727
 assert bundle['charts'][0]['end_month']=='2025-09'
 answer=append_comparison('인구 727명',bundle)
 assert '2025-09 ~ 2025-09' in answer
 assert '-373명' in answer
