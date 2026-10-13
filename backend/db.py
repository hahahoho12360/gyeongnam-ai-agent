from __future__ import annotations
import json, os, threading, uuid
from datetime import datetime, timezone
from typing import Any
from .config import settings

class Store:
    def create(self, collection: str, data: dict[str, Any], doc_id: str | None=None) -> dict: raise NotImplementedError
    def set(self, collection: str, doc_id: str, data: dict[str, Any], merge: bool=True) -> dict: raise NotImplementedError
    def get(self, collection: str, doc_id: str) -> dict | None: raise NotImplementedError
    def list(self, collection: str) -> list[dict]: raise NotImplementedError
    def update(self, collection: str, doc_id: str, changes: dict[str, Any]) -> dict | None: raise NotImplementedError
    def delete(self, collection: str, doc_id: str) -> bool: raise NotImplementedError
    def filter_eq(self, collection: str, field: str, value: Any) -> list[dict]: raise NotImplementedError

class MemoryStore(Store):
    def __init__(self):
        self._data: dict[str, dict[str,dict]] = {}
        self._lock = threading.Lock()
    def create(self, collection, data, doc_id=None):
        with self._lock:
            doc_id = doc_id or uuid.uuid4().hex
            row = {'id': doc_id, **data}
            self._data.setdefault(collection,{})[doc_id] = row
            return row.copy()
    def set(self, collection, doc_id, data, merge=True):
        with self._lock:
            bucket=self._data.setdefault(collection,{})
            row = ({**bucket.get(doc_id,{}), **data} if merge else dict(data))
            row['id']=doc_id
            bucket[doc_id]=row
            return row.copy()
    def get(self, collection, doc_id):
        row=self._data.get(collection,{}).get(doc_id)
        return row.copy() if row else None
    def list(self, collection):
        return [v.copy() for v in self._data.get(collection,{}).values()]
    def update(self, collection, doc_id, changes):
        with self._lock:
            if doc_id not in self._data.get(collection,{}): return None
            self._data[collection][doc_id].update(changes)
            return self._data[collection][doc_id].copy()
    def delete(self, collection, doc_id):
        with self._lock:
            return self._data.get(collection,{}).pop(doc_id,None) is not None
    def filter_eq(self, collection, field, value):
        return [v.copy() for v in self._data.get(collection,{}).values() if v.get(field)==value]

class FirestoreStore(Store):
    def __init__(self):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError as e:
            raise RuntimeError('firebase-admin이 설치되어 있지 않습니다. pip install firebase-admin') from e
        if not firebase_admin._apps:
            raw=settings.firebase_service_account_json.strip()
            if raw:
                if raw.startswith('{'):
                    cred=credentials.Certificate(json.loads(raw))
                else:
                    cred=credentials.Certificate(raw)
                firebase_admin.initialize_app(cred, {'projectId': settings.firebase_project_id} if settings.firebase_project_id else None)
            else:
                # GOOGLE_APPLICATION_CREDENTIALS 또는 Render의 ADC 사용
                firebase_admin.initialize_app(options={'projectId': settings.firebase_project_id} if settings.firebase_project_id else None)
        self.client=firestore.client()
    def _snap(self, snap):
        if not snap.exists: return None
        return {'id': snap.id, **snap.to_dict()}
    def create(self, collection, data, doc_id=None):
        if doc_id:
            ref=self.client.collection(collection).document(doc_id); ref.set(data); return {'id':doc_id,**data}
        _,ref=self.client.collection(collection).add(data); return {'id':ref.id,**data}
    def set(self, collection, doc_id, data, merge=True):
        ref=self.client.collection(collection).document(doc_id); ref.set(data, merge=merge); return {'id':doc_id,**data}
    def get(self, collection, doc_id): return self._snap(self.client.collection(collection).document(doc_id).get())
    def list(self, collection): return [self._snap(x) for x in self.client.collection(collection).stream()]
    def update(self, collection, doc_id, changes):
        ref=self.client.collection(collection).document(doc_id)
        if not ref.get().exists: return None
        ref.update(changes); return self._snap(ref.get())
    def delete(self, collection, doc_id):
        ref=self.client.collection(collection).document(doc_id)
        if not ref.get().exists: return False
        ref.delete(); return True
    def filter_eq(self, collection, field, value):
        # 최신 Firestore SDK 권장 문법. positional where 경고를 피한다.
        from google.cloud.firestore_v1.base_query import FieldFilter
        query=self.client.collection(collection).where(filter=FieldFilter(field, '==', value))
        return [self._snap(x) for x in query.stream()]

_store: Store | None = None

_store_lock=threading.RLock()

def get_store() -> Store:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = MemoryStore() if settings.use_memory_db else FirestoreStore()
    return _store

def utcnow_iso(): return datetime.now(timezone.utc).isoformat()

