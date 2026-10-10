import csv, io, json
from fastapi import APIRouter, HTTPException, Response
from .. import analysis
from ..live import live_snapshot
from ..db import get_store
router=APIRouter(prefix='/api/analytics',tags=['analytics'])
@router.get('/regions')
def regions(): return analysis.list_regions()
@router.get('/regions/{region_id}/summary')
def region_summary(region_id: str, months: int=12): return analysis.summary(region_id,months)
@router.get('/regions/{region_id}/trend')
def region_trend(region_id: str, months: int=36): return {'rows':analysis.series(region_id,months),'chart':analysis.chart_population([region_id],months)}
@router.get('/regions/{region_id}/compare')
def compare(region_id: str, answer_mode: str='basic'): return analysis.proactive_bundle(region_id,answer_mode)
@router.get('/regions/{region_id}/indexes')
def indexes(region_id: str):
    row=analysis.latest(region_id)
    if not row: raise HTTPException(404,'지역 데이터가 없습니다.')
    return {'region':analysis.resolve_region(region_id),'indexes':row.get('indexes',{}),'index_meta':row.get('index_meta',{}),'freshness':row.get('freshness',{})}

@router.get('/regions/{region_id}/live')
def live_region(region_id: str):
    return live_snapshot(region_id)

@router.get('/benchmarks/{region_id}')
def benchmarks(region_id: str):
    region=analysis.resolve_region(region_id)
    if not region: raise HTTPException(404,'지역을 찾을 수 없습니다.')
    store=get_store()
    rows=[r for r in store.list('benchmarks') if r.get('region_id')==region['id'] or r.get('bjd_code')==region.get('bjd_code')]
    return {'region':region,'rows':rows}

@router.get('/statistics/{region_id}')
def stats(region_id: str, months: int=36): return analysis.statistics(region_id,months)
@router.get('/export/{region_id}')
def export(region_id: str, format: str='csv', months: int=120):
    rows=analysis.series(region_id,months)
    if format.lower()=='json':
        return Response(json.dumps(rows,ensure_ascii=False,default=str),media_type='application/json',headers={'Content-Disposition':f'attachment; filename={region_id}.json'})
    buf=io.StringIO(); fields=['region_id','month','population_total','young_population_share','older_population_share','single_household_share','sale_price_per_m2','sale_price_yoy_pct','businesses_per_1000_people','vitality_index','housing_pressure_index','living_convenience_index','commerce_change_index']
    writer=csv.DictWriter(buf,fieldnames=fields); writer.writeheader()
    for r in rows:
        m=r.get('metrics',{}); d=r.get('derived',{}); idx=r.get('indexes',{})
        writer.writerow({'region_id':r.get('region_id'),'month':r.get('month'),'population_total':m.get('population_total'),'young_population_share':d.get('young_population_share'),'older_population_share':d.get('older_population_share'),'single_household_share':d.get('single_household_share'),'sale_price_per_m2':m.get('sale_price_per_m2'),'sale_price_yoy_pct':d.get('sale_price_yoy_pct'),'businesses_per_1000_people':d.get('businesses_per_1000_people'),'vitality_index':idx.get('vitality_index'),'housing_pressure_index':idx.get('housing_pressure_index'),'living_convenience_index':idx.get('living_convenience_index'),'commerce_change_index':idx.get('commerce_change_index')})
    return Response(buf.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename={region_id}.csv'})

