from __future__ import annotations
import json
from .config import settings
from .tooling import TOOLS, dispatch

SYSTEM="""당신은 경상남도 생활·주거·부동산·상권 변화 데이터 분석 비서입니다.
규칙:
1) 저장/도구 데이터에 근거해 답하고 숫자를 추측하지 마세요.
2) 지역·통계·비교 질문이면 최소 1개의 데이터 조회 도구를 호출한 뒤 답하세요. 사용자가 짧게 물어도 기본 모드에서는 최근 추세와 유용한 비교를 간결히 덧붙이세요.
3) 표본수가 작거나 freshness가 오래되면 반드시 주의문을 포함하세요.
4) Proxy/Composite Index는 공식 통계가 아니라 프로젝트 정의 지표임을 필요할 때 밝히세요.
5) 인접·Peer·seeded random 비교군은 도구 결과의 선정근거를 구분해 설명하세요.
6) source_as_of와 fetched_at을 혼동하지 말고, 잠정치(is_provisional)는 확정치처럼 표현하지 마세요.
7) 도구 결과가 region_ambiguous이면 임의 지역을 고르지 말고 후보를 사용자에게 제시하세요.
8) 답변은 한국어로 작성하세요.
9) answer_mode=simple이면 핵심 결론, 비교 1~2문장, 기준시점/한계, 후속 제안으로 간결하게 끝내세요. 월별 전체 표는 별도 차트에 있으므로 사용자가 요구할 때만 작성하세요.
10) comparison_reasoning과 comparison_summaries가 있으면 실제 제공된 비교군의 역할(인접/유사/무작위)을 밝히고 자료에 근거한 비교를 추가하세요. neighbors가 비어 있으면 인접지역 미구축을 밝히고 다른 비교군을 인접지역이라 부르지 마세요.
11) sample_size=null 또는 data_confidence=unknown은 앱 메타데이터 미제공/미분류라는 뜻이며 공식 통계가 부정확하다는 증거로 해석하지 마세요. 지표별 sources 메타데이터를 사용하세요.
12) 첫 관측월과 마지막 관측월의 변화율을 전년 동월 대비로 부르지 마세요. 후속 분석 제안을 한 문장 포함하고 문장을 끝까지 완성하세요."""


def _compact_context(context: dict | None) -> dict | None:
    """Context injection 요구를 지키면서 차트 원자료 중복 전송을 줄인다.

    세부 추세·비교는 Function Calling 도구가 필요할 때 다시 조회한다.
    """
    if not context or not isinstance(context, dict):
        return None
    summary=context.get('summary') if isinstance(context.get('summary'),dict) else {}
    comparison=context.get('comparison') if isinstance(context.get('comparison'),dict) else {}
    compact={
        'summary': {
            'region': summary.get('region'),
            'period': summary.get('period'),
            'count': summary.get('count'),
            'metrics': summary.get('metrics'),
            'derived': summary.get('derived'),
            'indexes': summary.get('indexes'),
            'index_meta': summary.get('index_meta'),
            'freshness': summary.get('freshness'),
        },
        'comparison_reasoning': {
            key: [{'id':r.get('id'),'name':r.get('full_name') or r.get('name')} for r in comparison.get(key,[]) if isinstance(r,dict)]
            for key in ('neighbors','peers','seeded_random')
        },
        'comparison_summaries': context.get('comparison_summaries', {}),
        'answer_mode': context.get('answer_mode'),
    }
    return compact


def _dump_output_item(item):
    """Responses SDK 출력 Item을 stateless 다음 요청에 다시 넣을 JSON으로 변환한다."""
    if hasattr(item, 'model_dump'):
        return item.model_dump(exclude_none=True)
    if isinstance(item, dict):
        return item
    return item


def _final_answer(response):
    text = response.output_text or ''
    if getattr(response, 'status', None) == 'incomplete':
        return (text.rstrip() + '\n\n[응답 미완료] 생성이 완료되지 않았습니다. 위 내용은 일부 답변이며 질문 범위를 줄여 다시 요청해 주세요.').strip()
    return text or '응답을 생성하지 못했습니다.'


def run_agent(message: str, context: dict | None=None) -> tuple[str,list[dict]]:
    if not settings.openai_api_key:
        return ('OPENAI_API_KEY가 설정되지 않아 AI 호출을 수행하지 않았습니다. 데이터 API와 데모 UI는 별도로 시험할 수 있습니다.',[])
    from openai import OpenAI
    client=OpenAI(api_key=settings.openai_api_key)
    input_text=message
    compact=_compact_context(context)
    if compact:
        input_text += '\n\n[앱이 미리 제공한 데이터 요약 컨텍스트]\n'+json.dumps(compact,ensure_ascii=False,default=str)

    # 개인정보/지역분석 데이터의 별도 OpenAI 저장을 피하기 위해 store=False를 사용한다.
    # 따라서 Function Calling 왕복 때 previous_response_id에 의존하지 않고, 이전 response.output
    # (reasoning/function_call 포함)과 function_call_output을 매번 전체 sequence로 재전송한다.
    sequence=[{'role':'user','content':input_text}]
    response=client.responses.create(
        model=settings.openai_model,
        instructions=SYSTEM,
        input=sequence,
        tools=TOOLS,
        max_output_tokens=settings.openai_max_output_tokens,
        store=False,
    )
    used=[]
    for _ in range(5):
        if getattr(response, 'status', None) == 'incomplete':
            return (_final_answer(response), used)
        calls=[x for x in response.output if getattr(x,'type',None)=='function_call']
        if not calls:
            return (_final_answer(response), used)

        # reasoning item과 function_call item을 포함한 모델 출력을 순서대로 보존한다.
        sequence.extend(_dump_output_item(x) for x in response.output)
        for call in calls:
            try:
                args=json.loads(call.arguments or '{}')
            except json.JSONDecodeError:
                args={}
            result=dispatch(call.name,args)
            used.append({'name':call.name,'arguments':args,'result_preview':str(result)[:500]})
            sequence.append({
                'type':'function_call_output',
                'call_id':call.call_id,
                'output':json.dumps(result,ensure_ascii=False,default=str),
            })
        response=client.responses.create(
            model=settings.openai_model,
            input=sequence,
            tools=TOOLS,
            instructions=SYSTEM,
            max_output_tokens=settings.openai_max_output_tokens,
            store=False,
        )
    return ('도구 호출 횟수 제한에 도달했습니다. 질문 범위를 조금 좁혀 주세요.',used)


