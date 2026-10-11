import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import os
os.environ['USE_MEMORY_DB']='true'
os.environ['ANALYSIS_SCOPE_PREFIX']=''
os.environ.pop('OPENAI_API_KEY',None)

os.environ['DEMO_SEED_ON_START']='true'


# Legacy API tests run as an explicitly authenticated test account only.
# Production has no authentication bypass switch.
import pytest
@pytest.fixture(autouse=True)
def authenticated_test_account():
    from backend.main import app
    from backend.auth import required_user
    prior=app.dependency_overrides.get(required_user)
    app.dependency_overrides[required_user]=lambda:'legacy-test-user'
    yield
    if prior is None:app.dependency_overrides.pop(required_user,None)
    else:app.dependency_overrides[required_user]=prior
