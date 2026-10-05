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


def quality_report() -> dict[str, Any]:
    """최종 제출 전에 실제 데이터 적재 상태를 한눈에 점검한다.

    비밀값은 읽거나 반환하지 않는다. Firestore에서는 집계문서만 읽으며,
    제출 단계에서 '최소 100개 포인트', 지역/월 커버리지, freshness/confidence를
    빠르게 검증하기 위한 운영용 리포트다.
    """
    store=get_store()
    regions=store.list('regions')
    rows=store.list('monthly_data')
    statuses=store.list('source_status')

    region_ids={str(r.get('id')) for r in regions if r.get('id')}
    month_counts=Counter(str(r.get('month')) for r in rows if r.get('month'))
    region_counts=Counter(str(r.get('region_id')) for r in rows if r.get('region_id'))
    months=sorted(month_counts)

    confidence=Counter()
    provisional=0
    freshness_ages=[]
    fields=defaultdict(int)
    for row in rows:
        fr=row.get('freshness') or {}
        c=fr.get('data_confidence') or row.get('data_confidence') or 'unknown'
        confidence[str(c)] += 1
        if fr.get('is_provisional') is True:
            provisional += 1
        age=_iso_age_hours(fr.get('fetched_at'))
        if age is not None:
            freshness_ages.append(age)
        for key,val in (row.get('metrics') or {}).items():
            if val is not None:
                fields[f'metrics.{key}'] += 1
        for key,val in (row.get('derived') or {}).items():
            if val is not None:
                fields[f'derived.{key}'] += 1
        for key,val in (row.get('indexes') or {}).items():
            if val is not None:
                fields[f'indexes.{key}'] += 1

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
    latest_month=months[-1] if months else None
    latest_month_regions=month_counts.get(latest_month,0) if latest_month else 0
    latest_month_coverage=round(latest_month_regions*100/len(region_ids),2) if region_ids else 0.0

    return {
        'minimum_100_points_met': len(rows) >= 100,
        'monthly_data_points': len(rows),
        'regions_master_count': len(regions),
        'regions_with_data': populated_regions,
        'region_coverage_pct': coverage_pct,
        'period': {'start': months[0] if months else None, 'end': latest_month, 'month_count': len(months)},
        'latest_month_region_count': latest_month_regions,
        'latest_month_coverage_pct': latest_month_coverage,
        'confidence_counts': dict(confidence),
        'provisional_points': provisional,
        'freshness_age_hours': {
            'min': min(freshness_ages) if freshness_ages else None,
            'max': max(freshness_ages) if freshness_ages else None,
            'average': round(sum(freshness_ages)/len(freshness_ages),2) if freshness_ages else None,
        },
        'top_non_null_fields': dict(sorted(fields.items(), key=lambda kv:(-kv[1],kv[0]))[:40]),
        'latest_source_status': latest_status,
        'notes': [
            'minimum_100_points_met은 첨부 과제의 최소 데이터 포인트 요건을 점검한다.',
            'coverage는 regions Master 대비 monthly_data 보유 지역 비율이다.',
            '실데이터 최종 증빙에서는 데모 Memory DB가 아니라 Firestore 모드에서 확인해야 한다.',
        ],
    }
