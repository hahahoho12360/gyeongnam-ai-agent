"""Question-aware, same-month peers. Missing measurements never become zero."""
import hashlib
import math
import random
import re

TOPICS = {
    'youth': ('청년|젊|20대|30대|대학생', '청년', {'young_population_share': 5, 'population_total': 1, 'single_household_share': 1}),
    'aging': ('고령|노인|어르신|노후|65세', '고령 인구', {'older_population_share': 5, 'population_total': 1}),
    'single': ('1인|일인|혼자|독거|세대|가구', '가구 구성', {'single_household_share': 5, 'young_population_share': 1, 'population_total': 1}),
    'rental': ('전세|월세|임대|보증금', '임대 주거', {'jeonse_price': 4, 'monthly_rent_share': 3, 'rent_count': 1}),
    'housing': ('매매|집값|실거래|아파트|주택|부동산|주거', '주택 매매', {'sale_price_per_m2': 5, 'apartment_supply_proxy': 2, 'housing_turnover_pct': 1}),
    'commerce': ('상권|상가|상점|업소|매장|소매|병원|의료|학원|가게|카페|식당|음식|생활편의|편의|창업|점포|사업', '상권·생활편의', {'businesses_per_1000_people': 4, 'business_diversity_index': 2, 'business_count': 1}),
    'building': ('건축|건물|단지|노후건축', '건축·주택 공급', {'old_building_share': 4, 'apartment_supply_proxy': 3, 'building_count': 1}),
    'population': ('인구|주민|사람|전입|전출', '인구', {'population_total': 4, 'population_yoy_pct': 3, 'young_population_share': 1}),
}
GENERAL = {'population_total': 2, 'young_population_share': 1, 'older_population_share': 1, 'single_household_share': 1, 'sale_price_per_m2': 1, 'businesses_per_1000_people': 1}


def topic_weights(question):
    matches = [(len(re.findall(pattern, question or '')), key, label, weights) for key, (pattern, label, weights) in TOPICS.items()]
    score, key, label, weights = max(matches, key=lambda item: item[0])
    return (key, label, weights) if score else ('general', '종합', GENERAL)


def measured(row, key):
    metrics = row.get('metrics') or {}
    derived = row.get('derived') or {}
    if row.get('freshness',{}).get('is_demo'): return None
    sources=row.get('freshness',{}).get('sources',{})
    source = ('age_population' if key in ('young_population_share','older_population_share') else 'single_household' if key=='single_household_share' else 'apt_sale' if key in ('sale_price_per_m2','housing_turnover_pct') else 'apt_rent' if key in ('jeonse_price','monthly_rent_share','rent_count') else 'commerce' if key.startswith('business') else 'population' if key.startswith('population') else 'building' if key in ('old_building_share','building_count') else 'apartment')
    if sources.get(source,{}).get('status')=='no_data': return None
    prerequisites = {'young_population_share': 'age_20_39', 'single_household_share': 'single_households', 'apartment_supply_proxy': 'apartment_units'}
    if key in prerequisites and metrics.get(prerequisites[key]) is None:
        return None
    if key == 'older_population_share' and metrics.get('age_65_plus') is None and metrics.get('age_60_plus') is None:
        return None
    ratios={'young_population_share':('age_20_39','population_total'),'single_household_share':('single_households','households'),'apartment_supply_proxy':('apartment_units','households')}
    if key in ratios:
        numerator,denominator=(metrics.get(field) for field in ratios[key])
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (numerator,denominator)) or denominator<=0 or numerator<0:
            return None
        if key!='apartment_supply_proxy' and numerator>denominator: return None
        return numerator/denominator*100
    value = metrics.get(key) if key in metrics else derived.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def select_comparisons(region_id, regions, rows, month, question='', k=2):
    master = {r['id']: r for r in regions}
    rows={rid:row for rid,row in rows.items() if rid in master and row.get('month')==month}
    base = rows.get(region_id, {})
    topic, label, weights = topic_weights(question)
    usable = {key: weight for key, weight in weights.items() if measured(base, key) is not None}
    fallback = not usable and topic != 'general'
    if fallback:
        usable = {key: weight for key, weight in GENERAL.items() if measured(base, key) is not None}
    scales = {}
    for key in usable:
        values = [measured(row, key) for row in rows.values()]
        values = sorted(v for v in values if v is not None)
        scales[key] = max((values[-1] - values[0]) if values else 0, 1)
    ranked = []
    for rid, row in rows.items():
        if rid == region_id or rid not in master or row.get('month') != month:
            continue
        # Require every selected feature: fewer observations must not earn a better score.
        if not usable or any(measured(row, key) is None for key in usable):
            continue
        distance = sum(weight * ((measured(base, key) - measured(row, key)) / scales[key]) ** 2 for key, weight in usable.items()) / sum(usable.values())
        ranked.append((distance, rid))
    ranked.sort()
    normalized = ' '.join((question or '').lower().split())
    seed = f'{region_id}:{month}:{topic}:{normalized}'
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    peers = []
    if ranked:
        peers.append(master[ranked[0][1]])
        # Keep the closest match; vary the second among a small, reasonably similar pool.
        ceiling = max(ranked[0][0] * 16, 0.02)
        pool = [item for item in ranked[1:6] if item[0] <= ceiling]
        if not pool and len(ranked) > 1:
            pool = ranked[1:2]
        if pool and k > 1:
            chosen = rng.choices(pool, weights=[1 / (0.01 + score) for score, _ in pool], k=1)[0]
            peers.append(master[chosen[1]])
    peers = peers[:k]
    excluded = {region_id, *[r['id'] for r in peers]}
    # Random means a different valid region, not necessarily statistically similar.
    pool = sorted((r for r in regions if r['id'] not in excluded and r['id'] in rows), key=lambda r: r['id'])
    random_pick = rng.sample(pool, 1) if pool else []
    return {'neighbors': [], 'peers': peers, 'seeded_random': random_pick, 'seed': seed,
            'topic': topic, 'topic_label': label, 'month': month, 'feature_keys': list(usable),
            'topic_data_unavailable': fallback, 'method': 'question_weighted_same_month_v1'}

