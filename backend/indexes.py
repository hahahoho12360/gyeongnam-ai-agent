from __future__ import annotations

from typing import Any
from .metrics import percentile_score, weighted_index

# 프로젝트 정의 Composite Index v1.0.
# 공식 통계가 아니며, 결측치는 해당 구성요소의 가중치를 제외하고 재정규화한다.
INDEX_DEFINITIONS = {
    'vitality_index': {
        'population_yoy_pct': 0.30,
        'young_population_share': 0.25,
        'business_net_change': 0.20,
        'housing_turnover_pct': 0.15,
        'small_household_share': 0.10,
    },
    'housing_pressure_index': {
        'sale_price_yoy_pct': 0.30,
        'monthly_rent_share': 0.20,
        'auction_listings_per_1000_households': 0.20,
        'old_building_share': 0.15,
        'rent_count_yoy_pct': 0.15,
    },
    'living_convenience_index': {
        'businesses_per_1000_people': 0.35,
        'business_diversity_index': 0.30,
        'health_businesses_per_1000_people': 0.20,
        'education_businesses_per_1000_people': 0.15,
    },
    'commerce_change_index': {
        'business_net_change': 0.40,
        'business_yoy_pct': 0.35,
        'business_diversity_index': 0.15,
        'commercial_transaction_yoy_pct': 0.10,
    },
}


def _value(row: dict[str, Any], key: str):
    if key in row.get('derived', {}):
        return row['derived'].get(key)
    return row.get('metrics', {}).get(key)


def compute_index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    """같은 월의 여러 지역을 경남 전체 percentile로 표준화한다."""
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
            indexes[index_name] = weighted_index(scores, weights)
        result[rid] = indexes
    return result
