"""공식 GeoJSON와 지역 snapshot을 대조하고 검토 자료를 생성한다. DB 저장 없음."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.build_neighbors import compute,_normalize_code

def verify(geojson, regions_json, output_dir):
    from shapely.geometry import shape,mapping
    from shapely.validation import explain_validity
    from shapely import transform
    from pyproj import Transformer
    data=json.loads(geojson.read_text(encoding='utf-8'));regions=json.loads(regions_json.read_text(encoding='utf-8'));known={str(r.get('bjd_code') or r['id']):r for r in regions if not r.get('is_demo')}
    sig={str(r.get('bjd_code') or r['id'])[:5]:r.get('sigungu','') for r in regions}
    inventory=[];candidates=[]
    for i,f in enumerate(data['features']):
        props=f['properties'];c=_normalize_code(props.get('EMD_CD'));g=shape(f['geometry']);name=props.get('EMD_KOR_NM') or props.get('EMD_NM');r=known.get(c+'00') if len(c)==8 else known.get(c)
        inventory.append({'feature':i,'emd_code':props.get('EMD_CD'),'bjd_code':c+'00' if len(c)==8 else c or None,'boundary_name':name,'valid_code':bool(c),'valid_geometry':g.is_valid,'geometry_issue':None if g.is_valid else explain_validity(g),'snapshot_id':r['id'] if r else None,'scope':'changwon' if c.startswith('4812') else 'outside_changwon'})
        if not c.startswith('4812'):continue
        if len(c)!=8:raise ValueError('Expected 8-digit EMD_CD')
        if r:candidates.append(r);continue
        district=sig.get(c[:5])
        if not district:raise ValueError('Cannot identify Changwon district from snapshot')
        rural=name.endswith(('읍','면'))
        candidates.append({'id':c+'00','bjd_code':c+'00','name':name,'full_name':f'경상남도 {district} {name}','sido':'경상남도','sigungu':district,'region_type':'eup_myeon' if rural else 'legal_dong','peer_group':'rural' if rural else 'urban','neighbors':[],'is_demo':False,'source':'VWorld LSMD_ADM_SECT_UMD_48_202609 경계 속성','master_code_status':'boundary_confirmed_not_independently_checked','monthly_data_status':'not_collected'})
    output_dir.mkdir(parents=True,exist_ok=True)
    def save(name,payload):
        (output_dir/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    source=json.loads(geojson.with_suffix('.provenance.json').read_text(encoding='utf-8'))
    if source['output_sha256']!=hashlib.sha256(geojson.read_bytes()).hexdigest():raise ValueError('GeoJSON checksum mismatch')
    save('gyeongnam_official_inventory_202609.json',inventory)
    save('changwon_boundary_master_202609.json',candidates)
    missing=[r for r in candidates if r['bjd_code'] not in known]
    save('changwon_missing_regions_202609.json',missing)
    reports={}
    for label,master in [('existing181',regions),('boundary204',candidates)]:
        result=compute(data,master);result['provenance']=source;result['report']['applied']=False;reports[label]=result
        save(f'changwon_official_{label}_validation.json',result)
    report=reports['boundary204']['report'];by={r['id']:r for r in candidates};fs={f['properties']['EMD_CD']+'00':f for f in data['features'] if _normalize_code(f['properties'].get('EMD_CD')).startswith('4812')};project=Transformer.from_crs('EPSG:4326','EPSG:5179',always_xy=True).transform;unproject=Transformer.from_crs('EPSG:5179','EPSG:4326',always_xy=True).transform
    review=[]
    for pair in report['overlaps']:
        a,b=pair['a'],pair['b'];ga=transform(shape(fs[a]['geometry']),project,interleaved=False);gb=transform(shape(fs[b]['geometry']),project,interleaved=False)
        pair.update({'a_name':by[a]['full_name'],'b_name':by[b]['full_name']})
        review.append({'type':'Feature','properties':pair,'geometry':mapping(transform(ga.intersection(gb),unproject,interleaved=False))})
    save('changwon_overlap_review_202609.geojson',{'type':'FeatureCollection','features':review})
    save('changwon_official_boundary204_validation.json',reports['boundary204'])
    summary={'source':source,'source_records':len(inventory),'valid_code_records':sum(x['valid_code'] for x in inventory),'invalid_code_records':[x for x in inventory if not x['valid_code']],'invalid_geometry_records':[x for x in inventory if not x['valid_geometry']],'changwon_boundaries':len(candidates),'missing_snapshot_regions':len(missing),'existing_master_validation':reports['existing181']['report'],'complete_boundary_master_validation':report,'firestore_applied':False,'note':'boundary204는 누락 후보를 포함한 오프라인 검증용 목록입니다.'}
    summary['note']='boundary204는 누락 후보를 포함한 오프라인 검증용 목록이며 신규 지역의 월별 데이터는 아직 수집하지 않았습니다.'
    save('official_boundary_verification_summary.json',summary)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--geojson',type=Path,default=ROOT/'data/boundaries/gyeongnam_legal_official_202609.geojson');p.add_argument('--regions-json',type=Path,default=ROOT/'data/boundaries/changwon_regions_snapshot.json');p.add_argument('--output-dir',type=Path,default=ROOT/'data/boundaries');a=p.parse_args();s=verify(a.geojson,a.regions_json,a.output_dir)
    print(json.dumps({k:s[k] for k in ('source_records','valid_code_records','changwon_boundaries','missing_snapshot_regions','firestore_applied')},ensure_ascii=False,indent=2));print('검증 통과:',s['complete_boundary_master_validation']['validation_passed']);raise SystemExit(0 if s['complete_boundary_master_validation']['validation_passed'] else 2)
