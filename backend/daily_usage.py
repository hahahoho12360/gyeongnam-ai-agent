"""Global, durable KST daily quota for outbound AI requests (not chat messages)."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from .config import settings
from .db import get_store, MemoryStore, FirestoreStore

KST = ZoneInfo('Asia/Seoul')
COLLECTION = 'ai_daily_usage'


def window(now=None):
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError('Quota time must be timezone-aware')
    local = now.astimezone(KST)
    reset = datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=KST)
    return local.date().isoformat(), reset.isoformat(), max(1, int((reset-local).total_seconds()))


def count(row):
    value = (row or {}).get('used', 0)
    if type(value) is not int or value < 0:
        raise ValueError('Invalid quota counter')
    return value


def payload(used, day, reset):
    limit = settings.ai_daily_call_limit
    return {'date': day, 'timezone': 'Asia/Seoul', 'limit': limit,
            'used': used, 'remaining': max(0, limit-used), 'reset_at': reset,
            'unit': 'AI API 호출', 'scope': 'service', 'exhausted': used >= limit}


def unavailable():
    return HTTPException(503, 'AI 사용량을 확인하지 못해 호출을 잠시 중단했어요. 잠시 후 다시 시도해 주세요.')


def usage_status(now=None):
    day, reset, _ = window(now)
    try:
        return payload(count(get_store().get(COLLECTION, day)), day, reset)
    except Exception:
        raise unavailable() from None


def reserve_call(now=None):
    """Reserve before every provider attempt; failures are not refunded.

    Keeping reservations on errors/crashes is conservative: an API timeout may
    already have incurred a charge. Only this transaction writes the counter.
    """
    day, reset, retry = window(now)
    limit = settings.ai_daily_call_limit

    def next_row(row):
        used = count(row)
        if used >= limit:
            raise HTTPException(429,
                f'오늘의 서비스 전체 AI 호출 한도 {limit}회를 모두 사용했어요. 한국 시간 다음 날 00:00에 다시 이용할 수 있어요. 통계·그래프·지도 조회는 계속 사용할 수 있어요.',
                headers={'Retry-After': str(retry)})
        return {'used': used+1, 'date': day, 'timezone': 'Asia/Seoul',
                'limit_at_last_call': limit, 'updated_at': datetime.now(KST).isoformat()}

    try:
        store = get_store()
        if isinstance(store, MemoryStore):
            # Test/development only. Production always uses the Firestore transaction.
            with store._lock:
                bucket = store._data.setdefault(COLLECTION, {})
                row = next_row(bucket.get(day))
                bucket[day] = {'id': day, **row}
        elif isinstance(store, FirestoreStore):
            from google.cloud import firestore
            ref = store.client.collection(COLLECTION).document(day)

            @firestore.transactional
            def reserve(transaction):
                snapshot = ref.get(transaction=transaction)
                row = next_row(snapshot.to_dict() if snapshot.exists else None)
                transaction.set(ref, row)
                return row

            row = reserve(store.client.transaction())
        else:
            raise RuntimeError('Quota store does not support atomic reservations')
        return payload(row['used'], day, reset)
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
