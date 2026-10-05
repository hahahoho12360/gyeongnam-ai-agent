from __future__ import annotations

from fastapi import APIRouter

from ..config import settings
from ..db import get_store
from scripts.collect.catalog import source_statuses
from ..data_quality import quality_report

router = APIRouter(prefix='/api/meta', tags=['meta'])


@router.get('/readiness')
def readiness():
    """비밀값 자체는 노출하지 않고 서비스의 연결 준비상태만 반환한다."""
    sources=[]
    for item in source_statuses():
        sources.append({
            'key': item['key'],
            'label': item['label'],
            'configured': item['configured'],
            'cadence': item['cadence'],
            'project_mode': item['project_mode'],
        })
    return {
        'db_mode': 'memory' if settings.use_memory_db else 'firestore',
        'openai_configured': bool(settings.openai_api_key),
        'firebase_project_configured': bool(settings.firebase_project_id),
        'public_data_key_configured': bool(settings.data_go_kr_service_key),
        'on_demand_refresh_enabled': settings.enable_on_demand_refresh,
        'sources': sources,
    }


@router.get('/source-status')
def source_status():
    """실제 갱신 작업이 기록한 source_status를 최신순으로 반환한다."""
    rows=get_store().list('source_status')
    rows.sort(key=lambda r: str(r.get('finished_at') or r.get('started_at') or ''), reverse=True)
    return rows[:200]


@router.get('/data-quality')
def data_quality():
    """실데이터 커버리지·100포인트·freshness·신뢰도 제출 점검."""
    return quality_report()
