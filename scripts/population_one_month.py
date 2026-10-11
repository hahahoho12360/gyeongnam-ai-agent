"""Bounded original-API probe and one-month verified Firestore repair."""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import population_history_final as core
from scripts.probe_population_repair import query, save, OUT
from scripts.collect.data_go_kr import DataGoKrClient
from scripts.probe_configured_api import SPECS
from scripts.population_repair_core import validate_rows
from backend.db import get_store, FirestoreStore, utcnow_iso

SAMGYE='4812725028'

class StopCollection(RuntimeError): pass

class Budget:
    def __init__(self, seconds=3600, threshold=6):
        self.deadline=time.monotonic()+seconds
        self.threshold=threshold; self.failures=0; self.events=[]; self.count=0
        self.lock=threading.Lock()
    def check(self):
        with self.lock:
            if time.monotonic()+30>=self.deadline: raise StopCollection('deadline_reached')
            if self.failures>=self.threshold: raise StopCollection('provider_circuit_open')
    def record(self,event,failed):
        with self.lock:
            self.failures=self.failures+1 if failed else 0
            self.count+=1; self.events.append(event); self.events=self.events[-100:]
            save('request_progress.json',{'requests':self.count,'consecutive_failures':self.failures,
                'seconds_remaining':round(self.deadline-time.monotonic()),'recent_requests':self.events})
        print(json.dumps(event,ensure_ascii=False),flush=True)

class BoundedClient(DataGoKrClient):
    budget=None
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
    def get(self,url,params=None,**kwargs):
        p={'serviceKey':self.key,**(params or {})}
        p.setdefault('pageNo',1);p.setdefault('numOfRows',1000)
        for attempt in range(2):
            self.budget.check(); start=time.monotonic()
            event={'code':p.get('stdgCd'),'from':p.get('srchFrYm'),'to':p.get('srchToYm'),
                'endpoint':url.rsplit('/',1)[-1],'page':p['pageNo'],'attempt':attempt+1,
                'http_status':None,'api_result_codes':[]}
            try:
                r=requests.get(url,params=p,timeout=(5,20))
                event['http_status']=r.status_code
                if r.status_code==429:raise RuntimeError('http_rate_limit')
                if r.status_code>=500:raise RuntimeError('http_server_error')
                if r.status_code>=400:raise RuntimeError('http_request_or_permission_error')
                try: payload=r.json()
                except ValueError: payload=self._xml_to_dict(r.text)
                def codes(node):
                    if isinstance(node,dict):
                        for k,v in node.items():
                            if k in ('resultCode','resultCd','returnReasonCode'):event['api_result_codes'].append(str(v))
                            elif isinstance(v,(dict,list)):codes(v)
                    elif isinstance(node,list):
                        for x in node:codes(x)
                codes(payload)
                error=self.error_message(payload)
                if error and not self.is_no_data_error(error):
                    raise RuntimeError('api_rate_limit' if (any(t in error.upper() for t in ('LIMIT','QUOTA')) or '22' in event['api_result_codes']) else 'api_result_error')
                event.update(outcome='success',elapsed_seconds=round(time.monotonic()-start,3),
                    total_count=self.total_count(payload),rows=len(self.items(payload)))
                self.budget.record(event,False);return payload
            except Exception as exc:
                category=('read_timeout' if isinstance(exc,requests.exceptions.ReadTimeout) else
                    'connect_timeout' if isinstance(exc,requests.exceptions.ConnectTimeout) else
                    'connection_error' if isinstance(exc,requests.exceptions.ConnectionError) else
                    str(exc) if isinstance(exc,RuntimeError) else 'malformed_response')
                event.update(outcome=category,elapsed_seconds=round(time.monotonic()-start,3))
                self.budget.record(event,True)
                if attempt or category in ('http_request_or_permission_error','api_result_error','api_rate_limit','http_rate_limit','malformed_response'):
                    raise RuntimeError(category) from None
                self.budget.check();time.sleep(1)


def configure():
    for source,(ue,qe) in SPECS.items():
        if source not in core.SOURCES:continue
        if not os.getenv(ue):raise ValueError('Missing endpoint configuration')
        os.environ[qe]=json.dumps({'stdgCd':'{bjd_code}','srchFrYm':'{yyyymm}',
            'srchToYm':'{yyyymm}','lv':'7','regSeCd':'1','type':'JSON'})


