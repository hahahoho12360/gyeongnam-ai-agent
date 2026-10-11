from datetime import datetime, timezone
from fastapi import APIRouter
from ..models import ChatRequest, ChatResponse
from ..db import get_store
from .. import analysis
from ..openai_agent import run_agent
from ..comparison_evidence import append_comparison
from ..chat_selection import select_region
from ..local_news import recent_news, append_news
from .data import data_summary
router=APIRouter(prefix='/api/chat',tags=['chat'])

def now(): return datetime.now(timezone.utc).isoformat()

@router.post('',response_model=ChatResponse)
def chat(req: ChatRequest):
    store=get_store(); context={}; charts=[]
    selected,candidates=select_region(req.message,req.region_id) if req.analysis_target=='region' else (None,[])
    if candidates:
        return ChatResponse(answer='지역을 하나로 확정할 수 없습니다. 기준으로 볼 지역을 선택해주세요: '+', '.join(r.get('full_name') or r['name'] for r in candidates),conversation_id=req.conversation_id or '',region_candidates=candidates)
    if req.analysis_target=='personal':
        context={'personal_data_summary':data_summary(),'answer_mode':req.answer_mode}
    elif selected:
        bundle=analysis.proactive_bundle(selected,req.answer_mode)
        context=bundle
        charts=bundle.get('charts',[]) if isinstance(bundle,dict) else []
    answer,tools=run_agent(req.message,context)
    answer=append_comparison(answer,context)
    if not selected and req.analysis_target=='region':
        for tool in reversed(tools):
            candidate=tool.get('arguments',{}).get('region_id')
            resolved=analysis.resolve_region(candidate) if candidate else None
            if resolved:
                selected=resolved['id']; break
    if selected:
        region=analysis.resolve_region(selected)
        if region: answer=append_news(answer,recent_news(region))
    if req.conversation_id and store.get('conversations',req.conversation_id):
        conv=store.get('conversations',req.conversation_id); messages=conv.get('messages',[])
        cid=req.conversation_id
    else:
        cid=store.create('conversations',{'title':req.message[:60],'messages':[],'created_at':now(),'updated_at':now()})['id']; messages=[]
    messages += [{'role':'user','content':req.message,'created_at':now()},{'role':'assistant','content':answer,'created_at':now()}]
    store.update('conversations',cid,{'messages':messages,'updated_at':now(),'last_tools_used':tools,'analysis_target':req.analysis_target,'region_id':selected,'resolved_region':analysis.resolve_region(selected) if selected else None})
    freshness=(context.get('summary',{}).get('freshness',{}) if isinstance(context,dict) else {})
    return ChatResponse(resolved_region=analysis.resolve_region(selected) if selected else None,analysis_target=req.analysis_target,answer=answer,conversation_id=cid,tools_used=tools,charts=charts,freshness=freshness)

