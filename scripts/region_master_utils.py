"""지역목록을 보완해도 기존 인접성과 추가 메타데이터를 보존한다."""
def upsert_region_master(store, region):
    updates=dict(region)
    if store.get('regions',region['id']):updates.pop('neighbors',None)
    return store.set('regions',region['id'],updates,merge=True)
