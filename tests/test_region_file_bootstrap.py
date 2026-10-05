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
