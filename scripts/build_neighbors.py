"""법정 읍면동 경계 검사/인접성 계산. 기본은 파일 출력만, --apply 명시 시 저장."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

def _normalize_code(value):
    s=str(value).strip() if value is not None else ''
    return s if s.isascii() and s.isdigit() and len(s) in (8,10) else ''

def _region_for_feature(code, by_code):
    key=code+'00' if len(code)==8 else code
    # 읍면동 자료만 허용: 법정리를 임의 부모로 합치지 않는다.
    return by_code[key]['id'] if key in by_code else None

def compute(payload, regions, *, code_field='EMD_CD', source_crs='EPSG:4326', scope_prefix='4812', min_shared_m=1.0):
    from shapely.geometry import shape
    from shapely.validation import explain_validity
    from shapely.ops import unary_union
    from shapely import transform
    from pyproj import Transformer
    if min_shared_m<=0: raise ValueError('min_shared_m must be positive')
    project=Transformer.from_crs(source_crs,'EPSG:5179',always_xy=True).transform
    unproject=Transformer.from_crs('EPSG:5179','EPSG:4326',always_xy=True).transform
    master=[r for r in regions if not r.get('is_demo') and str(r.get('bjd_code') or r['id']).startswith(scope_prefix)]
    by_code={str(r.get('bjd_code') or r['id']):r for r in master}
    if not master or len(by_code)!=len(master):raise ValueError('empty or duplicate region master')
    groups={}; invalid=[]; outside_invalid=[]; unmatched=[]; outside=0; names=[]
    for i,f in enumerate(payload.get('features',[])):
        props=f.get('properties') or {};code=_normalize_code(props.get(code_field))
        if not code:
            item={'feature':i,'reason':'invalid_code','value':props.get(code_field),'name':props.get('EMD_KOR_NM') or props.get('EMD_NM')}
            district=str(props.get('COL_ADM_SE') or '')
            if district.isdigit() and not district.startswith(scope_prefix):
                outside_invalid.append(item);outside+=1
            else:invalid.append(item)
            continue
        if not code.startswith(scope_prefix):outside+=1;continue
        rid=_region_for_feature(code,by_code)
        if not rid:unmatched.append(code);continue
        try:
            g=shape(f['geometry'])
            if g.is_empty or g.geom_type not in ('Polygon','MultiPolygon') or not g.is_valid:raise ValueError(explain_validity(g))
            g=transform(g,project,interleaved=False)
            if not g.is_valid:raise ValueError('invalid projected polygon')
        except Exception as e:invalid.append({'code':code,'reason':str(e)});continue
        expected=by_code[code+'00' if len(code)==8 else code].get('name')
        actual=props.get('EMD_KOR_NM')
        if actual and expected and actual!=expected:names.append({'code':code,'master':expected,'boundary':actual})
        groups.setdefault(rid,[]).append(g)
    geoms={k:unary_union(v) for k,v in groups.items()}
    missing=sorted(set(r['id'] for r in master)-set(geoms)); ids=sorted(geoms)
    neighbors={k:[] for k in ids}; lengths={k:{} for k in ids}; overlaps=[]
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            ga,gb=geoms[a],geoms[b]
            if not ga.intersects(gb):continue
            area=ga.intersection(gb).area
            length=ga.boundary.intersection(gb.boundary).length
            if area>0.01:
                overlaps.append({'a':a,'b':b,'area_m2':round(area,4),'shared_boundary_m':round(length,3)})
                continue
            if length>=min_shared_m:
                neighbors[a].append(b);neighbors[b].append(a)
                lengths[a][b]=length;lengths[b][a]=length
    updates={}
    for rid,g in geoms.items():
        c=transform(g.centroid,unproject,interleaved=False)
        updates[rid]={'neighbors':sorted(neighbors[rid],key=lambda x:(-lengths[rid][x],x)), 'neighbor_shared_boundary_m':{k:round(v,3) for k,v in lengths[rid].items()},'centroid':{'lon':round(c.x,7),'lat':round(c.y,7)}}
    report={'scope_prefix':scope_prefix,'features':len(payload.get('features',[])),'master_regions':len(master),'matched_regions':len(geoms),'missing_regions':missing,'unmatched_codes':sorted(set(unmatched)),'invalid_features':invalid,'name_mismatches':names,'outside_scope_features':outside,'outside_scope_invalid_codes':outside_invalid,'overlaps':overlaps,'neighbor_edges':sum(map(len,neighbors.values()))//2,'isolated_regions':[k for k in ids if not neighbors[k]],'method':'shared_boundary','min_shared_m':min_shared_m,'source_crs':source_crs,'measurement_crs':'EPSG:5179'}
    report['graph_symmetric']=all(a in neighbors[b] for a in ids for b in neighbors[a])
    report['self_edges']=sum(a in neighbors[a] for a in ids)
    report['validation_passed']=not (missing or unmatched or invalid or names or overlaps)
    return {'report':report,'updates':updates}

def main():
    p=argparse.ArgumentParser();p.add_argument('geojson',type=Path);p.add_argument('--regions-json',type=Path);p.add_argument('--code-field',default='EMD_CD');p.add_argument('--source-crs',required=True);p.add_argument('--scope-prefix',default='4812');p.add_argument('--min-shared-m',type=float,default=1.0);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-url',required=True);p.add_argument('--source-date',required=True);p.add_argument('--diagnostic-only',action='store_true');p.add_argument('--apply',action='store_true');a=p.parse_args()
    from backend.db import get_store
    regions=json.loads(a.regions_json.read_text()) if a.regions_json else get_store().list('regions')
    result=compute(json.loads(a.geojson.read_text()),regions,code_field=a.code_field,source_crs=a.source_crs,scope_prefix=a.scope_prefix,min_shared_m=a.min_shared_m)
    provenance={'source_url':a.source_url,'source_date':a.source_date,'sha256':hashlib.sha256(a.geojson.read_bytes()).hexdigest(),'diagnostic_only':a.diagnostic_only}
    result['provenance']=provenance;result['report']['applied']=False
    a.output.parent.mkdir(parents=True,exist_ok=True)
    def save():a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    if a.apply:
        if a.diagnostic_only or a.regions_json or not result['report']['validation_passed']:raise SystemExit('적용 거부: 진단용/오프라인 master/검증 실패. 보고서가 저장되었습니다.')
        from backend.db import FirestoreStore
        store=get_store()
        if not isinstance(store,FirestoreStore):raise SystemExit('적용은 실제 Firestore 환경에서만 가능합니다.')
        if len(result['updates'])>500:raise SystemExit('원자적 적용 한도 초과: 범위를 나누어 검토하세요.')
        backup=a.output.with_suffix('.backup.json')
        backup.write_text(json.dumps(regions,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        batch=store.client.batch()
        for rid,update in result['updates'].items():batch.update(store.client.collection('regions').document(rid),{**update,'neighbor_source':provenance,'neighbor_method':'shared_boundary'})
        batch.commit()
        result['report']['applied']=True
        save()
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in result['report'].items()},ensure_ascii=False,indent=2))
    return 0 if result['report']['validation_passed'] else 2
if __name__=='__main__':raise SystemExit(main())