def probe(month):
    y,m=map(int,month.split('-')); end_index=y*12+m-1+2
    end=f'{end_index//12:04d}-{end_index%12+1:02d}'
    results=[]
    for source in core.SOURCES:
        bundles={}
        for mode,last in [('single',month),('range',end)]:
            start=time.monotonic();before=BoundedClient.budget.count
            template={'stdgCd':SAMGYE,'srchFrYm':month.replace('-',''),
                'srchToYm':last.replace('-',''),'lv':'7','regSeCd':'1','type':'JSON'}
            item={'source':source,'mode':mode,'from':month,'to':last,'code':SAMGYE}
            try:
                rows=query(BoundedClient(),source,SAMGYE,last,template_override=template)
                for row in rows:
                    period=str(row.get('statsYm',''));validate_rows([row],SAMGYE,period[:4]+'-'+period[4:6])
                    if not month.replace('-','')<=period<=last.replace('-',''):raise ValueError('period_mismatch')
                bundles[mode]=[r for r in rows if str(r.get('statsYm'))==month.replace('-','')]
                item.update(status='success',row_count=len(rows),target_month_rows=len(bundles[mode]))
            except Exception as exc:
                item.update(status='failed',reason=str(exc) if isinstance(exc,(RuntimeError,StopCollection)) else type(exc).__name__)
            item.update(elapsed_seconds=round(time.monotonic()-start,2),
                request_attempts=BoundedClient.budget.count-before,
                requests=[e for e in BoundedClient.budget.events if e['code']==SAMGYE and e['endpoint']==os.environ[SPECS[source][0]].rsplit('/',1)[-1] and e['from']==template['srchFrYm'] and e['to']==template['srchToYm']])
            item['pages_received']=len({e['page'] for e in item['requests'] if e['outcome']=='success'})
            results.append(item);save('samgye_probe.json',{'outcomes':results,'database_writes':0})
        if len(bundles)==2:
            same=sorted(json.dumps(r,sort_keys=True) for r in bundles['single'])==sorted(json.dumps(r,sort_keys=True) for r in bundles['range'])
            results[-1]['same_target_month_as_single']=same
            save('samgye_probe.json',{'outcomes':results,'database_writes':0})
            if not same:raise ValueError('Single/range response mismatch')
    return all(r['status']=='success' for r in results if r['mode']=='single')


def run(month,max_minutes=60):
    configure();BoundedClient.budget=Budget(max_minutes*60)
    status={'month':month,'status':'probing','applied_this_run':0,'updated_at':utcnow_iso()}
    save('one_month_status.json',status)
    try:
        if not probe(month):raise StopCollection('samgye_probe_failed')
        store=get_store()
        if not isinstance(store,FirestoreStore):raise ValueError('Actual Firestore required')
        master,children,codes=core.inventory(json.loads((ROOT/'data/current_changwon_codes_verified20261010.json').read_text()))
        totals=json.loads((ROOT/'data/population_official_history_totals.json').read_text())['months'][month]
        before=core.check_totals([r for r in store.filter_eq('monthly_data','month',month) if r.get('region_id') in master],totals)
        save('before_totals.json',before)
        if before['status']=='passed':
            status.update(status='already_verified',firestore_verified=True);return status
        status['status']='collecting';save('one_month_status.json',status)
        core.DataGoKrClient=BoundedClient
        errors=core.prefetch_window([month],codes,workers=2)
        if errors:raise StopCollection('incomplete_original_api_capture')
        BoundedClient.budget.check()
        captures={(s,c):json.loads((OUT/f'{s}_{c}_{month}.json').read_text())['rows'] for s in core.SOURCES for c in codes}
        plan=core.resolve_month(month,master,children,captures,totals,'totals_first')
        save(f'prepared_plan_{month}.json',plan)
        status['status']='validated';save('one_month_status.json',status)
        core.apply_plan(store,plan)
        after_rows=[r for r in store.filter_eq('monthly_data','month',month) if r.get('region_id') in master]
        after=core.check_totals(after_rows,totals);save('after_totals.json',after)
        mismatches=[]
        by_id={r['region_id']:r for r in after_rows}
        for code,patch in plan['patches'].items():
            for key,value in patch['metrics'].items():
                if by_id.get(code,{}).get('metrics',{}).get(key)!=value:mismatches.append({'region':code,'metric':key})
        save('after_patch_verification.json',{'checked_regions':len(plan['patches']),'mismatches':mismatches,
            'naeseo_metrics':by_id.get('4812725000',{}).get('metrics',{})})
        if after['status']!='passed' or mismatches:raise ValueError('post_write_verification_failed')
        status.update(status='complete',applied_this_run=1,firestore_verified=True,
            verified_regions=len(plan['patches']),pending_index_recompute=True)
        print('Applied and verified:',month,flush=True)
        return status
    except Exception as exc:
        status.update(status='paused' if isinstance(exc,StopCollection) else 'blocked',
            reason=str(exc) if isinstance(exc,StopCollection) else type(exc).__name__,firestore_verified=False)
        return status
    finally:
        status['updated_at']=utcnow_iso();save('one_month_status.json',status)
        summary=json.dumps(status,ensure_ascii=False,indent=2);print(summary,flush=True)
        if os.getenv('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('### One-month verified repair\n```json\n'+summary+'\n```\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--month',default='2024-08');p.add_argument('--max-minutes',type=int,default=60);a=p.parse_args()
    result=run(a.month,a.max_minutes)
    sys.exit(0 if result['status'] in ('complete','already_verified') else 2)
