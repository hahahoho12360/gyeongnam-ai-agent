from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from .db import get_store


def _iso_age_hours(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc)-dt).total_seconds()/3600,2)
    except Exception:
        return None


def _region_code(row: dict[str,Any]) -> str:
    return str(row.get('bjd_code') or row.get('id') or '').strip()


def quality_report(*, scope_prefix: str | None=None, latest_month: str | None=None) -> dict[str, Any]:
    """실제 Firestore 적재 상태를 범위별로 점검한다.

    scope_prefix='4812'이면 창원시 Master/월별 데이터만 대상으로 커버리지와 결측을 계산한다.
    """
    store=get_store()
    all_regions=[r for r in store.list('regions') if r and not r.get('is_demo')]
    regions=[r for r in all_regions if not scope_prefix or _region_code(r).startswith(scope_prefix)]
    region_ids={str(r.get('id')) for r in regions if r.get('id')}

    all_rows=store.list('monthly_data')
    rows=[r for r in all_rows if str(r.get('region_id')) in region_ids and not (r.get('freshness') or {}).get('is_demo')]
    statuses=store.list('source_status')

    month_counts=Counter(str(r.get('month')) for r in rows if r.get('month'))
    region_counts=Counter(str(r.get('region_id')) for r in rows if r.get('region_id'))
    months=sorted(month_counts)

    confidence=Counter()
    provisional=0
    freshness_ages=[]
    fields=defaultdict(int)
    source_processed=Counter()
    source_no_data=Counter()
    invalid_numeric=[]
    for row in rows:
        fr=row.get('freshness') or {}
        c=fr.get('data_confidence') or row.get('data_confidence') or 'unknown'
        confidence[str(c)] += 1
        if fr.get('is_provisional') is True:
            provisional += 1
        age=_iso_age_hours(fr.get('fetched_at'))
        if age is not None:
            freshness_ages.append(age)
        for src,meta in (fr.get('sources') or {}).items():
            source_processed[str(src)] += 1
            if isinstance(meta,dict) and meta.get('status')=='no_data':
                source_no_data[str(src)] += 1
        for key,val in (row.get('metrics') or {}).items():
            if val is not None:
                fields[f'metrics.{key}'] += 1
            if isinstance(val,(int,float)) and key.endswith(('_count','households','population_total')) and val < 0:
                invalid_numeric.append({'id':row.get('id'),'field':key,'value':val})
        for key,val in (row.get('derived') or {}).items():
            if val is not None:
                fields[f'derived.{key}'] += 1
            if isinstance(val,(int,float)) and key.endswith('_share') and not (0 <= val <= 100):
                invalid_numeric.append({'id':row.get('id'),'field':key,'value':val})
        for key,val in (row.get('indexes') or {}).items():
            if val is not None:
                fields[f'indexes.{key}'] += 1
            if isinstance(val,(int,float)) and key.endswith('_index') and not (0 <= val <= 100):
                invalid_numeric.append({'id':row.get('id'),'field':key,'value':val})

    latest_status={}
    for st in sorted(statuses,key=lambda x:str(x.get('finished_at') or x.get('started_at') or ''),reverse=True):
        src=st.get('source')
        if src and src not in latest_status:
            latest_status[src]={
                'status':st.get('status'),
                'month':st.get('month'),
                'finished_at':st.get('finished_at'),
                'regions_updated':st.get('regions_updated'),
            }

    populated_regions=sum(1 for rid in region_ids if region_counts.get(rid,0)>0)
    coverage_pct=round(populated_regions*100/len(region_ids),2) if region_ids else 0.0
    resolved_latest=latest_month or (months[-1] if months else None)
    latest_rows=[r for r in rows if r.get('month')==resolved_latest] if resolved_latest else []
    latest_region_ids={str(r.get('region_id')) for r in latest_rows}
    latest_month_regions=len(latest_region_ids)
    latest_month_coverage=round(latest_month_regions*100/len(region_ids),2) if region_ids else 0.0

    expected_sources=('population','age_population','single_household','apt_sale','apt_rent','apartment_basic','building_register','commerce')
    latest_source_coverage={}
    for src in expected_sources:
        processed=no_data=0
        for row in latest_rows:
            meta=((row.get('freshness') or {}).get('sources') or {}).get(src)
            if meta is not None:
                processed += 1
                if isinstance(meta,dict) and meta.get('status')=='no_data':
                    no_data += 1
        latest_source_coverage[src]={
            'processed_regions':processed,
            'no_data_regions':no_data,
            'processed_pct':round(processed*100/len(region_ids),2) if region_ids else 0.0,
        }

    index_coverage={}
    for name in ('vitality_index','housing_pressure_index','living_convenience_index','commerce_change_index'):
        n=sum(1 for r in latest_rows if isinstance((r.get('indexes') or {}).get(name),(int,float)))
        index_coverage[name]={
            'regions':n,
            'coverage_pct':round(n*100/len(region_ids),2) if region_ids else 0.0,
        }

    return {
        'scope_prefix':scope_prefix,
        'minimum_100_points_met': len(rows) >= 100,
        'monthly_data_points': len(rows),
        'regions_master_count': len(regions),
        'regions_with_data': populated_regions,
        'region_coverage_pct': coverage_pct,
        'period': {'start': months[0] if months else None, 'end': months[-1] if months else None, 'month_count': len(months)},
        'latest_month':resolved_latest,
        'latest_month_region_count': latest_month_regions,
        'latest_month_coverage_pct': latest_month_coverage,
        'latest_source_coverage':latest_source_coverage,
        'index_coverage':index_coverage,
        'confidence_counts': dict(confidence),
        'provisional_points': provisional,
        'freshness_age_hours': {
            'min': min(freshness_ages) if freshness_ages else None,
            'max': max(freshness_ages) if freshness_ages else None,
            'average': round(sum(freshness_ages)/len(freshness_ages),2) if freshness_ages else None,
        },
        'source_processed_counts_all_months':dict(source_processed),
        'source_no_data_counts_all_months':dict(source_no_data),
        'invalid_numeric_count':len(invalid_numeric),
        'invalid_numeric_examples':invalid_numeric[:20],
        'top_non_null_fields': dict(sorted(fields.items(), key=lambda kv:(-kv[1],kv[0]))[:60]),
        'latest_source_status': latest_status,
        'notes': [
            'minimum_100_points_met은 과제의 최소 데이터 포인트 요건을 점검한다.',
            'scope_prefix를 지정하면 해당 법정지역코드 접두어 범위만 분모/분자로 사용한다.',
            'no_data는 0이 아니라 공공데이터 응답상 자료없음으로 처리된 상태다.',
            '상권변화지수는 장기 상권 Snapshot이 축적되기 전까지 현시점 상권활력 Proxy이다.',
        ],
    }
