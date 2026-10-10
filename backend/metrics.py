from __future__ import annotations
import math
from statistics import median
from typing import Any

def safe_div(a, b, default=None):
    try:
        if b in (0, None): return default
        return a / b
    except (TypeError, ZeroDivisionError): return default

def pct_change(current, previous):
    if current is None or previous in (None, 0): return None
    v=safe_div((current-previous)*100, previous)
    return round(v,4) if v is not None else None

def share(part, total):
    if part is None or total in (None, 0): return None
    v=safe_div(part*100,total)
    return round(v,4) if v is not None else None

def median_or_none(values):
    vals=[float(x) for x in values if x is not None]
    return median(vals) if vals else None

def shannon_diversity(counts: list[float]) -> float | None:
    vals=[max(0,float(x)) for x in counts if x is not None]
    total=sum(vals)
    if total<=0: return None
    h=-sum((x/total)*math.log(x/total) for x in vals if x>0)
    max_h=math.log(len([x for x in vals if x>0])) if len([x for x in vals if x>0])>1 else 0
    return round((h/max_h)*100,2) if max_h else 0.0

def _per_1000(count, total):
    if total in (None, 0) or count is None:
        return None
    v=safe_div(float(count)*1000,float(total))
    return round(v,4) if v is not None else None

def compute_derived(metrics: dict[str,Any], previous: dict[str,Any] | None=None, year_ago: dict[str,Any] | None=None) -> dict[str,Any]:
    previous=previous or {}; year_ago=year_ago or {}
    total=metrics.get('population_total')
    households=metrics.get('households')
    young=(metrics.get('age_20_39') or 0)
    if metrics.get('age_65_plus') is not None:
        older=metrics.get('age_65_plus') or 0
        older_basis='65_plus'
        older_is_proxy=False
    elif metrics.get('age_60_plus') is not None:
        older=metrics.get('age_60_plus') or 0
        older_basis='60_plus_proxy'
        older_is_proxy=True
    else:
        older=0
        older_basis='unavailable'
        older_is_proxy=True
    single=(metrics.get('single_households') or 0)
    small=(metrics.get('one_person_households') or 0)+(metrics.get('two_person_households') or 0)
    apt_units=metrics.get('apartment_units')
    old_buildings=metrics.get('old_buildings_30y')
    all_buildings=metrics.get('building_count')
    sale_count=metrics.get('sale_count')
    store_count=metrics.get('business_count')
    categories=metrics.get('business_category_counts') or {}
    return {
      'population_mom_pct': pct_change(total, previous.get('population_total')) if total is not None else None,
      'population_yoy_pct': pct_change(total, year_ago.get('population_total')) if total is not None else None,
      'young_population_share': share(young,total),
      'older_population_share': share(older,total),
      'older_population_basis': older_basis,
      'older_population_is_proxy': older_is_proxy,
      'single_household_share': share(single,households),
      'young_single_household_share': share(metrics.get('single_age_20_39'), single) if metrics.get('single_age_20_39') is not None else None,
      'older_single_household_share': share(
          metrics.get('single_age_65_plus') if metrics.get('single_age_65_plus') is not None else metrics.get('single_age_60_plus'),
          single,
      ) if (metrics.get('single_age_65_plus') is not None or metrics.get('single_age_60_plus') is not None) else None,
      'small_household_share': share(small,households),
      'apartment_supply_proxy': share(apt_units,households),
      'old_building_share': share(old_buildings,all_buildings),
      'sale_price_yoy_pct': pct_change(metrics.get('sale_price_per_m2'), year_ago.get('sale_price_per_m2')) if metrics.get('sale_price_per_m2') is not None else None,
      'housing_turnover_pct': share(sale_count,apt_units),
      'jeonse_price_yoy_pct': pct_change(metrics.get('jeonse_price'), year_ago.get('jeonse_price')) if metrics.get('jeonse_price') is not None else None,
      'rent_count_yoy_pct': pct_change(metrics.get('rent_count'), year_ago.get('rent_count')) if metrics.get('rent_count') is not None else None,
      'monthly_rent_share': share(metrics.get('monthly_rent_count'), metrics.get('rent_count')),
      'businesses_per_1000_people': _per_1000(store_count,total),
      'business_net_change': (store_count - previous.get('business_count')) if store_count is not None and previous.get('business_count') is not None else None,
      'business_yoy_pct': pct_change(store_count, year_ago.get('business_count')) if store_count is not None else None,
      'business_diversity_index': shannon_diversity(list(categories.values())) if categories else None,
      'health_businesses_per_1000_people': _per_1000(metrics.get('health_business_count'),total),
      'education_businesses_per_1000_people': _per_1000(metrics.get('education_business_count'),total),
      'restaurant_businesses_per_1000_people': _per_1000(metrics.get('restaurant_count'),total),
      'cafe_businesses_per_1000_people': _per_1000(metrics.get('cafe_count'),total),
      'convenience_businesses_per_1000_people': _per_1000(metrics.get('convenience_store_count'),total),
      'auction_listings_per_1000_households': _per_1000(metrics.get('auction_listing_count'),households),
      'commercial_transaction_yoy_pct': pct_change(metrics.get('commercial_transaction_count'), year_ago.get('commercial_transaction_count')) if metrics.get('commercial_transaction_count') is not None else None,
    }

def data_confidence(sample_size: int | None, thresholds=(5,20)) -> str:
    if sample_size is None: return 'unknown'
    if sample_size < thresholds[0]: return 'low'
    if sample_size < thresholds[1]: return 'medium'
    return 'high'

def percentile_score(value, population: list[float]) -> float | None:
    vals=sorted(v for v in population if v is not None)
    if value is None or not vals: return None
    below=sum(v < value for v in vals); equal=sum(v == value for v in vals)
    return round(100*(below+0.5*equal)/len(vals),2)

def weighted_index(scores: dict[str,float|None], weights: dict[str,float], *, minimum_components: int=1) -> float | None:
    valid=[(k,v) for k,v in scores.items() if v is not None and k in weights]
    if len(valid) < minimum_components:
        return None
    denom=sum(weights[k] for k,_ in valid)
    return round(sum(v*weights[k] for k,v in valid)/denom,2) if denom else None
