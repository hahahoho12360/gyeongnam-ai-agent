"""VWorld 법정 읍면동 SHP ZIP을 단순화 없는 EPSG:4326 GeoJSON로 변환."""
from __future__ import annotations
import argparse, hashlib, io, json, zipfile
from pathlib import Path

def convert(source: Path, output: Path):
    import shapefile
    from pyproj import CRS, Transformer
    from shapely.geometry import shape, mapping
    from shapely import transform
    from shapely.validation import explain_validity
    with zipfile.ZipFile(source) as z:
        shps=[n for n in z.namelist() if n.lower().endswith('.shp')]
        if len(shps)!=1:raise ValueError('정확히 한 SHP 레이어가 필요합니다.')
        stem=shps[0][:-4]
        def raw(ext):return z.read(stem+ext)
        crs=CRS.from_wkt(raw('.prj').decode('utf-8-sig'))
        encoding=raw('.cst').decode('ascii').strip() if stem+'.cst' in z.namelist() else 'euc-kr'
        reader=shapefile.Reader(shp=io.BytesIO(raw('.shp')),shx=io.BytesIO(raw('.shx')),dbf=io.BytesIO(raw('.dbf')),encoding=encoding)
        fields=[f[0] for f in reader.fields[1:]];project=Transformer.from_crs(crs,'EPSG:4326',always_xy=True).transform
        fs=[];invalid=[]
        for sr in reader.iterShapeRecords():
            props=dict(zip(fields,sr.record));g=shape(sr.shape.__geo_interface__)
            if not g.is_valid:invalid.append({'code':props.get('EMD_CD'),'name':props.get('EMD_NM'),'reason':explain_validity(g)})
            props['EMD_KOR_NM']=props.get('EMD_NM')
            fs.append({'type':'Feature','properties':props,'geometry':mapping(transform(g,project,interleaved=False))})
    metadata={'source_file':source.name,'source_layer':stem,'source_url':'https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?dsId=30603','source_version':stem.rsplit('_',1)[-1],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_crs_wkt':crs.to_wkt(),'source_crs_epsg':crs.to_epsg(min_confidence=20),'output_crs':'EPSG:4326','encoding':encoding,'simplified':False,'features':len(fs),'unique_codes':len(set(f['properties']['EMD_CD'] for f in fs)),'invalid_source_geometries':invalid}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'type':'FeatureCollection','features':fs},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    metadata['output_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.provenance.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return metadata

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('zip',type=Path);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(convert(a.zip,a.output),ensure_ascii=False,indent=2))
