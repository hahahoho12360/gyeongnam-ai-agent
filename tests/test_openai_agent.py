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
