from datetime import datetime,timezone
from backend.local_news import parse_news,append_news

def test_news_rejects_stale_unrelated_future_and_unsafe_links():
    now=datetime(2026,10,11,tzinfo=timezone.utc)
    def item(title,date,url='https://news.google.com/rss/articles/test'):
        return f'<item><title>{title}</title><pubDate>{date}</pubDate><link>{url}</link><source>지역신문</source></item>'
    xml='<rss><channel>'+''.join([
        item('창원 명서동 생활 소식','Sat, 10 Oct 2026 00:00:00 GMT'),
        item('창원 상남동 소식','Sat, 10 Oct 2026 00:00:00 GMT'),
        item('명서동 오래된 소식','Wed, 01 Jan 2025 00:00:00 GMT'),
        item('명서동 미래 소식','Mon, 12 Oct 2026 00:00:00 GMT'),
        item('명서동 링크 오류','Sat, 10 Oct 2026 00:00:00 GMT','javascript:alert(1)'),
    ])+'</channel></rss>'
    rows=parse_news(xml,{'name':'명서동'},now)
    assert len(rows)==1 and rows[0]['source']=='지역신문'
    answer=append_news('통계 분석',{'items':rows})
    assert '2026-10-10' in answer and '기사 확인' in answer
    assert '최근 지역 소식' in append_news('분석',{'items':[]})
    assert '확인하지 못했어요' in append_news('분석',{'items':[]})
