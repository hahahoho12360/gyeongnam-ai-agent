import io,json,zipfile
import shapefile
from pathlib import Path
from scripts.convert_legal_boundaries import convert

def test_zip_conversion_preserves_code_name_crs_and_geometry(tmp_path):
    shp,shx,dbf=io.BytesIO(),io.BytesIO(),io.BytesIO()
    w=shapefile.Writer(shp=shp,shx=shx,dbf=dbf,shapeType=shapefile.POLYGON,encoding='euc-kr')
    w.field('EMD_CD','C',8);w.field('EMD_NM','C',50)
    w.poly([[(200000,300000),(200000,300010),(200010,300010),(200010,300000),(200000,300000)]]);w.record('48125106','대성동1가');w.close()
    from pyproj import CRS
    source=tmp_path/'source.zip'
    with zipfile.ZipFile(source,'w') as z:
        for ext,buf in [('shp',shp),('shx',shx),('dbf',dbf)]:z.writestr('layer.'+ext,buf.getvalue())
        z.writestr('layer.prj',CRS.from_epsg(5186).to_wkt());z.writestr('layer.cst','EUC-KR')
    output=tmp_path/'converted.geojson';report=convert(source,output);f=json.loads(output.read_text())['features'][0]
    assert report['source_crs_epsg']==5186 and report['simplified'] is False
    assert not report['invalid_source_geometries']
    assert f['properties']['EMD_CD']=='48125106' and f['properties']['EMD_KOR_NM']=='대성동1가'
    assert len(f['geometry']['coordinates'][0])==5
    lon,lat=f['geometry']['coordinates'][0][0];assert 120<lon<140 and 30<lat<40
