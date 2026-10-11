"""모델의 비교 누락을 막기 위한 저장 자료 기반 비교 문단."""
import math

def _number(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def append_comparison(answer, context):
    if not context.get('summary',{}).get('region') or '[응답 미완료]' in answer:return answer
    comps=context.get('comparison',{});summaries=context.get('comparison_summaries',{})
    lines=[]
    roles={'peers':'유사 지역','seeded_random':'무작위 비교 지역'}
    base=context['summary']; base_id=base['region']['id']
    base=summaries.get(base_id,base)
    for group,label in roles.items():
        rows=comps.get(group,[])
        if not rows: continue
        for r in rows:
            if (r.get('name') or r['id']) in answer: continue
            s=summaries.get(r['id'],{});name=r.get('full_name') or r.get('name') or r['id'];value=s.get('metrics',{}).get('population_total');b=base.get('metrics',{}).get('population_total')
            period=s.get('period');same=bool(period and period==base.get('period'))
            text=f'- {label} {name}: '
            if _number(value):
                text+=f'인구 {value:,.0f}명 ({period or "기준기간 미확인"})'
                if same and _number(b):text+=f', 대상 지역 대비 {value-b:+,.0f}명'
                else:text+=', 기간이 같지 않거나 대상 수치가 없어 차이 계산 제외'
            else:text+='인구 자료가 없어 수치 비교 불가'
            lines.append(text+'.')

    answer=answer.replace('유사 Peer','유사 지역').replace('Peer Group','유사 지역').replace('Peer','유사 지역').replace('Seeded random','무작위 비교 지역')
    return answer+('\n\n'+'\n'.join(lines) if lines else '')
