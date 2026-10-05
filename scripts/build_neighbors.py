"""공식 법정구역 경계 GeoJSON로 실제 인접 법정읍·면·동을 계산한다.

권장 원천: 국토교통부 법정구역정보(WMS/WFS) 또는 공식 경계 파일.
이 스크립트는 인터넷 호출을 강제하지 않고 내려받은 GeoJSON을 받아 처리한다.
도시 법정동은 그대로, 법정리는 regions Master의 부모 읍·면(code[:8]+'00')으로 roll-up한다.

예:
  pip install -r requirements-spatial.txt
  python scripts/build_neighbors.py gyeongnam_legal.geojson --code-field EMD_CD

실제 WFS 필드명은 내려받은 파일의 properties를 확인해 --code-field로 지정한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from backend.db import get_store


def _load_shapely():
    try:
        from shapely.geometry import shape, mapping
        from shapely.ops import unary_union
        return shape, unary_union
    except ImportError as exc:
        raise SystemExit('shapely가 필요합니다: pip install -r requirements-spatial.txt') from exc


def _normalize_code(value: Any) -> str:
    if value is None:
        return ''
    text=''.join(ch for ch in str(value).strip() if ch.isdigit())
    return text[:10]


def _region_for_feature(code: str, regions_by_code: dict[str,dict]) -> str | None:
    if code in regions_by_code:
        return regions_by_code[code]['id']
    # WFS 읍면동 경계는 흔히 8자리 EMD_CD를 사용하므로 Master 10자리로 맞춘다.
    if len(code)==8 and code+'00' in regions_by_code:
        return regions_by_code[code+'00']['id']
    # 리 코드 → 부모 읍·면. 법정동 10자리에서 마지막 2자리를 00으로 roll-up.
    if len(code)>=10:
        parent=code[:8]+'00'
        if parent in regions_by_code:
            return regions_by_code[parent]['id']
    return None


def build_neighbors(path: Path, code_field: str, *, buffer_distance: float=0.0) -> dict[str,Any]:
    shape, unary_union=_load_shapely()
    store=get_store()
    regions=[r for r in store.list('regions') if not r.get('is_demo')]
    by_code={str(r.get('bjd_code') or r.get('id')):r for r in regions}
    if not regions:
        raise SystemExit('regions 컬렉션이 비어 있습니다. 먼저 scripts/bootstrap_regions.py를 실행하세요.')

    payload=json.loads(path.read_text(encoding='utf-8'))
    features=payload.get('features') or []
    grouped: dict[str,list]= {}
    unmatched=0
    for feature in features:
        props=feature.get('properties') or {}
        raw_code=props.get(code_field)
        if raw_code is None:
            for fallback in ('EMD_CD','emd_cd','법정동코드','BJD_CD','bjd_cd','STD_SGGCD'):
                if props.get(fallback) is not None:
                    raw_code=props.get(fallback); break
        code=_normalize_code(raw_code)
        rid=_region_for_feature(code,by_code)
        geom_raw=feature.get('geometry')
        if not rid or not geom_raw:
            unmatched+=1
            continue
        geom=shape(geom_raw)
        if not geom.is_empty:
            grouped.setdefault(rid,[]).append(geom)

    geoms={rid:unary_union(items) for rid,items in grouped.items() if items}
    ids=sorted(geoms)
    neighbor_map={rid:set() for rid in ids}
    for i,rid in enumerate(ids):
        a=geoms[rid]
        a_test=a.buffer(buffer_distance) if buffer_distance else a
        for other in ids[i+1:]:
            b=geoms[other]
            b_test=b.buffer(buffer_distance) if buffer_distance else b
            # exact topology 우선. buffer는 데이터 정밀도 오차 보정용 선택값이다.
            if a_test.touches(b_test) or a_test.intersects(b_test):
                neighbor_map[rid].add(other)
                neighbor_map[other].add(rid)

    updated=0
    for rid, geom in geoms.items():
        centroid=geom.centroid
        store.update('regions',rid,{
            'neighbors':sorted(neighbor_map.get(rid,set())),
            'centroid':{'lon':round(float(centroid.x),7),'lat':round(float(centroid.y),7)},
            'neighbor_source':path.name,
        })
        updated+=1

    return {
        'features':len(features),
        'regions_in_master':len(regions),
        'regions_with_geometry':len(geoms),
        'regions_updated':updated,
        'unmatched_features':unmatched,
        'neighbor_edges':sum(len(v) for v in neighbor_map.values())//2,
        'warning':'GeoJSON 좌표계가 EPSG:4326이 아니면 centroid의 lon/lat 표시는 의미가 다를 수 있습니다. 인접성 자체는 동일 좌표계 내부에서 계산됩니다.',
    }


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('geojson',type=Path)
    p.add_argument('--code-field',default='EMD_CD',help='GeoJSON properties 안의 10자리 법정구역 코드 필드명')
    p.add_argument('--buffer',type=float,default=0.0,help='경계 정밀도 오차 보정용 좌표단위 buffer. 기본 0 권장')
    args=p.parse_args()
    if not args.geojson.exists():
        raise SystemExit(f'파일을 찾을 수 없습니다: {args.geojson}')
    result=build_neighbors(args.geojson,args.code_field,buffer_distance=args.buffer)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
