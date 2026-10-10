from datetime import datetime, timezone
from fastapi import APIRouter
from ..models import ChatRequest, ChatResponse
from ..db import get_store
from .. import analysis
from ..openai_agent import run_agent
from ..comparison_evidence import append_comparison
router=APIRouter(prefix='/api/chat',tags=['chat'])

def now(): return datetime.now(timezone.utc).isoformat()

@router.post('',response_model=ChatResponse)
def chat(req: ChatRequest):
    store=get_store(); context={}; charts=[]
    if req.region_id:
        bundle=analysis.proactive_bundle(req.region_id,req.answer_mode)
        context=bundle
        charts=bundle.get('charts',[]) if isinstance(bundle,dict) else []
    answer,tools=run_agent(req.message,context)
    answer=append_comparison(answer,context)
    if req.conversation_id and store.get('conversations',req.conversation_id):
        conv=store.get('conversations',req.conversation_id); messages=conv.get('messages',[])
        cid=req.conversation_id
    else:
        cid=store.create('conversations',{'title':req.message[:60],'messages':[],'created_at':now(),'updated_at':now()})['id']; messages=[]
    messages += [{'role':'user','content':req.message,'created_at':now()},{'role':'assistant','content':answer,'created_at':now()}]
    store.update('conversations',cid,{'messages':messages,'updated_at':now(),'last_tools_used':tools})
    freshness=(context.get('summary',{}).get('freshness',{}) if isinstance(context,dict) else {})
    return ChatResponse(answer=answer,conversation_id=cid,tools_used=tools,charts=charts,freshness=freshness)

