"""Use existing GitHub API configuration; read-only, never print credentials."""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.bootstrap_regions import _extract, _is_gyeongnam_eup_myeon_dong, URL
from scripts.collect.data_go_kr import DataGoKrClient
from scripts.probe_configured_api import SPECS, render

OUT = ROOT / 'artifacts/population_repair'

def current_codes(key):
    import requests
    session=requests.Session()
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    retry=Retry(total=3,connect=3,read=3,status=3,backoff_factor=1.5,status_forcelist=[429,500,502,503,504])
    session.mount('https://', HTTPAdapter(max_retries=retry))
    rows=[]
    for page in range(1,101):
        response=session.get(URL,params={'ServiceKey':key,'pageNo':page,'numOfRows':1000,'type':'json'},timeout=60)
        response.raise_for_status()
        batch,total=_extract(response.json())
        if not batch:
            raise RuntimeError('Current code response was empty before completion')
        rows.extend(batch)
        print(f'Current code page {page}: {len(batch)} rows; cumulative {len(rows)}',flush=True)
        if total and len(rows)>=total:
            return rows
        if not total and len(batch)<1000:
            return rows
    raise RuntimeError('Code pagination incomplete')

def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def query(client, source, code, month, *, template_override=None):
    ue, qe = SPECS[source]
    url = os.environ[ue]
    template = template_override if template_override is not None else json.loads(os.environ[qe])
    if any('key' in k.lower() or 'token' in k.lower() for k in template):
        raise ValueError('Credentials must come from the client, not query templates')
    params = render(template, month, code)
    start = time.monotonic()
    rows, pages, totals = [], 0, []
    for page in range(1, 101):
        payload = client.get(url, {**params, 'pageNo': page, 'numOfRows': 1000})
        if not isinstance(payload, dict) or '_raw' in payload:
            raise RuntimeError('Malformed original API response')
        items = client.items(payload)
        total = client.total_count(payload)
        pages += 1
        totals.append(total)
        rows.extend(items)
        if not items and total is None and not client.is_no_data_error(client.error_message(payload) or ''):
            raise RuntimeError('Empty response without explicit no-data evidence')
        if total is not None and len(rows) > total:
            raise RuntimeError('API row count exceeds advertised total')
        if not items and total is not None and len(rows) < total:
            raise RuntimeError('API ended before all advertised rows were received')
        if not items or (total is not None and len(rows) >= total) or (total is None and len(items) < 1000):
            break
    else:
        raise RuntimeError('Pagination incomplete')
    known_totals = [t for t in totals if t is not None]
    if len(set(known_totals)) > 1 or (known_totals and len(rows) != known_totals[-1]):
        raise RuntimeError('Original API pagination counts are inconsistent')
    evidence = {'source': source, 'requested_code': code, 'month': month, 'url': url,
                'params': params, 'pages': pages, 'total_counts': totals,
                'row_count': len(rows), 'elapsed_seconds': round(time.monotonic()-start, 2),
                'http': 'client requires successful HTTP status; errors abort', 'rows': rows}
    save(f'{source}_{code}_{month}.json', evidence)
    print(json.dumps({k:v for k,v in evidence.items() if k!='rows'}, ensure_ascii=False), flush=True)
    return rows

def main():
    missing=json.loads((ROOT/'data/boundaries/changwon_missing_regions_202609.json').read_text())
    all_codes=current_codes(os.environ['DATA_GO_KR_SERVICE_KEY'])
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
