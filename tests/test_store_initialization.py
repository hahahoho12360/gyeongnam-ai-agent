import time
from concurrent.futures import ThreadPoolExecutor
from backend import db

def test_first_concurrent_requests_initialize_store_only_once(monkeypatch):
 calls=[]
 def factory():
  calls.append(1);time.sleep(0.01);return object()
 monkeypatch.setattr(db,'_store',None)
 monkeypatch.setattr(db,'MemoryStore',factory)
 monkeypatch.setattr(db.settings,'use_memory_db',True)
 with ThreadPoolExecutor(max_workers=8) as executor:stores=list(executor.map(lambda _:db.get_store(),range(8)))
 assert len(calls)==1
 assert all(store is stores[0] for store in stores)
