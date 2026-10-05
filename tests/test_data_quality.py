from backend.db import get_store
from backend.data_quality import quality_report


def test_quality_report_counts_demo_data():
    store=get_store()
    store.set('regions','r1',{'name':'테스트동','full_name':'경상남도 테스트시 테스트동'},merge=False)
    for i in range(100):
        month=f"{2020+i//12:04d}-{i%12+1:02d}"
        store.set('monthly_data',f'r1_{i}',{
            'region_id':'r1','month':month,
            'metrics':{'population_total':1000+i},
            'derived':{},'indexes':{},
            'freshness':{'data_confidence':'high','is_provisional':False,'fetched_at':'2026-10-05T00:00:00+00:00'},
        },merge=False)
    report=quality_report()
    assert report['minimum_100_points_met'] is True
    assert report['monthly_data_points'] >= 100
    assert report['regions_master_count'] >= 1
    assert report['period']['month_count'] >= 100
