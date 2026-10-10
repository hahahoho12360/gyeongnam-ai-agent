from __future__ import annotations

from typing import Any
from .metrics import percentile_score, weighted_index

# Checkpoint 3.2 — 창원 1차 MVP용 Composite Index.
# 공식 통계가 아닌 프로젝트 정의 지수이며, 같은 월/같은 비교범위 내 percentile(0~100)을 조합한다.
# 결측 구성요소는 가중치에서 제외하고 재정규화하되, 최소 구성요소 수 미만이면 지수를 만들지 않는다.
INDEX_DEFINITIONS = {
    'vitality_index': {
        'population_yoy_pct': 0.35,
        'young_population_share': 0.30,
        'housing_turnover_pct': 0.20,
        'businesses_per_1000_people': 0.15,
    },
    'housing_pressure_index': {
        'sale_price_yoy_pct': 0.35,
        'rent_count_yoy_pct': 0.20,
        'monthly_rent_share': 0.20,
        'old_building_share': 0.15,
        'housing_turnover_pct': 0.10,
    },
    'living_convenience_index': {
        'businesses_per_1000_people': 0.30,
        'business_diversity_index': 0.25,
        'health_businesses_per_1000_people': 0.20,
        'education_businesses_per_1000_people': 0.15,
        'apartment_supply_proxy': 0.10,
    },
    # 상권의 과거 Snapshot이 아직 충분하지 않으므로 1차 MVP에서는 '변화'를 직접 측정하지 않는다.
    # 현시점 상권활력 Proxy로 계산하고 index_meta/index_report에 한계를 명시한다.
    'commerce_change_index': {
        'businesses_per_1000_people': 0.30,
        'business_diversity_index': 0.25,
        'restaurant_businesses_per_1000_people': 0.20,
        'cafe_businesses_per_1000_people': 0.15,
        'convenience_businesses_per_1000_people': 0.10,
    },
}

INDEX_METHODS = {
    'vitality_index': {
        'label_ko': '지역활력지수',
        'method': 'percentile_weighted',
        'minimum_components': 2,
    },
    'housing_pressure_index': {
        'label_ko': '주거시장압력지수',
        'method': 'percentile_weighted',
        'minimum_components': 2,
    },
    'living_convenience_index': {
        'label_ko': '생활편의지수',
        'method': 'percentile_weighted',
        'minimum_components': 2,
    },
    'commerce_change_index': {
        'label_ko': '상권변화지수',
        'method': 'snapshot_activity_proxy',
        'minimum_components': 2,
        'limitation': '상권 Snapshot의 장기 시계열이 아직 부족하여 현시점 상권활력 Proxy로 계산한다.',
    },
}


def _value(row: dict[str, Any], key: str):
    if key in row.get('derived', {}):
        return row['derived'].get(key)
    return row.get('metrics', {}).get(key)


def component_population_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    keys={k for d in INDEX_DEFINITIONS.values() for k in d}
    return {key: sum(1 for row in rows if isinstance(_value(row,key),(int,float))) for key in sorted(keys)}


def compute_index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    """같은 월·같은 비교범위의 지역들을 percentile로 표준화하여 4개 지수를 계산한다."""
    populations: dict[str, list[float]] = {}
    for definition in INDEX_DEFINITIONS.values():
        for key in definition:
            populations.setdefault(key, [])
    for row in rows:
        for key in populations:
            v = _value(row, key)
            if isinstance(v, (int, float)):
                populations[key].append(float(v))

    result: dict[str, dict[str, float | None]] = {}
    for row in rows:
        rid = str(row.get('region_id'))
        indexes: dict[str, float | None] = {}
        for index_name, weights in INDEX_DEFINITIONS.items():
            scores: dict[str, float | None] = {}
            for key in weights:
                v = _value(row, key)
                scores[key] = percentile_score(float(v), populations[key]) if isinstance(v, (int, float)) else None
            minimum=int(INDEX_METHODS[index_name].get('minimum_components',1))
            indexes[index_name] = weighted_index(scores, weights, minimum_components=minimum)
        result[rid] = indexes
    return result


def methodology_payload(*, comparison_scope: str, month: str, region_count: int) -> dict[str, Any]:
    return {
        'method_version': '3.2',
        'comparison_scope': comparison_scope,
        'comparison_month': month,
        'comparison_region_count': region_count,
        'score_range': [0,100],
        'standardization': 'same-month percentile within comparison scope',
        'official_statistic': False,
        'missing_value_policy': 'missing component weight excluded and remaining weights renormalized; minimum component rule applies',
        'indexes': {
            name: {
                **INDEX_METHODS[name],
                'weights': weights,
            }
            for name,weights in INDEX_DEFINITIONS.items()
        },
    }
