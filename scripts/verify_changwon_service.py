"""v3.2 이후 FastAPI 실데이터 연결을 읽기 전용으로 검증한다."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings


def verify() -> dict:
    if settings.use_memory_db:
        raise RuntimeError('실데이터 검증은 USE_MEMORY_DB=false로 실행해야 합니다.')
    if settings.analysis_scope_prefix != '4812':
        raise RuntimeError('ANALYSIS_SCOPE_PREFIX=4812로 창원 서비스 범위를 지정하세요.')
    with TestClient(app) as client:
        def get(path):
            response=client.get(path)
            response.raise_for_status()
            return response.json()

        get('/health')
        report=get('/api/meta/changwon-mvp')
        quality=report['quality_report']
        if report.get('scope') != 'changwon' or not quality.get('minimum_100_points_met'):
            raise RuntimeError('v3.2 창원 리포트 또는 최소 데이터 포인트 요건을 확인하세요.')
        if quality.get('invalid_numeric_count') != 0:
            raise RuntimeError('v3.2 리포트에 잘못된 수치가 있습니다.')
        regions=get('/api/analytics/regions')
        if not regions or any(not str(r.get('bjd_code') or r['id']).startswith('4812') for r in regions):
            raise RuntimeError('서비스 지역 목록이 창원 범위와 일치하지 않습니다.')
        if len(regions) != quality['regions_master_count']:
            raise RuntimeError('현재 Master 수와 v3.2 리포트가 다릅니다. finalize를 다시 확인하세요.')
        # 지수자료가 존재하는 대표지역 하나를 찾아 실제 저장 결과와 API 연결을 점검한다.
        selected=None
        for region in regions:
            rid=region['id']
            response=client.get(f'/api/analytics/regions/{rid}/indexes')
            if response.status_code != 200:
                continue
            data=response.json()
            if data.get('index_meta',{}).get('comparison_month') == report['latest_month']:
                selected=(rid,data)
                break
        if selected is None:
            raise RuntimeError('v3.2 비교월 메타데이터를 가진 지역이 없습니다.')
        rid,data=selected
        meta=data['index_meta']
        if meta.get('comparison_scope') != 'changwon' or meta.get('official_statistic') is not False:
            raise RuntimeError('지수 메타데이터의 비교범위/공식통계 여부가 잘못되었습니다.')
        bundle=get(f'/api/analytics/regions/{rid}/compare?answer_mode=simple')
        if not bundle['charts'] or not bundle['summary']['count']:
            raise RuntimeError('간단 응답의 추세/그래프가 연결되지 않았습니다.')
        for fmt in ('csv','json'):
            client.get(f'/api/analytics/export/{rid}?format={fmt}').raise_for_status()
        return {
            'version':'3.3', 'status':'passed', 'scope':'changwon',
            'region_count':len(regions), 'checked_region':rid,
            'comparison_month':report['latest_month'],
            'report_generated_at':report.get('generated_at'),
            'checks':['health','saved_v32_report','region_scope','index_metadata','simple_chart','csv','json'],
            'limitations':['읽기 전용 API 검증이며 CRUD/대화는 자동테스트로 별도 검증한다.',
                           'OpenAI 실호출·외부 배포 URL·MCP 실호출은 별도 검증이 필요하다.',
                           '품질 집계는 저장된 v3.2 리포트 시점 기준이다.'],
        }


if __name__ == '__main__':
    result=verify()
    output=ROOT/'artifacts'/'changwon_v33_service_report.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
