"""Resolve explicit question regions before building the shared UI/agent context."""
import re
from . import analysis

def select_region(message, fallback):
    regions=analysis.list_regions()
    codes=re.findall(r'\b4812\d{6}\b',message)
    hits=[r for r in regions if r['id'] in codes]
    if not hits:
        named=[r for r in regions if r.get('name') and r['name'] in message]
        # Prefer the longest legal name (e.g. 장군동5가 over 장군동).
        if named:
            length=max(len(r['name']) for r in named)
            hits=[r for r in named if len(r['name'])==length]
    if not hits:
        tokens=re.findall(r'([가-힣]+동)(?=의|\s|$)',message)
        hits=[r for r in regions if any(re.fullmatch(re.escape(t)+r'[0-9]+가',r.get('name','')) for t in tokens)]
    if len(hits)>1:
        qualified=[r for r in hits if r.get('sigungu') and (r['sigungu'] in message or r['sigungu'].split()[-1] in message)]
        if len(qualified)==1:hits=qualified
    if len(hits)==1:return hits[0]['id'],[]
    if hits:return None,hits
    return fallback,[]

