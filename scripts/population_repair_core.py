"""Strict, pure validation for official API population repair."""
import re
from collections import defaultdict
from scripts.collect.adapters import aggregate_population_rows, aggregate_age_rows, aggregate_single_household_rows

ADAPTERS = {'population': aggregate_population_rows, 'age_population': aggregate_age_rows,
            'single_household': aggregate_single_household_rows}

def validate_rows(rows, requested_code, month):
    seen, result = {}, []
    for row in rows:
        code = str(row.get('stdgCd') or '').strip()
        period = re.sub(r'\D', '', str(row.get('statsYm') or ''))[:6]
        if code != requested_code or period != month.replace('-', ''):
            raise ValueError('API returned an unexpected legal code or month')
        if row.get('regSeCd') not in (None, '', '1', 1):
            raise ValueError('Unexpected population registration category')
        # lv=7 rows may be split by administrative dong/tong/ban. Do not collapse those.
        identity = tuple(str(row.get(k) or '') for k in ['statsYm','stdgCd','admmCd','tong','ban'])
        if identity in seen:
            if row != seen[identity]:
                raise ValueError('Conflicting duplicate API identity')
            continue
        seen[identity] = row
        result.append(row)
    return result

def nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0

def validate_bundle(bundle):
    pop, age, hh = bundle['population'], bundle['age_population'], bundle['single_household']
    for key in ['population_total','population_male','population_female','households']:
        if not nonnegative_int(pop.get(key)):
            raise ValueError('Incomplete population/sex/household metrics')
    if pop['population_male'] + pop['population_female'] != pop['population_total']:
        raise ValueError('Sex totals do not equal population')
    keys = [f'age_{i}_{i+9}' for i in range(0,100,10)] + ['age_100_plus']
    if any(not nonnegative_int(age.get(k)) for k in keys):
        raise ValueError('Missing age bucket')
    if sum(age[k] for k in keys) != pop['population_total']:
        raise ValueError('Age totals do not equal population')
    if not nonnegative_int(hh.get('single_households')) or hh['single_households'] > pop['households']:
        raise ValueError('Invalid one-person household count')
    if hh.get('single_male_households') is not None and hh.get('single_female_households') is not None:
        if hh['single_male_households'] + hh['single_female_households'] != hh['single_households']:
            raise ValueError('One-person household sex totals do not match')
    return True

def population_reconciliation(regions, rows, benchmark):
    """Absent official rows stay unknown; they are never silently converted to zero."""
    by_id = {r['region_id']: r for r in rows}
    expected = benchmark['regions']
    district = defaultdict(int)
    problems = []
    for code, official in expected.items():
        value = (by_id.get(code, {}).get('metrics') or {}).get('population_total')
        if (official.get('population_total') is None and value is None) or (
            official.get('population_total') is not None and value != official['population_total']
        ):
            problems.append({'code': code, 'stored': value, 'official': official['population_total']})
    for code, row in by_id.items():
        value = (row.get('metrics') or {}).get('population_total')
        if value is not None:
            if not nonnegative_int(value):
                problems.append({'code':code,'error':'invalid_population'})
            else:
                district[code[:5]] += value
    for sig, total in benchmark['totals'].items():
        actual = sum(district.values()) if sig == '48120' else district[sig]
        if actual != total['population_total']:
            problems.append({'district':sig,'stored':actual,'official':total['population_total']})
    master_ids={r['id'] for r in regions}
    for code in expected:
        if code not in master_ids:
            problems.append({'code':code,'error':'master_missing'})
    return {'status':'passed' if not problems else 'failed','problems':problems,
            'population_sum':sum(district.values()),'district_sums':dict(district),
            'unknown_no_official_rows':[r['id'] for r in regions if r['id'] not in expected]}
