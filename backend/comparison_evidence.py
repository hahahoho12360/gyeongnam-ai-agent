"""모델의 비교 누락을 막기 위한 저장 자료 기반 비교 문단."""
import math

def _number(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def append_comparison(answer, context):
    if not context.get('summary',{}).get('region') or '[응답 미완료]' in answer:return answer
    comps=context.get('comparison',{});summaries=context.get('comparison_summaries',{})
    lines=['[저장 데이터 기반 자동 비교]']
    roles={'neighbors':'인접지역','peers':'유사 지역','seeded_random':'월별 고정 추출 지역'}
    base=context['summary']; base_id=base['region']['id']
    base=summaries.get(base_id,base)
    for group,label in roles.items():
        rows=comps.get(group,[])
        if not rows:
            if group=='neighbors': continue
            lines.append(f'- {label}: 비교 대상이 없습니다.' + (' 경계자료 검증·등록 여부를 확인해야 하며, 실제 이웃이 없다는 뜻은 아닙니다.' if group=='neighbors' else ''))
        for r in rows:
            s=summaries.get(r['id'],{});name=r.get('full_name') or r.get('name') or r['id'];value=s.get('metrics',{}).get('population_total');b=base.get('metrics',{}).get('population_total')
            period=s.get('period');same=bool(period and period==base.get('period'))
            text=f'- {label} {name}: '
            if _number(value):
                text+=f'인구 {value:,.0f}명 ({period or "기준기간 미확인"})'
                if same and _number(b):text+=f', 대상 지역 대비 {value-b:+,.0f}명'
                else:text+=', 기간이 같지 않거나 대상 수치가 없어 차이 계산 제외'
            else:text+='인구 자료가 없어 수치 비교 불가'
            lines.append(text+'.')
    lines.append('선정 근거: 인접지역은 등록된 경계 공유 관계, 유사 지역은 같은 peer_group의 지표 거리, 고정 추출은 지역코드·월을 이용한 추출입니다. 유사도 계산에서 결측치를 0으로 처리하므로 유사 지역 선정에는 한계가 있습니다.')
    return answer+'\n\n'+'\n'.join(lines)
