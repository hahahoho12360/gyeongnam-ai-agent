from scripts.collect.data_go_kr import DataGoKrClient
from scripts.collect.adapters import (
    aggregate_apartment_sales, aggregate_apartment_rent, aggregate_commerce, aggregate_buildings, aggregate_population_rows
)

REGIONS=[{'id':'4812310100','bjd_code':'4812310100','name':'상남동','full_name':'경상남도 창원시 성산구 상남동'}]

def test_xml_items_parser():
    xml='''<response><header><resultCode>00</resultCode><resultMsg>NORMAL</resultMsg></header><body><items><item><sggCd>48123</sggCd><umdNm>상남동</umdNm><dealAmount>40,000</dealAmount></item><item><sggCd>48123</sggCd><umdNm>상남동</umdNm><dealAmount>50,000</dealAmount></item></items><totalCount>2</totalCount></body></response>'''
    payload=DataGoKrClient._xml_to_dict(xml)
    items=DataGoKrClient.items(payload)
    assert len(items)==2
    assert DataGoKrClient.total_count(payload)==2

def test_sale_and_rent_aggregation():
    sales=[{'sggCd':'48123','umdNm':'상남동','dealAmount':'40,000','excluUseAr':'84.9'}, {'sggCd':'48123','umdNm':'상남동','dealAmount':'42,000','excluUseAr':'84.9'}]
    s=aggregate_apartment_sales(sales,REGIONS,'2026-09','48123')['4812310100']
    assert s['sale_count']==2 and s['sale_price_per_m2']>0
    rents=[{'sggCd':'48123','umdNm':'상남동','deposit':'30,000','monthlyRent':'0','excluUseAr':'84.9'}, {'sggCd':'48123','umdNm':'상남동','deposit':'5,000','monthlyRent':'80','excluUseAr':'84.9'}]
    r=aggregate_apartment_rent(rents,REGIONS,'2026-09','48123')['4812310100']
    assert r['rent_count']==2 and r['jeonse_count']==1 and r['monthly_rent_count']==1

def test_commerce_and_building_aggregation():
    commerce=[
      {'sggCd':'48123','lnoAdr':'경상남도 창원시 성산구 상남동 1','indsLclsNm':'음식','indsSclsNm':'카페'},
      {'sggCd':'48123','lnoAdr':'경상남도 창원시 성산구 상남동 2','indsLclsNm':'의료','indsSclsNm':'약국'},
    ]
    c=aggregate_commerce(commerce,REGIONS,'48123')['4812310100']
    assert c['business_count']==2 and c['cafe_count']==1 and c['health_business_count']==1
    buildings=[{'sggCd':'48123','umdNm':'상남동','mainPurpsCdNm':'공동주택','totArea':'1000','hhldCnt':'20','useAprDay':'19900101'}]
    b=aggregate_buildings(buildings,REGIONS,sigungu_code='48123')['4812310100']
    assert b['building_count']==1 and b['old_buildings_30y']==1

from scripts.collect.adapters import (
    aggregate_age_rows, aggregate_single_household_rows, aggregate_household_size_rows,
    aggregate_birth_death_rows,
)


def test_sex_specific_age_buckets_are_combined():
    rows=[{
        'sggCd':'48123','umdNm':'상남동',
        '만20~29세남자':'100','만20~29세여자':'120',
        '만30~39세남자':'90','만30~39세여자':'110',
        '만60~69세남자':'80','만60~69세여자':'100',
        '만70~79세남자':'40','만70~79세여자':'60',
        '만80~89세남자':'10','만80~89세여자':'20',
        '만90~99세남자':'1','만90~99세여자':'3',
        '만100세이상남자':'1','만100세이상여자':'2',
    }]
    row=aggregate_age_rows(rows,REGIONS,'48123')['4812310100']
    assert row['age_20_39']==420
    assert row['age_60_plus']==317
    assert row['age_100_plus']==3
    assert 'age_65_plus' not in row


