from backend.metrics import pct_change, share, shannon_diversity, data_confidence, compute_derived
def test_basic_metrics():
    assert pct_change(110,100)==10
    assert share(25,100)==25
    assert 0 <= shannon_diversity([10,10,10]) <= 100
    assert data_confidence(2)=='low' and data_confidence(10)=='medium' and data_confidence(30)=='high'
def test_derived():
    d=compute_derived({'population_total':1000,'households':500,'age_20_39':250,'age_65_plus':200,'single_households':200,'one_person_households':200,'two_person_households':150,'apartment_units':400,'building_count':100,'old_buildings_30y':25,'sale_count':10,'rent_count':20,'monthly_rent_count':8,'business_count':100,'business_category_counts':{'a':50,'b':50}}, {'population_total':990,'business_count':98},{'population_total':950,'sale_price_per_m2':100})
    assert d['young_population_share']==25
    assert d['single_household_share']==40
    assert d['business_net_change']==2

def test_older_population_proxy_is_explicit():
    d=compute_derived({'population_total':1000,'households':500,'age_20_39':200,'age_60_plus':300})
    assert d['older_population_share']==30
    assert d['older_population_basis']=='60_plus_proxy'
    assert d['older_population_is_proxy'] is True


def test_exact_65_plus_overrides_proxy_and_single_age_shares():
    d=compute_derived({
        'population_total':1000,'households':500,'age_65_plus':220,'age_60_plus':300,
        'single_households':200,'single_age_20_39':80,'single_age_65_plus':50,
    })
    assert d['older_population_share']==22
    assert d['older_population_basis']=='65_plus'
    assert d['older_population_is_proxy'] is False
    assert d['young_single_household_share']==40
    assert d['older_single_household_share']==25
