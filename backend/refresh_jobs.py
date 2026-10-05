from __future__ import annotations

import traceback
from .db import get_store, utcnow_iso


def execute_refresh_job(job_id: str, scope: str) -> None:
    """Best-effort 수동 갱신 작업.

    정기 운영의 1순위는 GitHub Actions이고, 이 함수는 Swagger/관리자 수동 실행 및
    증빙용이다. Render 프로세스 재시작 시 중간 작업은 끊길 수 있으므로 장시간 backfill에는
    사용하지 않는다.
    """
    store=get_store()
    store.set('refresh_jobs',job_id,{
        'scope':scope,'status':'running','started_at':utcnow_iso(),'finished_at':None,
    },merge=True)
    try:
        from scripts.update_data import main as update_main
        code=update_main(scope)
        status='ok' if code==0 else 'error'
        store.set('refresh_jobs',job_id,{
            'status':status,'exit_code':code,'finished_at':utcnow_iso(),
        },merge=True)
    except Exception as exc:
        store.set('refresh_jobs',job_id,{
            'status':'error','error':f'{type(exc).__name__}: {exc}',
            'traceback':traceback.format_exc()[-4000:], 'finished_at':utcnow_iso(),
        },merge=True)
