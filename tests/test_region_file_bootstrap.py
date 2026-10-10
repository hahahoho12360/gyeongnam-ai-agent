from scripts.bootstrap_regions_file import normalize_gyeongnam_regions


def test_official_legal_dong_csv_rollup_rule():
    rows=[
        {'법정동코드':'4800000000','시도명':'경상남도','시군구명':'','읍면동명':'','리명':'','생성일자':'19880101'},
        {'법정동코드':'4812300000','시도명':'경상남도','시군구명':'창원시 성산구','읍면동명':'','리명':'','생성일자':'20100701'},
        {'법정동코드':'4812310100','시도명':'경상남도','시군구명':'창원시 성산구','읍면동명':'토월동','리명':'','생성일자':'19880101'},
        {'법정동코드':'4882025021','시도명':'경상남도','시군구명':'거창군','읍면동명':'거창읍','리명':'중앙리','생성일자':'19880101'},
        {'법정동코드':'4882025000','시도명':'경상남도','시군구명':'거창군','읍면동명':'거창읍','리명':'','생성일자':'19880101'},
        {'법정동코드':'2600000000','시도명':'부산광역시','시군구명':'','읍면동명':'','리명':'','생성일자':'19880101'},
    ]
    out=normalize_gyeongnam_regions(rows)
    ids={x['id'] for x in out}
    assert ids=={'4812310100','4882025000'}
    rural=next(x for x in out if x['id']=='4882025000')
    urban=next(x for x in out if x['id']=='4812310100')
    assert rural['region_type']=='eup_myeon' and rural['peer_group']=='rural'
    assert urban['region_type']=='legal_dong' and urban['peer_group']=='urban'


def test_legal_dong_ga_suffix_is_not_dropped():
    from scripts.bootstrap_regions import _is_gyeongnam_eup_myeon_dong
    rows=[{'법정동코드':'4812510600','시도명':'경상남도','시군구명':'창원시 마산합포구','읍면동명':'대성동1가','리명':''}]
    out=normalize_gyeongnam_regions(rows)
    assert out[0]['name']=='대성동1가' and out[0]['region_type']=='legal_dong'
    assert _is_gyeongnam_eup_myeon_dong({'sido_cd':'48','umd_cd':'106','ri_cd':'00','locallow_nm':'대성동1가'})
    rows[0]['법정동코드']='4812510601';assert normalize_gyeongnam_regions(rows)==[]

def test_master_refresh_preserves_neighbors_and_metadata():
    from backend.db import MemoryStore
    from scripts.region_master_utils import upsert_region_master
    s=MemoryStore();s.set('regions','4812510600',{'neighbors':['4812510700'],'centroid':{'lon':128,'lat':35},'custom':'keep'})
    upsert_region_master(s,{'id':'4812510600','name':'대성동1가','neighbors':[]})
    r=s.get('regions','4812510600');assert r['neighbors']==['4812510700'] and r['custom']=='keep' and r['centroid']['lon']==128
    upsert_region_master(s,{'id':'4812510700','name':'대성동2가','neighbors':[]});assert s.get('regions','4812510700')['neighbors']==[]
