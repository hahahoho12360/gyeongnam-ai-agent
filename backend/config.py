from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _bool(name: str, default: bool=False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {'1','true','yes','on'}

def _csv(name: str, default: str='') -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(',') if x.strip()]

@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv('OPENAI_API_KEY','')
    openai_model: str = os.getenv('OPENAI_MODEL','gpt-6-luna')
    openai_max_output_tokens: int = int(os.getenv('OPENAI_MAX_OUTPUT_TOKENS','1200'))
    firebase_service_account_json: str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON','')
    google_application_credentials: str = os.getenv('GOOGLE_APPLICATION_CREDENTIALS','')
    firebase_project_id: str = os.getenv('FIREBASE_PROJECT_ID','')
    use_memory_db: bool = _bool('USE_MEMORY_DB', False)
    allowed_origins: list[str] = None
    admin_refresh_token: str = os.getenv('ADMIN_REFRESH_TOKEN','')
    data_go_kr_service_key: str = os.getenv('DATA_GO_KR_SERVICE_KEY','')
    recent_real_estate_recalc_months: int = int(os.getenv('RECENT_REAL_ESTATE_RECALC_MONTHS','3'))
    enable_on_demand_refresh: bool = _bool('ENABLE_ON_DEMAND_REFRESH', False)
    live_real_estate_ttl_hours: int = int(os.getenv('LIVE_REAL_ESTATE_TTL_HOURS','24'))
    live_onbid_ttl_hours: int = int(os.getenv('LIVE_ONBID_TTL_HOURS','6'))

    def __post_init__(self):
        object.__setattr__(self, 'allowed_origins', _csv('ALLOWED_ORIGINS','http://127.0.0.1:5500,http://localhost:5500'))

settings = Settings()
