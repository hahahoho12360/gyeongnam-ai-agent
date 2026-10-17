from backend.comparison_evidence import append_comparison, comparison_keys
from backend.topic_comparison import topic_weights


def context(question='가포동 상점에 대해 알려줘'):
    def row(code,count):
        return {'region':{'id':code}, 'month':'2026-09', 'metrics':{'business_count':count,'cafe_count':0,'population_total':100},'freshness':{'sources':{'commerce':{'source_as_of':'2026-09-30','status':'ok'}}}}
    return {'question':question,'summary':row('a',10),'comparison':{'month':'2026-09','peers':[{'id':'b','name':'비교동'}],'seeded_random':[]},'comparison_summaries':{'a':row('a',10),'b':row('b',20)}}


def test_commerce_not_population_even_when_population_exists():
    c=context(); answer=append_comparison('동네 소개',c)
    assert '업소 수 20개' in answer and '+10개' in answer
    assert '인구' not in answer
    assert topic_weights(c['question'])[0]=='commerce'


def test_specific_cafe_and_real_zero():
    c=context('카페·커피 업소 수가 궁금해요')
    assert comparison_keys(c)==['cafe_count']
    assert '카페·커피 업소 수 0개' in append_comparison('소개',c)


def test_missing_is_scoped_not_global_and_never_population_fallback():
    c=context();c['comparison_summaries']['b']['metrics']={}
    answer=append_comparison('소개',c)
    assert '비교 기준월 2026-09' in answer
    assert '인구 자료' not in answer and '업소 수 0개' not in answer


def test_snapshot_dates_must_match_for_delta():
    c=context();c['comparison_summaries']['b']['freshness']['sources']['commerce']['source_as_of']='2026-08-31'
    answer=append_comparison('소개',c)
    assert '+10개' not in answer and '2026-08-31' in answer


def test_no_data_status_overrides_stale_value():
    c=context();c['comparison_summaries']['b']['freshness']['sources']['commerce']['status']='no_data'
    assert '업소 수 20개' not in append_comparison('소개',c)
