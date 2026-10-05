from __future__ import annotations

import uuid
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from ..config import settings
from ..db import get_store, utcnow_iso
from ..refresh_jobs import execute_refresh_job

router=APIRouter(prefix='/api/admin',tags=['admin'])


def _auth(x_admin_token: str | None):
    if not settings.admin_refresh_token:
        raise HTTPException(503,'ADMIN_REFRESH_TOKEN이 설정되지 않아 관리자 API가 비활성화되어 있습니다.')
    if x_admin_token != settings.admin_refresh_token:
        raise HTTPException(401,'관리자 토큰이 올바르지 않습니다.')


@router.post('/refresh')
def refresh(
    background_tasks: BackgroundTasks,
    scope: str='daily',
    x_admin_token: str | None=Header(default=None),
):
    _auth(x_admin_token)
    if scope not in {'daily','monthly','all'}:
        raise HTTPException(422,'scope는 daily, monthly, all 중 하나여야 합니다.')
    job_id=uuid.uuid4().hex
    row=get_store().set('refresh_jobs',job_id,{
        'scope':scope,
        'requested_at':utcnow_iso(),
        'status':'queued',
        'note':'장시간 Historical Backfill이 아니라 최신 증분갱신용입니다. 정기 운영은 GitHub Actions를 우선합니다.',
    },merge=False)
    background_tasks.add_task(execute_refresh_job,job_id,scope)
    return {'ok':True,'job_id':job_id,'status':row,'poll_url':f'/api/admin/refresh/{job_id}'}


@router.get('/refresh/{job_id}')
def refresh_status(job_id: str, x_admin_token: str | None=Header(default=None)):
    _auth(x_admin_token)
    row=get_store().get('refresh_jobs',job_id)
    if not row:
        raise HTTPException(404,'갱신 작업을 찾을 수 없습니다.')
    return row


@router.get('/source-status')
def source_status(x_admin_token: str | None=Header(default=None)):
    _auth(x_admin_token)
    return sorted(get_store().list('source_status'),key=lambda x:(x.get('source',''),x.get('month','')),reverse=True)


@router.get('/readiness')
def readiness(x_admin_token: str | None=Header(default=None)):
    """Secret의 실제 값은 노출하지 않고 설정 준비 여부만 반환한다."""
    _auth(x_admin_token)
    from scripts.collect.catalog import source_statuses
    return {
        'firebase_configured': bool(settings.firebase_service_account_json or settings.google_application_credentials),
        'openai_configured': bool(settings.openai_api_key),
        'data_go_kr_configured': bool(settings.data_go_kr_service_key),
        'openai_model': settings.openai_model,
        'openai_max_output_tokens': settings.openai_max_output_tokens,
        'sources': source_statuses(),
    }
