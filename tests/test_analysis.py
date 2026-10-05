from fastapi.testclient import TestClient
from backend.main import app

def test_demo_analysis_and_compare():
    with TestClient(app) as client:
        regions=client.get('/api/analytics/regions').json()
        assert len(regions) >= 3
        rid=regions[0]['id']
        res=client.get(f'/api/analytics/regions/{rid}/compare?answer_mode=detail')
        assert res.status_code == 200
        body=res.json()
        assert body['summary']['count'] >= 12
        assert len(body['charts']) >= 2

from backend.tooling import dispatch


def test_domain_specific_tools_share_analysis_backend():
    with TestClient(app) as client:
        rid=client.get('/api/analytics/regions').json()[0]['id']
        for tool in ('get_housing_market','get_rental_market','get_commerce_trend','get_auction_market'):
            result=dispatch(tool,{'region':rid,'months':12})
            assert 'summary' in result and 'chart' in result and 'rows' in result
