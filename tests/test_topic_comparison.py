from backend.topic_comparison import measured, select_comparisons, topic_weights
from backend import analysis, db

MONTH='2026-09'

def dataset():
    regions=[{'id':str(i),'name':f'지역{i}','neighbors':['1']} for i in range(8)]
    def row(pop,price):
        return {'month':MONTH,'metrics':{'population_total':pop,'sale_price_per_m2':price}}
    rows={'0':row(1000,10000),'1':row(1001,50000),'2':row(999,48000),
          '3':row(9000,10001),'4':row(9500,9999),'5':row(7000,30000),
          '6':row(8000,35000),'7':row(6000,40000)}
    return regions,rows

def test_topic_changes_actual_nearest_region_and_reproducible():
    regions,rows=dataset()
    a=select_comparisons('0',regions,rows,MONTH,'인구가 비슷한 곳')
    b=select_comparisons('0',regions,rows,MONTH,'매매가격이 비슷한 곳')
    assert a['peers'][0]['id'] in ('1','2')
    assert b['peers'][0]['id'] in ('3','4')
    assert a==select_comparisons('0',regions,rows,MONTH,'인구가 비슷한 곳')
    assert a['neighbors']==[]
    assert len({r['id'] for r in a['peers']+a['seeded_random']})==3
    assert all(r['id']!='0' for r in a['peers']+a['seeded_random'])

def test_question_variation_keeps_closest_and_varies_second():
    regions=[{'id':str(i)} for i in range(8)]
    rows={str(i):{'month':MONTH,'metrics':{'population_total':1000+i}} for i in range(8)}
    answers=[select_comparisons('0',regions,rows,MONTH,f'인구 비교 설명 {i}') for i in range(12)]
    assert all(a['peers'][0]['id']=='1' for a in answers)
    assert len({a['peers'][1]['id'] for a in answers})>1

def test_missing_is_not_zero_wrong_month_and_out_of_scope_excluded():
    regions,rows=dataset()
    rows['1']['month']='2026-08'
    rows['2']['metrics']['population_total']=None
    rows['outside']={'month':MONTH,'metrics':{'population_total':1000}}
    out=select_comparisons('0',regions,rows,MONTH,'인구')
    assert not {r['id'] for r in out['peers']+out['seeded_random']}&{'1','outside'}
    assert '2' not in {r['id'] for r in out['peers']}
    assert measured({'metrics':{'population_total':0}},'population_total')==0
    assert measured({'metrics':{'population_total':0},'freshness':{'sources':{'population':{'status':'no_data'}}}},'population_total') is None
    assert measured({'derived':{'young_population_share':0}},'young_population_share') is None

def test_topic_unavailable_falls_back_explicitly():
    regions,rows=dataset()
    out=select_comparisons('0',regions,rows,MONTH,'상권과 카페')
    assert out['topic']=='commerce' and out['topic_data_unavailable']
    assert 'businesses_per_1000_people' not in out['feature_keys']
    assert out['peers']

def test_no_monthly_data_does_not_label_random_as_similar():
    regions,rows=dataset()
    out=select_comparisons('0',regions,{},MONTH,'주택')
    assert not out['peers'] and not out['seeded_random']

def test_comparison_reads_month_once_without_per_region_latest(monkeypatch):
    store=db.MemoryStore();monkeypatch.setattr(db,'_store',store)
    regions,rows=dataset()
    for r in regions:store.set('regions',r['id'],r)
    for rid,row in rows.items():store.set('monthly_data',rid+MONTH,{'region_id':rid,**row})
    store.set('region_latest','0',rows['0'])
    reads=[];original=store.filter_eq
    monkeypatch.setattr(store,'filter_eq',lambda c,k,v:(reads.append((c,k,v)) or original(c,k,v)))
    out=analysis.comparison_regions('0',MONTH,'집값')
    assert out['peers'][0]['id'] in ('3','4')
    assert reads==[('monthly_data','month',MONTH)]

def test_auto_comparison_never_appends_registered_neighbors():
    from backend.comparison_evidence import append_comparison
    base={'region':{'id':'0'},'metrics':{'population_total':100},'period':MONTH}
    text=append_comparison('설명',{'summary':base,'comparison':{'neighbors':[{'id':'x','name':'이웃동'}]}})
    assert '이웃동' not in text and '인접' not in text

def test_topic_labels():
    assert topic_weights('청년 인구')[0]=='youth'
    assert topic_weights('전세가격')[0]=='rental'
    assert topic_weights('동네 소개')[0]=='general'
