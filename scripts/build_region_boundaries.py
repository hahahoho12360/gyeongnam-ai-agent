"""Build the versioned reference map; never substitute administrative-dong codes.

Run manually: pip install pyproj; python scripts/build_region_boundaries.py
Input is pinned and checksummed. Replace source/date/hash together after reviewing
a newer official legal-dong boundary release. This is not a runtime dependency.
"""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from pyproj import Geod

SOURCE = 'https://raw.githubusercontent.com/KnellBalm/kr-admin-geojson/3a859f2a45be8acf8237d9eefd9565f99cc603da/emd.geojson'
SHA256 = 'ca8d03b0df83e5d90f78b83090ef0ef03143c1be339cce9c448260005ac1e004'
DISTRICTS = {'48121', '48123', '48125', '48127', '48129'}


def build(source):
    geod = Geod(ellps='WGS84')
    features = []
    codes = set()
    for feature in source['features']:
        p, g = feature['properties'], feature['geometry']
        code = str(p['EMD_CD'])
        if code[:5] not in DISTRICTS:
            continue
        assert len(code) == 8 and code.isdigit() and code not in codes
        assert g['type'] in ('Polygon', 'MultiPolygon')
        codes.add(code)
        polygons = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
        area = 0
        for polygon in polygons:
            for i, ring in enumerate(polygon):
                assert len(ring) >= 4 and ring[0] == ring[-1]
                assert all(127 < lon < 130 and 34 < lat < 36 for lon, lat in ring)
                ring_area, _ = geod.polygon_area_perimeter(*zip(*ring))
                area += abs(ring_area) * (1 if i == 0 else -1)
        assert area > 0
        features.append({'type': 'Feature', 'properties': {
            'code': code + '00', 'name': p['FULL_NM'],
            'area_km2': round(area / 1_000_000, 4),
        }, 'geometry': g})
    assert len(features) == 204
    return {'type': 'FeatureCollection', 'metadata': {
        'boundary_date': '2023-07-29',
        'kind': 'legal_eup_myeon_dong_reference',
        'source': '국가공간정보포털·브이월드; KnellBalm/kr-admin-geojson 좌표 변환·단순화',
        'source_url': SOURCE, 'source_sha256': SHA256,
        'license': '출처 표시 조건 (원본 및 가공 저장소 README 참조)',
        'simplification': 'upstream Douglas-Peucker 0.0005 degrees, coordinates 6 decimals; no additional simplification',
        'area_method': 'WGS84 ellipsoidal geodesic area of simplified rings; holes subtracted; not official area',
        'warning': '2023년 경계 참고도. 현재 및 조회기간의 경계와 다를 수 있음.',
    }, 'features': sorted(features, key=lambda f: f['properties']['code'])}


if __name__ == '__main__':
    raw = urlopen(SOURCE, timeout=60).read()
    assert hashlib.sha256(raw).hexdigest() == SHA256, 'Unexpected source content'
    result = build(json.loads(raw))
    target = Path(__file__).resolve().parents[1] / 'frontend/data/changwon-legal-boundaries.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'Wrote {len(result["features"])} legal-dong boundaries to {target}')
