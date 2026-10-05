from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import settings
from . import analysis


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z','+00:00'))
    except Exception:
        return None


def is_stale(row: dict[str, Any] | None, ttl_hours: int) -> bool:
    if not row:
        return True
    fetched = _parse_iso((row.get('freshness') or {}).get('fetched_at'))
    if not fetched:
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched).total_seconds() > ttl_hours * 3600


def live_snapshot(region: str) -> dict[str, Any]:
    reg=analysis.resolve_region(region)
    if not reg:
        return {'error':'region_not_found','region':region}
    before=analysis.latest(reg['id'])
    refreshed=False; refresh_result=[]
    if settings.enable_on_demand_refresh and is_stale(before, settings.live_real_estate_ttl_hours):
        try:
            # 느린 네트워크 작업은 import 시점이 아니라 실제 Tool 호출 때만 수행한다.
            from scripts.pipeline import current_month, collect_apt_sale_for_sigungu, collect_apt_rent_for_sigungu, apply_patches
            month=current_month(); code=str(reg.get('bjd_code') or reg['id']); sgg=code[:5]
            # 실거래 API의 최소 공간조회 단위가 시군구이므로 대상 시군구만 새로 받아 그 안의 지역을 upsert한다.
            for source,collector,key in (
                ('apt_sale',collect_apt_sale_for_sigungu,'sale_count'),
                ('apt_rent',collect_apt_rent_for_sigungu,'rent_count'),
            ):
                patches=collector(month,sgg)
                count=apply_patches(month,source,patches,provisional=True,sample_key=key)
                refresh_result.append({'source':source,'regions_updated':count})
            refreshed=True
        except Exception as exc:
            refresh_result.append({'status':'error','error':f'{type(exc).__name__}: {exc}'})
    after=analysis.latest(reg['id']) or before
    return {
        'region':reg,
        'latest':after,
        'refreshed':refreshed,
        'refresh_result':refresh_result,
        'policy':{
            'cache_first':True,
            'on_demand_enabled':settings.enable_on_demand_refresh,
            'ttl_hours':settings.live_real_estate_ttl_hours,
            'note':'Scheduled Refresh가 기본이며, TTL 초과 시 선택적으로 최신 실거래를 재조회합니다.'
        }
    }


def _source_is_stale(row: dict[str, Any] | None, source: str, ttl_hours: int) -> bool:
    if not row:
        return True
    source_meta=((row.get('freshness') or {}).get('sources') or {}).get(source) or {}
    fetched=_parse_iso(source_meta.get('fetched_at'))
    if not fetched:
        return True
    if fetched.tzinfo is None:
        fetched=fetched.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc)-fetched).total_seconds() > ttl_hours*3600


def live_auction_snapshot(region: str) -> dict[str, Any]:
    """온비드가 설정되어 있으면 TTL 초과 시 현월 공매 집계를 갱신한다.

    공매 API가 미설정이거나 갱신 실패해도 기존 Firestore 스냅샷을 반환하는 cache-first 정책이다.
    """
    reg=analysis.resolve_region(region)
    if not reg:
        return analysis.region_resolution_error(region)
    before=analysis.latest(reg['id'])
    refreshed=False; refresh_result=[]
    configured=False
    try:
        import os
        configured=bool(os.getenv('ONBID_PROPERTY_API_URL') or os.getenv('ONBID_RESULT_API_URL'))
    except Exception:
        configured=False
    if settings.enable_on_demand_refresh and configured and _source_is_stale(before,'onbid',settings.live_onbid_ttl_hours):
        try:
            from scripts.pipeline import current_month, collect_onbid, apply_patches
            month=current_month()
            patches=collect_onbid(month)
            count=apply_patches(month,'onbid',patches,provisional=True,sample_key='auction_result_count')
            refresh_result.append({'source':'onbid','regions_updated':count})
            refreshed=True
        except Exception as exc:
            refresh_result.append({'status':'error','error':f'{type(exc).__name__}: {exc}'})
    after=analysis.latest(reg['id']) or before
    return {
        'region':reg,
        'latest':after,
        'refreshed':refreshed,
        'refresh_result':refresh_result,
        'policy':{
            'cache_first':True,
            'on_demand_enabled':settings.enable_on_demand_refresh,
            'source_configured':configured,
            'ttl_hours':settings.live_onbid_ttl_hours,
            'note':'온비드 API가 설정된 경우 TTL 초과 시 현월 집계를 갱신하며, 실패하면 저장 스냅샷을 사용합니다.',
        }
    }
