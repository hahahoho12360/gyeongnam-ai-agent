from fastapi import APIRouter, HTTPException
from ..db import get_store
from ..models import DataPointCreate, DataPointUpdate
router=APIRouter(prefix='/api/data',tags=['data'])

@router.post('')
def create_data(item: DataPointCreate): return get_store().create('data', item.model_dump(mode='json'))
@router.get('')
def list_data(): return sorted(get_store().list('data'),key=lambda x:x.get('date',''))
@router.put('/{doc_id}')
def update_data(doc_id: str, item: DataPointUpdate):
    row=get_store().update('data',doc_id,{k:v for k,v in item.model_dump(mode='json').items() if v is not None})
    if not row: raise HTTPException(404,'데이터를 찾을 수 없습니다.')
    return row
@router.delete('/{doc_id}')
def delete_data(doc_id: str):
    if not get_store().delete('data',doc_id): raise HTTPException(404,'데이터를 찾을 수 없습니다.')
    return {'deleted':True,'id':doc_id}
@router.get('/summary')
def data_summary():
    rows=list_data(); vals=[float(r['value']) for r in rows if r.get('value') is not None]
    if not rows: return {'period':None,'count':0,'metrics':{},'trend':'데이터 없음'}
    trend='유지'
    if len(vals)>=2:
        diff=vals[-1]-vals[0]; trend='상승' if diff>0 else ('감소' if diff<0 else '유지')
    return {'period':f"{rows[0]['date']} ~ {rows[-1]['date']}",'count':len(rows),'metrics':{'average':sum(vals)/len(vals) if vals else None,'max':max(vals) if vals else None,'min':min(vals) if vals else None},'trend':trend}
