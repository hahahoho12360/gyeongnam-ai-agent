"""Deterministic, question-specific comparison with explicit observation dates."""
import re
from .question_catalog import definition, read
from .topic_comparison import topic_weights

DEFAULTS = {
    'commerce': ['business_count', 'cafe_count', 'restaurant_count'],
    'population': ['population_total'], 'youth': ['age_20_39'],
    'aging': ['age_60_plus'], 'single': ['single_households', 'households'],
    'housing': ['sale_price_per_m2', 'sale_count'],
    'rental': ['jeonse_price', 'rent_count'],
    'building': ['building_count'], 'general': ['population_total'],
}
SPECIFIC = [(r'카페|커피', 'cafe_count'), (r'음식|식당', 'restaurant_count'),
            (r'편의점', 'convenience_store_count'), (r'병원|의료|건강', 'health_business_count'),
            (r'학원|교육.*업소', 'education_business_count')]


def comparison_keys(context):
    question = context.get('question', '')
    from .question_catalog import CATALOG
    matches = [(k,d['label']) for k,d in CATALOG.items() if d['label'] in question]
    exact = [k for k,label in matches if not any(label != other and label in other for _,other in matches)]
    categories = (context.get('summary', {}).get('metrics', {}).get('business_category_counts') or {})
    exact += ['category:' + k for k in categories if k in question]
    if exact:
        return exact[:3]
    topic = topic_weights(question)[0] if question else context.get('comparison', {}).get('topic', 'general')
    specific = [key for pattern,key in SPECIFIC if re.search(pattern,question)]
    return specific[:3] if specific else DEFAULTS.get(topic, DEFAULTS['general'])


def comparison_text(context):
    base = context.get('summary', {})
    if not base.get('region'): return ''
    comps = context.get('comparison', {})
    summaries = context.get('comparison_summaries', {})
    base = summaries.get(base['region']['id'], base)
    lines = []
    for group,label in [('peers','유사 지역'),('seeded_random','무작위 비교 지역')]:
        for region in comps.get(group, []):
            row = summaries.get(region['id'], {})
            parts = []
            for key in comparison_keys(context):
                d = definition(key)
                value, baseline = read(row,key), read(base,key)
                source = row.get('freshness', {}).get('sources', {}).get(d['source'], {})
                base_source = base.get('freshness', {}).get('sources', {}).get(d['source'], {})
                month = row.get('month') or comps.get('month')
                observed = source.get('source_as_of')
                if value is None:
                    parts.append(f'{d["label"]}: 비교 기준월 {month or "미확인"}의 제공 자료에서 값을 확인하지 못했어요')
                    continue
                text = f'{d["label"]} {value:,.2f}'.rstrip('0').rstrip('.') + d['unit']
                text += f' (자료 기준 {observed})' if observed else f' (저장 월 {month or "미확인"}, 실제 자료 기준일 미확인)'
                same_month = bool(row.get('month') and row.get('month') == base.get('month'))
                comparable = same_month and baseline is not None and (not d['snapshot'] or bool(observed and observed == base_source.get('source_as_of')))
                if comparable:
                    diff = f'{value-baseline:+,.2f}'.rstrip('0').rstrip('.')
                    text += f', 대상 지역 대비 {diff}{d["unit"]}'
                elif baseline is not None:
                    text += ', 기준시점 확인이 필요해 차이는 계산하지 않았어요'
                parts.append(text)
            name = region.get('full_name') or region.get('name') or region['id']
            lines.append(f'- {label} {name}: ' + '; '.join(parts) + '.')
    return '\n'.join(lines)


def append_comparison(answer, context):
    if '[응답 미완료]' in answer: return answer
    text = comparison_text(context)
    return answer + ('\n\n' + text if text else '')
