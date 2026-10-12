import json
from copy import deepcopy
from pathlib import Path
from scripts.population_only_derived import population_derived,plans,write_and_verify
from scripts.population_followup_step import should_continue
from scripts.population_one_month import original_sources_verified


def test_missing_numerators_stay_null_and_real_zero_is_preserved():
    d=population_derived({'population_total':100,'households':50})
    assert d['young_population_share'] is None
    assert d['single_household_share'] is None
    assert d['small_household_share'] is None
    d=population_derived({'population_total':100,'households':50,'age_20_39':0,'single_households':0})
    assert d['young_population_share']==0
    assert d['single_household_share']==0
    assert d['young_single_household_share'] is None


def test_population_changes_and_age_proxy():
    d=population_derived({'population_total':110,'households':60,'age_20_39':22,'age_60_plus':33,
        'single_households':15},{'population_total':100,'households':50},{'population_total':100})
    assert d['population_mom_pct']==10 and d['population_yoy_pct']==10
    assert d['young_population_share']==20 and d['single_household_share']==25
    assert d['older_population_basis']=='60_plus_proxy' and d['older_population_is_proxy']


def test_unverified_comparison_month_never_used():
    rows=[{'id':'x_2024-09','region_id':'x','month':'2024-09','metrics':{'population_total':110}},
        {'id':'x_2024-08','region_id':'x','month':'2024-08','metrics':{'population_total':10}}]
    p=plans(rows,{'2024-09':{'status':'passed'},'2024-08':{'status':'failed'}},{'2024-09'})
    assert p[0]['values']['population_mom_pct'] is None
    assert not p[0]['meta']['previous_month_verified']


def test_provider_outage_halts_but_one_month_validation_issue_does_not():
    assert not should_continue({'status':'paused'},{'consecutive_failures':6})
    assert not should_continue({'status':'paused'},{'recent_requests':[{'outcome':'api_rate_limit'}]})
    assert not should_continue({}, {}, timed_out=True)
    assert should_continue({'status':'blocked','reason':'UnresolvedMonth'}, {})
    assert should_continue({'status':'complete'}, {})
    assert not should_continue({'status':'blocked','reason':'RuntimeError'}, {})


def test_totals_alone_do_not_allow_skip_without_capture_provenance():
    master={'x':{}}
    assert not original_sources_verified([{'region_id':'x'}],master)
    sources={s:{'collection_method':'3.7.1-final','status':'no_data','source_as_of':'2024-09-30'} for s in ['population','age_population','single_household']}
    assert original_sources_verified([{'region_id':'x','month':'2024-09','freshness':{'sources':sources}}],master)
    assert not original_sources_verified([{'region_id':'x','month':'2024-10','freshness':{'sources':sources}}],master)


class FakeStore:
    def __init__(self):
        base={'id':'x_2024-09','region_id':'x','month':'2024-09',
            'derived':{'sale_price_yoy_pct':7,'businesses_per_1000_people':5},
            'indexes':{'vitality_index':42},'indexes_need_recompute':True}
        self.data={'monthly_data':{base['id']:deepcopy(base)},'region_latest':{'x':{**deepcopy(base),'id':'x'}}}
        self.client=self
    def list(self,c):return list(self.data[c].values())
    def collection(self,c):
        class Collection:
            def document(self,doc):return (c,doc)
        return Collection()
    def batch(self):
        owner=self
        class Batch:
            def __init__(self):self.ops=[]
            def update(self,ref,fields):self.ops.append((ref,fields))
            def commit(self):
                for (c,doc),fields in self.ops:
                    for key,value in fields.items():
                        if '.' in key:
                            parent,child=key.split('.',1);owner.data[c][doc].setdefault(parent,{})[child]=value
                        else:owner.data[c][doc][key]=value
        return Batch()


def test_readback_preserves_other_derived_and_indexes():
    store=FakeStore()
    patches=[{'id':'x_2024-09','region_id':'x','month':'2024-09',
        'values':{'population_mom_pct':10,'single_household_share':None},'meta':{'population_only':True}}]
    assert write_and_verify(store,patches)==[]
    for collection,doc in [('monthly_data','x_2024-09'),('region_latest','x')]:
        row=store.data[collection][doc]
        assert row['derived']['sale_price_yoy_pct']==7
        assert row['derived']['businesses_per_1000_people']==5
        assert row['derived']['single_household_share'] is None
        assert row['indexes']['vitality_index']==42
        assert row['indexes_need_recompute'] is True


def test_followup_remaining_12_months_and_no_nested_writer_lock():
    import yaml
    root=Path(__file__).resolve().parents[1]
    w=yaml.safe_load((root/'.github/workflows/changwon-population-followup.yml').read_text())
    trigger=w.get('on',w.get(True))
    assert set(trigger)=={'workflow_dispatch','push'}
    jobs=w['jobs'];monthly=[(k,v) for k,v in jobs.items() if k.startswith('month_')]
    assert len(monthly)==12
    assert monthly[0][1]['with']['month']=='2025-09'
    assert monthly[-1][1]['with']['month']=='2026-08'
    for i,(key,job) in enumerate(monthly):
        if i:assert job['needs']==[monthly[i-1][0]]
    assert jobs['final_population_recalculation']['if']=='${{ always() }}'
    worker=yaml.safe_load((root/'.github/workflows/changwon-population-month-worker.yml').read_text())
    assert 'concurrency' not in worker
    assert worker['jobs']['month']['timeout-minutes']<360
    assert 12*worker['jobs']['month']['timeout-minutes']>540
