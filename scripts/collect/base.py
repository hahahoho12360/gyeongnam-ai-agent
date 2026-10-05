from __future__ import annotations
import os
from dataclasses import dataclass
from .data_go_kr import DataGoKrClient

@dataclass
class SourceSpec:
    key: str
    env_url: str
    cadence: str
    source_as_of_rule: str

SOURCES=[
 SourceSpec('population','POPULATION_API_URL','monthly','월말 주민등록 집계'),
 SourceSpec('age_population','AGE_POPULATION_API_URL','monthly','월말 주민등록 집계'),
 SourceSpec('single_household','SINGLE_HOUSEHOLD_API_URL','monthly','월말 주민등록 집계'),
 SourceSpec('apartment_basic','APARTMENT_BASIC_API_URL','monthly_snapshot','조회 시점 기본정보'),
 SourceSpec('building_register','BUILDING_REGISTER_API_URL','monthly','건축HUB 갱신 기준'),
 SourceSpec('apt_sale','APT_SALE_API_URL','daily_recent_3m','계약/신고 반영 시점'),
 SourceSpec('apt_rent','APT_RENT_API_URL','daily_recent_3m','확정일자·신고 반영 시점'),
 SourceSpec('commerce','COMMERCE_API_URL','weekly_monthly_snapshot','조회 시점 업소목록'),
 SourceSpec('household_birth_death','HOUSEHOLD_BIRTH_DEATH_API_URL','monthly','월말 집계'),
 SourceSpec('other_real_estate','OTHER_REAL_ESTATE_API_URL','daily_recent_3m','신고 반영 시점'),
 SourceSpec('onbid','ONBID_PROPERTY_API_URL','on_demand_or_daily','온비드 갱신 시점'),
 SourceSpec('kosis','KOSIS_API_URL','benchmark','공표 기준')]

def configured_sources(): return [s for s in SOURCES if os.getenv(s.env_url)]

def fetch_source(spec: SourceSpec, params: dict):
    url=os.getenv(spec.env_url)
    if not url: raise RuntimeError(f'{spec.env_url}가 설정되지 않았습니다.')
    client=DataGoKrClient(); payload=client.get(url,params); return client.items(payload),payload
