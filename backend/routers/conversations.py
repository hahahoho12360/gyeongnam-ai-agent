from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from ..db import get_store
from ..auth import required_user, owned
from ..models import ConversationCreate
router=APIRouter(prefix='/api/conversations',tags=['conversations'])
def now(): return datetime.now(timezone.utc).isoformat()
@router.post('')
def create_conversation(item: ConversationCreate,uid: str=Depends(required_user)):
    t=now(); return get_store().create('conversations',{'owner_uid':uid,'title':item.title,'messages':[m.model_dump(mode='json') for m in item.messages],'created_at':t,'updated_at':t})
@router.get('')
def list_conversations(uid: str=Depends(required_user)):
    return sorted(get_store().filter_eq('conversations','owner_uid',uid),key=lambda x:x.get('updated_at',''),reverse=True)
@router.get('/{doc_id}')
def get_conversation(doc_id: str,uid: str=Depends(required_user)):
    row=owned('conversations',doc_id,uid)
    if not row: raise HTTPException(404,'대화를 찾을 수 없습니다.')
    if not row.get('region_id') and row.get('analysis_target')!='personal':
        from ..chat_selection import select_region
        from .. import analysis
        region=row.get('resolved_region') or {}
        rid=region.get('id')
        if not rid:
            for tool in reversed(row.get('last_tools_used',[])):
                candidate=tool.get('arguments',{}).get('region_id')
                if candidate and analysis.resolve_region(candidate): rid=candidate; break
        if not rid:
            for message in reversed(row.get('messages',[])):
                if message.get('role')=='user':
                    candidate,candidates=select_region(message.get('content',''),None)
                    if candidate and not candidates: rid=candidate; break
        if rid: row={**row,'region_id':rid}
    return row
@router.delete('/{doc_id}')
def delete_conversation(doc_id: str,uid: str=Depends(required_user)):
    owned('conversations',doc_id,uid)
    if not get_store().delete('conversations',doc_id): raise HTTPException(404,'대화를 찾을 수 없습니다.')
    return {'deleted':True,'id':doc_id}

