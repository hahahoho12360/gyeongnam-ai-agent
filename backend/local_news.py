"""Bounded, cached RSS headline lookup; never invent or summarize unread articles."""
import time
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
import requests
_cache={}

def parse_news(xml,region,now=None):
    now=now or datetime.now(timezone.utc)
    name=region.get('name','')
    if not name: return []
    rows=[]
    for item in ET.fromstring(xml).findall('./channel/item'):
        title=item.findtext('title','').strip(); link=item.findtext('link','').strip()
        try: published=parsedate_to_datetime(item.findtext('pubDate',''))
        except (ValueError,TypeError): continue
        if published.tzinfo is None: published=published.replace(tzinfo=timezone.utc)
        source=item.findtext('source','').strip()
        if '창원' not in title: continue
        if not re.search(r'(?<![가-힣])'+re.escape(name)+r'(?![가-힣])',title): continue
        if not now-timedelta(days=30)<=published<=now: continue
        if urlparse(link).scheme!='https' or urlparse(link).hostname!='news.google.com' or not source: continue
        rows.append({'title':title,'url':link,'published_at':published.isoformat(),'source':source,'verification':'rss_headline_only'})
    return sorted(rows,key=lambda x:x['published_at'],reverse=True)[:1]

def recent_news(region):
    key=region.get('id') or region.get('name')
    cached=_cache.get(key)
    if cached and time.monotonic()-cached[0]<1800: return cached[1]
    try:
        response=requests.get('https://news.google.com/rss/search',params={'q':f'"창원" "{region.get("name","")}" when:30d','hl':'ko','gl':'KR','ceid':'KR:ko'},timeout=(2,3))
        response.raise_for_status()
        rows=parse_news(response.content,region)
        result={'status':'found' if rows else 'no_recent_match','items':rows,'note':'최근 30일 기사 제목에 해당 지역명이 있는 소식입니다. 본문 사실 검증·인과관계 분석은 수행하지 않습니다.'}
    except (requests.RequestException,ET.ParseError):
        result={'status':'unavailable','items':[],'note':'소식 연결이 지연되어 통계 분석만 제공합니다.'}
    if len(_cache)>512: _cache.clear()
    _cache[key]=(time.monotonic(),result)
    return result

def append_news(answer,news):
    if not news.get('items') or '[응답 미완료]' in answer: return answer
    item=news['items'][0]
    title=item['title'].replace('[','').replace(']','').replace('\n',' ')
    return answer+f"\n\n**최근 지역 소식**\n{item['source']}에서 ‘{title}’라는 소식을 전했어요 ({item['published_at'][:10]}). [기사 확인]({item['url']})\n기사 제목 기준으로 찾은 소식이며, 통계 변화의 원인으로 단정하지 않아요."
