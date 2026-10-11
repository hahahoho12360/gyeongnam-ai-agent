from fastapi import APIRouter, Depends
from ..db import get_store
from ..models import DataPointCreate, DataPointUpdate
from ..auth import required_user, owned
from ..personal_records import validate_record, summarize, METRICS
router=APIRouter(prefix='/api/data',tags=['data'])

@router.get('/metrics')
def metric_options():
    return [{'key':key,'label':label,'unit':unit} for key,(label,unit) in METRICS.items() if key!='custom']

@router.post('')
def create_data(item: DataPointCreate, uid: str=Depends(required_user)):
    row=validate_record(item.model_dump(mode='json'))
    return get_store().create('data',{**row,'owner_uid':uid})

@router.get('')
def list_data(uid: str=Depends(required_user)):
    return sorted(get_store().filter_eq('data','owner_uid',uid),key=lambda x:x.get('date',''))

@router.put('/{doc_id}')
def update_data(doc_id: str,item: DataPointUpdate,uid: str=Depends(required_user)):
    old=owned('data',doc_id,uid)
    fields=item.model_dump(mode='json',exclude_unset=True)
    updated=validate_record({**old,**fields})
    return get_store().update('data',doc_id,{k:v for k,v in updated.items() if k not in ('id','owner_uid')})

@router.delete('/{doc_id}')
def delete_data(doc_id: str,uid: str=Depends(required_user)):
    owned('data',doc_id,uid);get_store().delete('data',doc_id)
    return {'deleted':True,'id':doc_id}

@router.get('/summary')
def data_summary(uid: str=Depends(required_user)):
    return summarize(list_data(uid))
