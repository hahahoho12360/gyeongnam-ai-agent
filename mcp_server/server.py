from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from mcp.server.fastmcp import FastMCP
from backend.tooling import dispatch

mcp=FastMCP('gyeongnam-area-ai')

@mcp.tool()
def get_region_summary(region: str, months: int=12) -> dict:
    """경남 지역의 최근 통합 요약을 조회합니다."""
    return dispatch('get_region_summary',{'region':region,'months':months})

@mcp.tool()
def get_population_trend(region: str, months: int=36) -> dict:
    """경남 지역의 월별 인구 추세와 차트 데이터를 조회합니다."""
    return dispatch('get_population_trend',{'region':region,'months':months})

@mcp.tool()
def get_housing_market(region: str, months: int=36) -> dict:
    """아파트 매매가격·거래량·거래회전율 추세를 조회합니다."""
    return dispatch('get_housing_market',{'region':region,'months':months})

@mcp.tool()
def get_rental_market(region: str, months: int=36) -> dict:
    """전세가격·전월세 거래량·월세화 비율 추세를 조회합니다."""
    return dispatch('get_rental_market',{'region':region,'months':months})

@mcp.tool()
def get_commerce_trend(region: str, months: int=36) -> dict:
    """상가 수·순증감·업종다양성 추세를 조회합니다."""
    return dispatch('get_commerce_trend',{'region':region,'months':months})

@mcp.tool()
def get_auction_market(region: str, months: int=12) -> dict:
    """온비드 공매 지표 추세를 조회합니다."""
    return dispatch('get_auction_market',{'region':region,'months':months})

@mcp.tool()
def compare_regions(region: str, months: int=36) -> dict:
    """인접·유사 Peer·seeded random 비교군과 대상 지역을 비교합니다."""
    return dispatch('compare_regions',{'region':region,'months':months})

@mcp.tool()
def get_live_area_snapshot(region: str) -> dict:
    """캐시 우선 정책으로 최신 저장값을 조회하고, 허용된 경우 TTL 초과 시 최신 실거래를 갱신합니다."""
    return dispatch('get_live_area_snapshot',{'region':region})

@mcp.tool()
def get_region_indexes(region: str) -> dict:
    """지역활력·주거시장압력·생활편의·상권변화 지수를 조회합니다."""
    return dispatch('get_region_indexes',{'region':region})

if __name__=='__main__':
    mcp.run(transport='stdio')
