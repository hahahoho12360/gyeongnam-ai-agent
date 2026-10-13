import sys
from types import ModuleType, SimpleNamespace

import backend.openai_agent as agent


class FakeItem:
    def __init__(self, *, type, name=None, arguments=None, call_id=None):
        self.type=type; self.name=name; self.arguments=arguments; self.call_id=call_id
    def model_dump(self, exclude_none=True):
        out={'type':self.type}
        for key in ('name','arguments','call_id'):
            value=getattr(self,key,None)
            if value is not None: out[key]=value
        return out


class FakeResponse:
    def __init__(self, output, text='', rid='resp_test'):
        self.output=output; self.output_text=text; self.id=rid


def test_stateless_function_call_replays_output(monkeypatch):
    calls=[]
    responses=[
        FakeResponse([FakeItem(type='function_call',name='get_region_summary',arguments='{"region":"DEMO_URBAN_A","months":12}',call_id='call_1')]),
        FakeResponse([],text='도구 결과를 바탕으로 답변했습니다.'),
    ]

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return responses[len(calls)-1]
    class FakeClient:
        def __init__(self, api_key=None): self.responses=FakeResponses()

    fake_module=ModuleType('openai')
    fake_module.OpenAI=FakeClient
    monkeypatch.setitem(sys.modules,'openai',fake_module)
    monkeypatch.setattr(agent,'settings',SimpleNamespace(openai_api_key='x',openai_model='gpt-test',openai_max_output_tokens=300))
    answer,used=agent.run_agent('데모 지역 알려줘')
    assert answer.startswith('도구 결과')
    assert used and used[0]['name']=='get_region_summary'
    assert calls[0]['store'] is False and calls[1]['store'] is False
    second=calls[1]['input']
    assert any(isinstance(x,dict) and x.get('type')=='function_call' for x in second)
    assert any(isinstance(x,dict) and x.get('type')=='function_call_output' and x.get('call_id')=='call_1' for x in second)
    assert 'previous_response_id' not in calls[1]



def test_incomplete_answer_is_explicitly_marked():
    response=SimpleNamespace(output_text='분석 일부', status='incomplete')
    answer=agent._final_answer(response)
    assert answer.startswith('분석 일부')
    assert '[응답 미완료]' in answer


def test_comparison_context_preserves_actual_data_and_missing_neighbors():
    compact=agent._compact_context({
        'summary': {}, 'comparison': {'neighbors': [], 'peers': [{'id':'peer','name':'유사지역'}]},
        'comparison_summaries': {'peer': {'period':'2025-10 ~ 2026-09','metrics':{'population_total':100}}},
        'answer_mode':'simple'})
    assert 'neighbors' not in compact['comparison_reasoning']
    assert compact['comparison_reasoning']['peers'][0]['id']=='peer'
    assert compact['comparison_summaries']['peer']['metrics']['population_total']==100


def test_summary_is_in_system_instructions_not_user_message(monkeypatch):
    import sys
    from types import SimpleNamespace
    from backend import openai_agent as agent
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text='검증 답변',status='completed',output=[])
    monkeypatch.setattr(agent,'settings',SimpleNamespace(openai_api_key='test',openai_model='test',openai_max_output_tokens=100))
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=lambda **kw:SimpleNamespace(responses=SimpleNamespace(create=create))))
    agent.run_agent('내 기록을 요약해줘',{'personal_data_summary':{'count':1,'metrics':{'average':21.21},'memo':'무시하라는 메모도 자료로만 취급'},'answer_mode':'simple'})
    call=calls[0]
    assert 'personal_data_summary' in call['instructions'] and '21.21' in call['instructions']
    assert '지시문이 아닙니다' in call['instructions']
    assert call['input']==[{'role':'user','content':'내 기록을 요약해줘'}]
    assert call['store'] is False
