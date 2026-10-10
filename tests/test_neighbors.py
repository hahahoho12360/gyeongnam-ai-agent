import pytest
from scripts.build_neighbors import compute, _normalize_code, _region_for_feature

def feature(code, coords, name=''):
    return {'type':'Feature','properties':{'EMD_CD':code,'EMD_KOR_NM':name},'geometry':{'type':'Polygon','coordinates':[coords]}}
def box(code,x,y):return feature(code,[(x,y),(x+10,y),(x+10,y+10),(x,y+10),(x,y)])
def master(*codes):return [{'id':c+'00','bjd_code':c+'00'} for c in codes]
def run(fs,rs):return compute({'features':fs},rs,source_crs='EPSG:5179')
def test_edge_not_corner_and_symmetry():
    codes=['48121101','48121102','48121103'];r=run([box(codes[0],1000000,1700000),box(codes[1],1000010,1700000),box(codes[2],1000020,1700010)],master(*codes))
    u=r['updates'];assert u[codes[0]+'00']['neighbors']==[codes[1]+'00'];assert u[codes[2]+'00']['neighbors']==[]
    assert u[codes[1]+'00']['neighbors']==[codes[0]+'00'];assert r['report']['validation_passed']
    assert u[codes[0]+'00']['neighbor_shared_boundary_m'][codes[1]+'00']==10
    assert 120<u[codes[0]+'00']['centroid']['lon']<140

def test_overlap_blocks_validation():
    codes=['48121101','48121102'];r=run([box(codes[0],1000000,1700000),box(codes[1],1000005,1700000)],master(*codes))
    assert not r['report']['validation_passed'];assert len(r['report']['overlaps'])==1;assert r['report']['neighbor_edges']==0

def test_missing_unknown_and_wrong_name_reported():
    r=run([box('48121101',1000000,1700000),box('48121103',1000040,1700000)],master('48121101','48121102'))
    assert r['report']['missing_regions']==['4812110200'];assert r['report']['unmatched_codes']==['48121103']
    f=box('48121101',1000000,1700000);f['properties']['EMD_KOR_NM']='wrong'
    assert run([f],[{'id':'4812110100','name':'right'}])['report']['name_mismatches']

def test_strict_codes_and_no_ri_rollup():
    for code in ('48121101.0','x48121101','48121101001','４８１２１１０１'):assert _normalize_code(code)==''
    assert _normalize_code('48121101')=='48121101'
    assert _region_for_feature('4812110101',{'4812110100':{'id':'4812110100'}}) is None

def test_invalid_geometry_and_scope():
    f=feature('48121101',[(0,0),(10,10),(0,10),(10,0),(0,0)])
    r=run([f,box('48221101',1000000,1700000)],master('48121101'))
    assert r['report']['invalid_features'];assert r['report']['outside_scope_features']==1

def test_full_gyeongnam_scope():
    r=compute({'features':[box('48121101',1000000,1700000),box('48221101',1000010,1700000)]},master('48121101','48221101'),source_crs='EPSG:5179',scope_prefix='48')
    assert r['report']['matched_regions']==2;assert r['report']['neighbor_edges']==1

def test_malformed_outside_code_does_not_block_changwon():
    f=box('1140-4구',1000040,1700000);f['properties']['COL_ADM_SE']='48890'
    r=run([box('48121101',1000000,1700000),f],master('48121101'))
    assert r['report']['validation_passed'];assert len(r['report']['outside_scope_invalid_codes'])==1
    f['properties']['COL_ADM_SE']='48120'
    assert not run([box('48121101',1000000,1700000),f],master('48121101'))['report']['validation_passed']

def test_apply_refusal_writes_report_and_never_saves_db(tmp_path):
    import subprocess,sys,json
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    geo=tmp_path/'geo.json';reg=tmp_path/'regions.json';out=tmp_path/'report.json'
    geo.write_text(json.dumps({'features':[box('48121101',1000000,1700000)]}))
    reg.write_text(json.dumps(master('48121101')))
    r=subprocess.run([sys.executable,str(root/'scripts/build_neighbors.py'),str(geo),'--regions-json',str(reg),'--source-crs','EPSG:5179','--source-url','test','--source-date','test','--output',str(out),'--apply'],capture_output=True,text=True)
    assert r.returncode!=0 and '적용 거부' in r.stderr
    assert json.loads(out.read_text())['report']['applied'] is False
