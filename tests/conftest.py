import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import os
os.environ['USE_MEMORY_DB']='true'
os.environ['ANALYSIS_SCOPE_PREFIX']=''
os.environ.pop('OPENAI_API_KEY',None)

os.environ['DEMO_SEED_ON_START']='true'

