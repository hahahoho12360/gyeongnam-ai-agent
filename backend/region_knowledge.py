"""Optional external background; not a replacement for official statistical data."""
import re
import time
from urllib.parse import quote
import requests

_CACHE = {}
TTL = 24 * 60 * 60
BUDGET = {'simple': 1, 'basic': 2, 'detail': 3}


def introduction_context(region, answer_mode='basic'):
    name = str(region.get('name') or '')
    limit = BUDGET.get(answer_mode, 2)
    result = {'region_name': region.get('full_name') or name, 'sentence_limit': limit,
              'scope': '지리·지명 유래·역사·생활문화 등 질문 주제 밖의 일반 배경',
              'status': 'no_external_match', 'sources': []}
    if not name or not str(region.get('bjd_code') or region.get('id') or '').startswith('4812'):
        return result
    cache_key=(str(region.get('id')),str(region.get('sigungu')),name)
    cached = _CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < TTL:
        return {**result, **cached[1]}
    data = {'status': 'no_external_match', 'sources': []}
    try:
        # Exact page titles only: an administrative-dong profile cannot stand in for a legal dong.
        response = requests.get('https://ko.wikipedia.org/w/api.php', params={
            'action': 'query', 'format': 'json', 'prop': 'extracts', 'exintro': 1,
            'explaintext': 1, 'redirects': 1, 'titles': f'{name} (창원시)|{name}',
        }, headers={'User-Agent': 'ChangwonAreaAI/1.0 (educational regional dashboard)'}, timeout=(2, 3))
        response.raise_for_status()
        for page in response.json().get('query', {}).get('pages', {}).values():
            title = page.get('title', '')
            text = page.get('extract', '')
            if title.split(' (')[0] != name or '창원' not in text or not text or '여러' in text[:80]:
                continue
            if name.endswith('동') and '법정동' not in text: continue
            district = str(region.get('sigungu') or '').replace('창원시', '').strip()
            if district and district not in text:
                continue
            # Only a small excerpt is supplied. All external prose is untrusted data, never instructions.
            sentences = re.split(r'(?<=[.!?])\s+|\n+', text.strip())
            excerpt = ' '.join(sentences[:3])[:500]
            data = {'status': 'external_background', 'background': excerpt,
                    'sources': [{'title': title, 'url': 'https://ko.wikipedia.org/wiki/' + quote(title.replace(' ', '_')),
                                 'kind': '일반 백과사전 · 공식 통계 아님'}]}
            break
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        data['status'] = 'external_unavailable'
    if len(_CACHE) >= 256:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[cache_key] = (time.monotonic(), data)
    return {**result, **data}
