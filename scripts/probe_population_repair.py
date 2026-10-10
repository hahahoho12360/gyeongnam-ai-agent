"""Use existing GitHub API configuration; read-only, never print credentials."""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.bootstrap_regions import _fetch_all, _is_gyeongnam_eup_myeon_dong
from scripts.collect.data_go_kr import DataGoKrClient
from scripts.probe_configured_api import SPECS, render

OUT = ROOT / 'artifacts/population_repair'

def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def query(client, source, code, month):
    ue, qe = SPECS[source]
    url = os.environ[ue]
    template = json.loads(os.environ[qe])
    if any('key' in k.lower() or 'token' in k.lower() for k in template):
        raise ValueError('Credentials must come from the client, not query templates')
    params = render(template, month, code)
    start = time.monotonic()
    rows, pages, totals = [], 0, []
    for page in range(1, 101):
        payload = client.get(url, {**params, 'pageNo': page, 'numOfRows': 1000})
        items = client.items(payload)
        total = client.total_count(payload)
        pages += 1
        totals.append(total)
        rows.extend(items)
        if not items or (total is not None and len(rows) >= total) or (total is None and len(items) < 1000):
            break
    else:
        raise RuntimeError('Pagination incomplete')
    evidence = {'source': source, 'requested_code': code, 'month': month, 'url': url,
                'params': params, 'pages': pages, 'total_counts': totals,
                'row_count': len(rows), 'elapsed_seconds': round(time.monotonic()-start, 2),
                'http': 'client requires successful HTTP status; errors abort', 'rows': rows}
    save(f'{source}_{code}_{month}.json', evidence)
    print(json.dumps({k:v for k,v in evidence.items() if k!='rows'}, ensure_ascii=False), flush=True)
    return rows

def main():
    missing=json.loads((ROOT/'data/boundaries/changwon_missing_regions_202609.json').read_text())
    all_codes=_fetch_all(os.environ['DATA_GO_KR_SERVICE_KEY'])
    master=[r for r in all_codes if _is_gyeongnam_eup_myeon_dong(r) and str(r['region_cd']).startswith('4812')]
    index={str(r['region_cd']):r for r in master}
    unresolved=[r['id'] for r in missing if r['id'] not in index]
    if unresolved:
        raise RuntimeError(f'Current code API does not confirm missing candidates: {unresolved}')
    confirmed=[index[r['id']] for r in missing]
    children=[r for r in all_codes if str(r.get('region_cd','')).startswith('48121310') and str(r.get('region_cd',''))[-2:]!='00']
    if not children:
        raise RuntimeError('Current code API did not supply Buk-myeon ri codes')
    save('current_changwon_codes.json', [r for r in all_codes if str(r.get('region_cd','')).startswith('4812')])
    save('confirmed_23.json', confirmed)
    client=DataGoKrClient()
    outcomes=[]
    for source in ['population','age_population','single_household']:
        for code in ['4812510600','4812131000',str(children[0]['region_cd'])]:
            rows=query(client,source,code,'2026-09')
            outcomes.append({'source':source,'code':code,'rows':len(rows)})
    save('probe_summary.json', {'status':'probe_complete','database_writes':0,'confirmed_master_codes':len(master),
                              'confirmed_missing_codes':len(confirmed),'buk_myeon_child_code':str(children[0]['region_cd']),
                              'outcomes':outcomes})

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        # HTTP error strings can include a request URL containing serviceKey.
        save('failure.json', {'status':'blocked','exception_type':type(exc).__name__,'database_writes':0})
        print('Probe blocked:', type(exc).__name__, flush=True)
        raise SystemExit(2)
