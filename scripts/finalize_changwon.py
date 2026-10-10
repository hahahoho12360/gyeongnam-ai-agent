from __future__ import annotations

"""Checkpoint 3.2 — 창원 1차 MVP 복합지수 계산 + 최종 Data Quality 검증.

실제 Firestore의 창원(법정지역코드 4812*) 최신월 자료를 대상으로:
1) 최신 파생변수 재계산
2) 창원 내부 percentile 기준 4개 Composite Index 계산
3) 지수 메타데이터를 함께 저장
4) 창원 범위 Data Quality 리포트 저장
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from backend.data_quality import quality_report
from backend.db import get_store, utcnow_iso
from backend.indexes import compute_index_rows, component_population_counts, methodology_payload
from backend.metrics import compute_derived
from scripts.pipeline import month_shift

SCOPE_PREFIX='4812'
REPORT_ID='changwon_v32_final'


def _region_code(row: dict[str,Any]) -> str:
    return str(row.get('bjd_code') or row.get('id') or '').strip()


def changwon_region_ids() -> set[str]:
    return {
        str(r.get('id')) for r in get_store().list('regions')
        if r.get('id') and not r.get('is_demo') and _region_code(r).startswith(SCOPE_PREFIX)
    }


def latest_month_for_scope(region_ids:set[str]) -> str:
    months=[
        str(r.get('month')) for r in get_store().list('monthly_data')
        if str(r.get('region_id')) in region_ids and r.get('month')
        and not (r.get('freshness') or {}).get('is_demo')
    ]
    if not months:
        raise RuntimeError('창원 monthly_data가 없습니다.')
    return max(months)


def recompute_latest_derived(month:str, region_ids:set[str]) -> list[dict[str,Any]]:
    store=get_store()
    rows=[
        r for r in store.filter_eq('monthly_data','month',month)
        if str(r.get('region_id')) in region_ids and not (r.get('freshness') or {}).get('is_demo')
    ]
    refreshed=[]
    for row in rows:
        rid=str(row.get('region_id'))
        metrics=dict(row.get('metrics') or {})
        prev=store.get('monthly_data',f'{rid}_{month_shift(month,-1)}') or {}
        yearago=store.get('monthly_data',f'{rid}_{month_shift(month,-12)}') or {}
        derived=compute_derived(metrics,prev.get('metrics') or {},yearago.get('metrics') or {})
        store.update('monthly_data',row['id'],{'derived':derived})
        row=dict(row); row['derived']=derived
        refreshed.append(row)
    return refreshed


def index_stats(rows:list[dict[str,Any]]) -> dict[str,Any]:
    names=('vitality_index','housing_pressure_index','living_convenience_index','commerce_change_index')
    out={}
    for name in names:
        vals=[
            float((r.get('indexes') or {}).get(name))
            for r in rows if isinstance((r.get('indexes') or {}).get(name),(int,float))
        ]
        out[name]={
            'count':len(vals),
            'min':round(min(vals),2) if vals else None,
            'max':round(max(vals),2) if vals else None,
            'mean':round(mean(vals),2) if vals else None,
        }
    return out


def finalize(month:str|None=None, *, dry_run:bool=False) -> dict[str,Any]:
    store=get_store()
    region_ids=changwon_region_ids()
    if not region_ids:
        raise RuntimeError('regions에서 창원(4812*) Master를 찾지 못했습니다.')
    month=month or latest_month_for_scope(region_ids)

    latest_rows=[
        r for r in store.filter_eq('monthly_data','month',month)
        if str(r.get('region_id')) in region_ids and not (r.get('freshness') or {}).get('is_demo')
    ]
    if dry_run:
        return {
            'dry_run':True,
            'scope':'changwon',
            'scope_prefix':SCOPE_PREFIX,
            'month':month,
            'master_regions':len(region_ids),
            'latest_month_rows':len(latest_rows),
        }

    rows=recompute_latest_derived(month,region_ids)
    computed=compute_index_rows(rows)
    method=methodology_payload(comparison_scope='changwon',month=month,region_count=len(rows))
    generated=utcnow_iso()

    for row in rows:
        rid=str(row.get('region_id'))
        idx=computed.get(rid,{})
        meta={
            'method_version':'3.2',
            'comparison_scope':'changwon',
            'comparison_month':month,
            'comparison_region_count':len(rows),
            'official_statistic':False,
            'computed_at':generated,
        }
        store.update('monthly_data',row['id'],{'indexes':idx,'index_meta':meta})
        latest=store.get('region_latest',rid)
        if latest and latest.get('month')==month:
            store.update('region_latest',rid,{'derived':row.get('derived') or {},'indexes':idx,'index_meta':meta})
        row['indexes']=idx

    quality=quality_report(scope_prefix=SCOPE_PREFIX,latest_month=month)
    report={
        'version':'3.2',
        'scope':'changwon',
        'scope_prefix':SCOPE_PREFIX,
        'generated_at':generated,
        'latest_month':month,
        'methodology':method,
        'component_population_counts':component_population_counts(rows),
        'index_stats':index_stats(rows),
        'quality_report':quality,
        'submission_note':'1차 MVP 비교범위는 창원시이며, 경남 전체 확장 시 동일 방법으로 재표준화한다.',
    }
    store.set('rollout_reports',REPORT_ID,report,merge=False)

    out=ROOT/'artifacts'/'changwon_v32_final_report.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main()->int:
    p=argparse.ArgumentParser(description='Checkpoint 3.2 창원 복합지수 + 최종 데이터 품질 검증')
    p.add_argument('--month',default=None,help='기본: 창원 monthly_data 최신월')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    report=finalize(a.month,dry_run=a.dry_run)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