def test_single_household_age_buckets_and_totals():
    rows=[{
        'sggCd':'48123','umdNm':'상남동','남자세대수':'200','여자세대수':'250',
        '만20~29세남자':'50','만20~29세여자':'60',
        '만30~39세남자':'40','만30~39세여자':'50',
        '만60~69세남자':'20','만60~69세여자':'30',
        '만70~79세남자':'10','만70~79세여자':'20',
    }]
    row=aggregate_single_household_rows(rows,REGIONS,'48123')['4812310100']
    assert row['single_households']==450
    assert row['single_age_20_39']==200
    assert row['single_age_60_plus']==80



def test_single_household_official_15108085_fields_and_sum():
    regions=[{'id':'4812313300','bjd_code':'4812313300','name':'남양동','full_name':'경상남도 창원시 성산구 남양동'}]
    rows=[
      {'statsYm':'202609','stdgCd':'4812313300','stdgNm':'남양동','totHhCnt':'100','maleHhCnt':'40','femlHhCnt':'60',
       'male20AgeHhCnt':'10','feml20AgeHhCnt':'15','male30AgeHhCnt':'12','feml30AgeHhCnt':'18',
       'male60AgeHhCnt':'4','feml60AgeHhCnt':'6','male70AgeHhCnt':'2','feml70AgeHhCnt':'3','male100AgeHhCnt':'0','feml100AgeHhCnt':'1'},
      {'statsYm':'202609','stdgCd':'4812313300','stdgNm':'남양동','totHhCnt':'20','maleHhCnt':'8','femlHhCnt':'12',
       'male20AgeHhCnt':'2','feml20AgeHhCnt':'3','male30AgeHhCnt':'1','feml30AgeHhCnt':'4',
       'male60AgeHhCnt':'1','feml60AgeHhCnt':'2','male70AgeHhCnt':'1','feml70AgeHhCnt':'0','male100AgeHhCnt':'0','feml100AgeHhCnt':'0'},
    ]
    row=aggregate_single_household_rows(rows,regions)['4812313300']
    assert row['single_households']==120
    assert row['single_male_households']==48
    assert row['single_female_households']==72
    assert row['single_age_20_39']==65
    assert row['single_age_60_plus']==20
    assert row['single_age_100_plus']==1
    assert row['single_source_rows']==2

def test_household_size_detailed_five_plus_and_birth_death():
    rows=[{
        'sggCd':'48123','umdNm':'상남동',
        '1인세대수':'100','2인세대수':'80','3인세대수':'50','4인세대수':'40',
        '5인세대수':'10','6인세대수':'5','7인세대수':'2','8인세대수':'1','9인세대수':'1','10인이상세대수':'1',
    }]
    row=aggregate_household_size_rows(rows,REGIONS,'48123')['4812310100']
    assert row['five_plus_households']==20
    assert row['households']==290
    bd=aggregate_birth_death_rows([{'sggCd':'48123','umdNm':'상남동','출생등록자수':'12','사망말소자수':'9'}],REGIONS,'48123')['4812310100']
    assert bd['natural_change']==3


def test_population_official_fields_and_tongban_sum():
    regions=[{'id':'1111014000','bjd_code':'1111014000','name':'삼청동','full_name':'서울특별시 종로구 삼청동'}]
    rows=[
      {'statsYm':'202210','stdgCd':'1111014000','stdgNm':'삼청동','admmCd':'1111054000','tong':'1','ban':'1','totNmprCnt':'60','hhCnt':'25','maleNmprCnt':'31','femlNmprCnt':'29'},
      {'statsYm':'202210','stdgCd':'1111014000','stdgNm':'삼청동','admmCd':'1111054000','tong':'1','ban':'2','totNmprCnt':'27','hhCnt':'20','maleNmprCnt':'9','femlNmprCnt':'18'},
    ]
    row=aggregate_population_rows(rows,regions)['1111014000']
    assert row['population_total']==87
    assert row['households']==45
    assert row['population_male']==40
    assert row['population_female']==47
    assert row['persons_per_household']==round(87/45,4)
    assert row['sex_ratio']==round(40/47,4)
    assert row['population_source_rows']==2


