"""One resumable month in a serial workflow; classify whether later months may run."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.probe_population_repair import OUT, save
from backend.db import utcnow_iso

HALT_OUTCOMES={'http_rate_limit','api_rate_limit','http_request_or_permission_error','api_result_error'}

def should_continue(status,progress,timed_out=False):
    if timed_out:return False
    if status.get('status') in ('complete','already_verified'):return True
    if progress.get('consecutive_failures',0)>=6:return False
    if any(r.get('outcome') in HALT_OUTCOMES for r in progress.get('recent_requests',[])):return False
    # A provider-specific or validation failure in one month does not invent data
    # and does not prevent a later, independent month from being attempted.
    return status.get('reason') in ('incomplete_original_api_capture','UnresolvedMonth','ValueError')

def read(name):
    path=OUT/name
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

def main(month):
    totals=json.loads((ROOT/'data/population_official_history_totals.json').read_text())['months']
    if month not in totals or not '2024-09'<=month<='2026-08':raise ValueError('Outside authorized follow-up months')
    for name in ('one_month_status.json','request_progress.json'):(OUT/name).unlink(missing_ok=True)
    timed_out=False
    try:
        result=subprocess.run([sys.executable,str(ROOT/'scripts/population_one_month.py'),
            '--month',month,'--max-minutes','60','--skip-probe'],timeout=70*60)
        returncode=result.returncode
    except subprocess.TimeoutExpired:
        timed_out=True;returncode=124
        save('one_month_status.json',{'month':month,'status':'paused','reason':'absolute_process_timeout',
            'firestore_verified':False,'instruction':'Re-read Firestore before retry; writes may need verification.'})
    status=read('one_month_status.json');progress=read('request_progress.json')
    proceed=should_continue(status,progress,timed_out)
    derived='not_attempted'
    if returncode==0 and status.get('status') in ('complete','already_verified'):
        try:
            p=subprocess.run([sys.executable,str(ROOT/'scripts/population_only_derived.py'),'--month',month],timeout=20*60)
            derived='complete' if p.returncode==0 else 'failed'
        except subprocess.TimeoutExpired:
            derived='paused';proceed=False
    report={'month':month,'repair':status,'derived_status':derived,
        'continue_processing':proceed,'updated_at':utcnow_iso()}
    save('followup_month_step.json',report)
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('continue_processing='+str(proceed).lower()+'\n')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('### '+month+' repair and population-only recalculation\n```json\n'+json.dumps(report,ensure_ascii=False,indent=2)+'\n```\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    # Final workflow verification determines overall success. Retain month issues
    # without killing independent later months.
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--month',required=True);a=p.parse_args()
    main(a.month)
