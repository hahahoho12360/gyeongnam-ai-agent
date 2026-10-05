from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from ..db import get_store
from ..models import ConversationCreate
router=APIRouter(prefix='/api/conversations',tags=['conversations'])
def now(): return datetime.now(timezone.utc).isoformat()
@router.post('')
def create_conversation(item: ConversationCreate):
    t=now(); return get_store().create('conversations',{'title':item.title,'messages':[m.model_dump(mode='json') for m in item.messages],'created_at':t,'updated_at':t})
@router.get('')
def list_conversations():
    return sorted(get_store().list('conversations'),key=lambda x:x.get('updated_at',''),reverse=True)
@router.get('/{doc_id}')
def get_conversation(doc_id: str):
    row=get_store().get('conversations',doc_id)
    if not row: raise HTTPException(404,'대화를 찾을 수 없습니다.')
    return row
@router.delete('/{doc_id}')
def delete_conversation(doc_id: str):
    if not get_store().delete('conversations',doc_id): raise HTTPException(404,'대화를 찾을 수 없습니다.')
    return {'deleted':True,'id':doc_id}
