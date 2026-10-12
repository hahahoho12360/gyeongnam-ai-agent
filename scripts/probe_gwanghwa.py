"""Read-only original response evidence for the Gwanghwa validation failure."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.population_one_month import configure,BoundedClient,Budget
from scripts.probe_population_repair import query,save
from scripts.population_repair_core import validate_rows,ADAPTERS,validate_bundle
from scripts.collect.redaction import redact

configure();BoundedClient.budget=Budget(600,threshold=10)
results={};bundle={}
for source in ADAPTERS:
    try:
        rows=query(BoundedClient(),source,'4812912400','2025-09')
        save('gwanghwa_raw_'+source+'.json',redact({'rows':rows,'requested_code':'4812912400','month':'2025-09'}))
        item={'rows':rows,'row_count':len(rows)}
        try:
            clean=validate_rows(rows,'4812912400','2025-09');item['validation']='passed'
            bundle[source]=ADAPTERS[source](clean,[{'id':'4812912400','bjd_code':'4812912400','name':'광화동'}],'48129').get('4812912400',{})
        except ValueError as exc:
            item.update(validation='failed',reason=str(exc))
        results[source]=item
    except Exception as exc:
        results[source]={'request':'failed','exception_type':type(exc).__name__}
    save('gwanghwa_diagnostic.json',redact(results))
    print(json.dumps(redact({source:results[source]}),ensure_ascii=False),flush=True)
if len(bundle)==3:
    try:validate_bundle(bundle);print('All source bundle totals passed',flush=True)
    except ValueError as exc:print('Bundle check:',str(exc),flush=True)
