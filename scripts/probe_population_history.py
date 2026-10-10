"""Read-only probe of original APIs' historical range support."""
import json
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.probe_population_repair import query, OUT, save
from scripts.population_repair_core import validate_rows
from scripts.collect.data_go_kr import DataGoKrClient
from scripts.probe_configured_api import SPECS

def main():
    outcomes=[]
    for source in ['population','age_population','single_household']:
        _, qe=SPECS[source]
        template=json.loads(os.environ[qe])
        template['srchFrYm']='202607';template['srchToYm']='202609'
        os.environ[qe]=json.dumps(template)
        for code in ['4812510600','4812131021']:
            try:
                rows=query(DataGoKrClient(),source,code,'2026-09')
            except RuntimeError as exc:
                message=str(exc).replace(os.getenv('DATA_GO_KR_SERVICE_KEY',''),'[redacted]')[:500]
                outcomes.append({'source':source,'code':code,'status':'range_rejected','safe_error':message})
                continue
            months=sorted({str(r.get('statsYm','')) for r in rows})
            for month in months:
                if len(month)!=6 or not '202210'<=month<='202609':raise ValueError('Unexpected historical month')
                validate_rows([r for r in rows if str(r.get('statsYm',''))==month],code,month[:4]+'-'+month[4:])
            outcomes.append({'source':source,'code':code,'months':months,'rows':len(rows)})
    save('history_probe_summary.json',{'status':'range_probe_complete','database_writes':0,'outcomes':outcomes})

if __name__=='__main__':
    try:main()
    except Exception as exc:
        message=str(exc).replace(os.getenv('DATA_GO_KR_SERVICE_KEY',''),'[redacted]')[:500] if isinstance(exc,RuntimeError) else ''
        save('history_probe_failure.json',{'status':'blocked','exception_type':type(exc).__name__,'database_writes':0,'safe_error':message})
        print('Historical range probe blocked:',type(exc).__name__);sys.exit(2)
