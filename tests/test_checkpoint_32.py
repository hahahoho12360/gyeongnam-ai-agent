from backend.indexes import compute_index_rows, methodology_payload
from backend.metrics import compute_derived, weighted_index


def test_commerce_density_metrics():
    d=compute_derived({
        'population_total':1000,
        'households':400,
        'business_count':100,
        'restaurant_count':20,
        'cafe_count':10,
        'convenience_store_count':5,
        'health_business_count':4,
        'education_business_count':3,
        'business_category_counts':{'a':50,'b':50},
    })
    assert d['businesses_per_1000_people']==100.0
    assert d['restaurant_businesses_per_1000_people']==20.0
    assert d['cafe_businesses_per_1000_people']==10.0
    assert d['convenience_businesses_per_1000_people']==5.0


def test_weighted_index_minimum_components():
    assert weighted_index({'a':50,'b':None},{'a':.5,'b':.5},minimum_components=2) is None
    assert weighted_index({'a':50,'b':100},{'a':.5,'b':.5},minimum_components=2)==75.0


def test_changwon_index_computation_and_meta():
    rows=[
      {'region_id':'1','derived':{
        'population_yoy_pct':1,'young_population_share':30,'housing_turnover_pct':2,
        'businesses_per_1000_people':30,'sale_price_yoy_pct':3,'rent_count_yoy_pct':1,
        'monthly_rent_share':40,'old_building_share':20,'business_diversity_index':70,
        'health_businesses_per_1000_people':2,'education_businesses_per_1000_people':3,
        'apartment_supply_proxy':80,'restaurant_businesses_per_1000_people':10,
        'cafe_businesses_per_1000_people':5,'convenience_businesses_per_1000_people':2,
      },'metrics':{}},
      {'region_id':'2','derived':{
        'population_yoy_pct':-1,'young_population_share':20,'housing_turnover_pct':1,
        'businesses_per_1000_people':20,'sale_price_yoy_pct':-2,'rent_count_yoy_pct':-1,
        'monthly_rent_share':30,'old_building_share':30,'business_diversity_index':50,
        'health_businesses_per_1000_people':1,'education_businesses_per_1000_people':2,
        'apartment_supply_proxy':60,'restaurant_businesses_per_1000_people':8,
        'cafe_businesses_per_1000_people':3,'convenience_businesses_per_1000_people':1,
      },'metrics':{}},
    ]
    out=compute_index_rows(rows)
    assert set(out['1'])=={'vitality_index','housing_pressure_index','living_convenience_index','commerce_change_index'}
    assert out['1']['vitality_index'] > out['2']['vitality_index']
    meta=methodology_payload(comparison_scope='changwon',month='2026-09',region_count=181)
    assert meta['comparison_scope']=='changwon'
    assert meta['official_statistic'] is False
