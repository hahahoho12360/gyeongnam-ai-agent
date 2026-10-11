import json
import pytest
import requests
from scripts.collect.redaction import redact, redact_text
from scripts.collect.data_go_kr import DataGoKrClient

@pytest.mark.parametrize('message',[
 'HTTP 403 https://api.test/path?serviceKey=old%2Bkey%3D&month=202210',
 'HTTP 403 https%3A%2F%2Fapi.test%3FserviceKey%3Dold%252Bkey%253D%26month%3D202210',
 '{"serviceKey": "old-key", "month":"2022-10"}',
 "{'api_key': 'old-key', 'status': 'error'}",
])
def test_unrecognized_old_keys_are_removed_but_diagnostics_survive(message):
 result=redact_text(message)
 assert 'old' not in result and '[REDACTED]' in result
 assert '403' in result or '2022-10' in result or 'error' in result


def test_current_key_is_removed_in_raw_and_encoded_forms(monkeypatch):
 from urllib.parse import quote
 key='synthetic-key+/=never-real'
 monkeypatch.setenv('DATA_GO_KR_SERVICE_KEY',key)
 for text in (key,quote(key,safe=''),quote(quote(key,safe=''),safe='')):
  assert redact_text('failure '+text)=='failure [REDACTED]'


def test_recursive_report_and_private_key_redaction():
 value={'last_error':'403 for https://api.test/?serviceKey=old-key&month=202210',
        'nested':[{'private_key':'private content'}],'month':'2022-10','count':204}
 result=redact(value)
 assert 'old-key' not in json.dumps(result)
 assert result['nested'][0]['private_key']=='[REDACTED]'
 assert result['month']=='2022-10' and result['count']==204
 assert value['nested'][0]['private_key']=='private content'
 assert 'secret' not in redact_text('-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----')


@pytest.mark.parametrize('error_class',[requests.exceptions.HTTPError,requests.exceptions.ReadTimeout,requests.exceptions.ConnectionError])
def test_api_errors_do_not_expose_query_keys(monkeypatch,error_class):
 def get(*args,**kwargs): raise error_class('403 https://api.test/?serviceKey=old-key&month=202210')
 monkeypatch.setattr(requests,'get',get)
 client=DataGoKrClient(service_key='synthetic-current-key',max_retries=0)
 with pytest.raises(error_class) as error:client.get('https://api.test')
 assert 'old-key' not in str(error.value)
 assert '403' in str(error.value) and 'month=202210' in str(error.value)


def test_status_artifact_redacts_legacy_state(monkeypatch,tmp_path):
 from scripts import cloud_rollout
 monkeypatch.setattr(cloud_rollout,'STATUS_PATH',tmp_path/'status.json')
 payload=cloud_rollout.status_payload({'last_error':'HTTP 403 ?serviceKey=old-key&month=202210'})
 cloud_rollout.write_status(payload)
 text=(tmp_path/'status.json').read_text()
 assert 'old-key' not in text and '403' in text