def test_population_legal_ri_rolls_up_to_parent_eup_myeon():
    regions=[{'id':'4888031000','bjd_code':'4888031000','name':'가상면','full_name':'경상남도 가상군 가상면'}]
    rows=[{'statsYm':'202609','stdgCd':'4888031011','stdgNm':'가상리','totNmprCnt':'100','hhCnt':'50','maleNmprCnt':'52','femlNmprCnt':'48'}]
    row=aggregate_population_rows(rows,regions)['4888031000']
    assert row['population_total']==100 and row['households']==50


def test_population_response_capital_response_head_items_parser():
    xml='''<Response><head><resultCode>0</resultCode><resultMsg>NORMAL_SERVICE</resultMsg><totalCount>23</totalCount><numOfRows>10</numOfRows><pageNo>1</pageNo></head><items><item><statsYm>202210</statsYm><stdgCd>1111014000</stdgCd><stdgNm>삼청동</stdgNm><totNmprCnt>60</totNmprCnt><hhCnt>25</hhCnt><maleNmprCnt>31</maleNmprCnt><femlNmprCnt>29</femlNmprCnt></item></items></Response>'''
    payload=DataGoKrClient._xml_to_dict(xml)
    assert DataGoKrClient.error_message(payload) is None
    items=DataGoKrClient.items(payload)
    assert len(items)==1 and items[0]['stdgNm']=='삼청동'
    assert DataGoKrClient.total_count(payload)==23


def test_age_population_official_15108074_fields():
    rows=[{
        'stdgCd':'4812313300','stdgNm':'남양동',
        'male20AgeNmprCnt':'100','feml20AgeNmprCnt':'120',
        'male30AgeNmprCnt':'90','feml30AgeNmprCnt':'110',
        'male60AgeNmprCnt':'80','feml60AgeNmprCnt':'100',
        'male70AgeNmprCnt':'40','feml70AgeNmprCnt':'60',
        'male80AgeNmprCnt':'10','feml80AgeNmprCnt':'20',
        'male90AgeNmprCnt':'1','feml90AgeNmprCnt':'3',
        'male100AgeNmprCnt':'1','feml100AgeNmprCnt':'2',
    }]
    regions=[{'id':'4812313300','bjd_code':'4812313300','name':'남양동','full_name':'경상남도 창원시 성산구 남양동'}]
    row=aggregate_age_rows(rows,regions)['4812313300']
    assert row['age_20_39']==420
    assert row['age_60_plus']==317
    assert row['age_100_plus']==3
    assert row['age_20_29']==220
    assert row['age_source_rows']==1


def test_age_population_multiple_rows_are_summed():
    rows=[
      {'stdgCd':'1111014000','stdgNm':'삼청동','male20AgeNmprCnt':'10','feml20AgeNmprCnt':'20','male30AgeNmprCnt':'5','feml30AgeNmprCnt':'5'},
      {'stdgCd':'1111014000','stdgNm':'삼청동','male20AgeNmprCnt':'3','feml20AgeNmprCnt':'7','male30AgeNmprCnt':'2','feml30AgeNmprCnt':'3'},
    ]
    regions=[{'id':'1111014000','bjd_code':'1111014000','name':'삼청동','full_name':'서울특별시 종로구 삼청동'}]
    row=aggregate_age_rows(rows,regions)['1111014000']
    assert row['age_20_39']==55
    assert row['age_source_rows']==2


def test_kapt_v4_json_body_items_parser():
    payload={
      'header': {'resultCode':'00','resultMsg':'NORMAL_SERVICE'},
      'body': {
        'items': [{'bjdCode':'4812313300','kaptCode':'A001','kaptName':'가상아파트'}],
        'numOfRows':'1','pageNo':'1','totalCount':'1'
      }
    }
    assert DataGoKrClient.error_message(payload) is None
    rows=DataGoKrClient.items(payload)
    assert len(rows)==1 and rows[0]['kaptCode']=='A001'
    assert DataGoKrClient.total_count(payload)==1
