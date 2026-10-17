from datetime import datetime, timezone
import hashlib
import logging
import threading
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from ..models import ChatRequest, ChatResponse
from ..db import get_store
from ..auth import required_user, owned
from .. import analysis
from ..openai_agent import run_agent
from ..comparison_evidence import append_comparison
from ..chat_selection import select_region
from ..local_news import recent_news, append_news
from ..region_knowledge import introduction_context
from .data import data_summary
router=APIRouter(prefix='/api/chat',tags=['chat'])
log=logging.getLogger(__name__)
_lock=threading.Lock()
_inflight=set()
_cache={}

def now(): return datetime.now(timezone.utc).isoformat()

def stage(request,name):
    request.state.stage=name
    log.info('chat_stage id=%s stage=%s elapsed_ms=%s',request.state.request_id,name,round((time.monotonic()-request.state.started)*1000))

@router.post('',response_model=ChatResponse)
def chat(req: ChatRequest,request: Request,uid: str=Depends(required_user)):
    request.state.request_id=req.request_id or uuid.uuid4().hex
    request.state.started=time.monotonic()
    key=hashlib.sha256((uid+':'+req.request_id).encode()).hexdigest() if req.request_id else None
    fingerprint=hashlib.sha256(req.model_dump_json(exclude={'request_id'}).encode()).hexdigest()
    if key:
        with _lock:
            cached=_cache.get(key)
            if cached:
                if cached[0]!=fingerprint:raise HTTPException(409,'같은 요청 번호로 다른 질문을 보낼 수 없어요.')
                return cached[1]
            if key in _inflight:raise HTTPException(409,'이 질문을 아직 처리하고 있어요. 잠시 후 다시 시도해 주세요.')
            _inflight.add(key)
    try:
        stage(request,'request_lookup')
        if key:
            previous=get_store().get('chat_requests',key)
            if previous:
                if previous.get('fingerprint')!=fingerprint:raise HTTPException(409,'같은 요청 번호로 다른 질문을 보낼 수 없어요.')
                return ChatResponse(**previous['response'])
        result=process_chat(req,uid,request)
        if key:
            with _lock:
                if len(_cache)>512:_cache.clear()
                _cache[key]=(fingerprint,result)
            try:get_store().set('chat_requests',key,{'owner_uid':uid,'fingerprint':fingerprint,'response':result.model_dump(),'created_at':now()})
            except Exception as exc:log.warning('request_cache_failed id=%s error_type=%s',request.state.request_id,type(exc).__name__)
        stage(request,'complete')
        return result
    finally:
        if key:
            with _lock:_inflight.discard(key)

def process_chat(req,uid,request):
    store=get_store();context={};charts=[];tools=[]
    stage(request,'conversation')
    existing=owned('conversations',req.conversation_id,uid) if req.conversation_id else None
    # Never mix private-record history with a regional conversation.
    history=(existing or {}).get('messages',[]) if (existing or {}).get('analysis_target',req.analysis_target)==req.analysis_target else []
    stage(request,'region_resolution')
    fallback=req.region_id or ((existing or {}).get('region_id') if req.analysis_target=='region' else None)
    selected,candidates=select_region(req.message,fallback) if req.analysis_target=='region' else (None,[])
    question=req.message
    pending=(existing or {}).get('pending_question')
    if pending and selected and not candidates:
        question=pending+'\n사용자가 확정한 지역: '+req.message
    if candidates:
        answer='어느 법정읍·면·동인지 확인해 주세요: '+', '.join(r.get('full_name') or r['name'] for r in candidates)+'. 지역을 선택하면 앞서 질문하신 내용을 이어서 분석할게요.'
    else:
        if req.analysis_target=='personal':
            context={'personal_data_summary':data_summary(uid),'answer_mode':req.answer_mode}
        elif selected:
            stage(request,'statistics')
            context=analysis.proactive_bundle(selected,req.answer_mode,question)
            region=analysis.resolve_region(selected)
            stage(request,'introduction')
            if region:
                try:context['region_introduction']=introduction_context(region,req.answer_mode)
                except Exception as exc:
                    log.warning('introduction_failed id=%s error_type=%s',request.state.request_id,type(exc).__name__)
                    context['region_introduction']={'region_name':region.get('full_name') or region.get('name'),'status':'unavailable','sources':[]}
            charts=context.get('charts',[])
        context['conversation_history']=history[-8:]
        stage(request,'ai')
        answer,tools=run_agent(question,context)
        stage(request,'comparison')
        try:answer=append_comparison(answer,context)
        except Exception as exc:log.warning('comparison_failed id=%s error_type=%s',request.state.request_id,type(exc).__name__)
        if not selected and req.analysis_target=='region':
            for tool in reversed(tools):
                candidate=tool.get('arguments',{}).get('region') or tool.get('arguments',{}).get('region_id')
                resolved=analysis.resolve_region(candidate) if candidate else None
                if resolved:selected=resolved['id'];break
        if selected:
            region=analysis.resolve_region(selected)
            stage(request,'news')
            if region:
                try:news=recent_news(region)
                except Exception as exc:
                    log.warning('news_failed id=%s error_type=%s',request.state.request_id,type(exc).__name__)
                    news={'status':'unavailable','items':[]}
                answer=append_news(answer,news)
    stage(request,'save')
    cid=req.conversation_id or ''
    messages=list((existing or {}).get('messages',[]))
    messages += [{'role':'user','content':req.message,'created_at':now()},{'role':'assistant','content':answer,'created_at':now()}]
    changes={'messages':messages,'updated_at':now(),'last_tools_used':tools,'analysis_target':req.analysis_target,'comparison_question':question if req.analysis_target=='region' else '', 'region_id':selected,'resolved_region':analysis.resolve_region(selected) if selected else None,'pending_question':question if candidates else None}
    try:
        if existing:store.update('conversations',cid,changes)
        else:
            cid=hashlib.sha256((uid+':'+req.request_id).encode()).hexdigest() if req.request_id else uuid.uuid4().hex
            store.set('conversations',cid,{'owner_uid':uid,'title':req.message[:60],'created_at':now(),**changes},merge=False)
    except Exception as exc:
        log.warning('conversation_save_failed id=%s error_type=%s',request.state.request_id,type(exc).__name__)
        cid=req.conversation_id or ''
        answer+='\n\n답변은 생성됐지만 대화 저장에 실패했어요. 필요한 내용을 복사해 두세요.'
    return ChatResponse(resolved_region=analysis.resolve_region(selected) if selected else None,region_candidates=candidates,analysis_target=req.analysis_target,answer=answer,conversation_id=cid,tools_used=tools,charts=charts,freshness=context.get('summary',{}).get('freshness',{}))


@router.get('/usage')
def daily_ai_usage(response: Response):
    """Aggregate counter only; no account identifiers or credentials."""
    from ..daily_usage import usage_status
    response.headers['Cache-Control'] = 'no-store'
    return usage_status()
