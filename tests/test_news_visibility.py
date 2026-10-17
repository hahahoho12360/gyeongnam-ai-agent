from backend.local_news import append_news

def test_news_section_remains_visible_without_fabricating_news():
    assert '최근 지역 소식' in append_news('분석',{'status':'no_recent_match','items':[]})
    assert '연결이 지연' in append_news('분석',{'status':'unavailable','items':[]})
    item={'title':'창원 용호동 소식','source':'지역언론','published_at':'2026-10-17','url':'https://news.google.com/example'}
    text=append_news('분석',{'items':[item]})
    assert item['url'] in text and '2026-10-17' in text
