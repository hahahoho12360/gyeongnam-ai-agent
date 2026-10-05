from __future__ import annotations

import os
import time
import requests
import xml.etree.ElementTree as ET
from typing import Any, Iterable


class DataGoKrClient:
    """data.go.kr 공통 REST client.

    JSON/XML 양쪽을 수용하고, 서비스키 인코딩 차이와 페이지네이션을 한 곳에서 처리한다.
    개별 API의 업무 의미/필드명 변환은 adapters.py가 담당한다.
    """

    def __init__(
        self,
        service_key: str | None = None,
        timeout: int = 60,
        pause_seconds: float = 0.05,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.5,
    ):
        self.key = service_key or os.getenv('DATA_GO_KR_SERVICE_KEY', '')
        self.timeout = timeout
        self.pause_seconds = pause_seconds
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        if not self.key:
            raise RuntimeError('DATA_GO_KR_SERVICE_KEY가 없습니다. 공공데이터포털에서 활용신청 후 .env에 넣으세요.')

    @staticmethod
    def _xml_to_dict(text: str) -> dict[str, Any]:
        root = ET.fromstring(text)

        def node_value(node: ET.Element) -> Any:
            children = list(node)
            if not children:
                return (node.text or '').strip()
            out: dict[str, Any] = {}
            for child in children:
                value = node_value(child)
                if child.tag in out:
                    if not isinstance(out[child.tag], list):
                        out[child.tag] = [out[child.tag]]
                    out[child.tag].append(value)
                else:
                    out[child.tag] = value
            return out

        return {root.tag: node_value(root)}

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        json_hint: bool = True,
        add_paging: bool = True,
    ) -> dict:
        incoming = dict(params or {})
        p: dict[str, Any] = {'serviceKey': self.key}
        if add_paging:
            p.update({'pageNo': 1, 'numOfRows': 1000})
        if json_hint and '_type' not in incoming and 'type' not in incoming:
            # API에 따라 _type / type 중 하나만 인식한다. 호출부가 type을 명시하면 중복 전송하지 않는다.
            p['_type'] = 'json'
        p.update(incoming)
        # 공공데이터포털은 간헐적으로 응답이 느려지거나 5xx/429가 발생할 수 있다.
        # 400/401/403 같은 요청/권한 오류는 재시도해도 해결되지 않으므로 즉시 실패시키고,
        # timeout/연결오류/429/5xx만 지수형 backoff로 제한 재시도한다.
        last_exc: Exception | None = None
        response = None
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.get(url, params=p, timeout=self.timeout)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    wait = self.retry_backoff_seconds * (2 ** attempt)
                    print(f'    data.go.kr 일시 오류 HTTP {response.status_code}; {wait:.1f}초 후 재시도 {attempt + 1}/{self.max_retries}')
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                break
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise
                wait = self.retry_backoff_seconds * (2 ** attempt)
                print(f'    data.go.kr 응답 지연/연결 오류; {wait:.1f}초 후 재시도 {attempt + 1}/{self.max_retries}')
                time.sleep(wait)
        if response is None:
            if last_exc:
                raise last_exc
            raise RuntimeError('공공데이터포털 응답을 받지 못했습니다.')
        ctype = response.headers.get('content-type', '')

        try:
            payload = response.json()
        except Exception:
            try:
                payload = self._xml_to_dict(response.text)
            except Exception:
                payload = {'_raw': response.text, '_content_type': ctype}

        # 공공데이터포털의 인증/게이트웨이 오류가 HTTP 200 XML/JSON으로 오는 경우를 명시화한다.
        error = self.error_message(payload)
        if error:
            # data.go.kr의 NODATA_ERROR는 인증/서버 실패가 아니라 '조회 결과 0건'이다.
            # 수집 파이프라인이 빈 rows를 정상적으로 처리하도록 예외를 발생시키지 않는다.
            if not self.is_no_data_error(error):
                raise RuntimeError(error)
        return payload

    @staticmethod
    def is_no_data_error(error: str | Exception) -> bool:
        text = str(error or '').upper()
        return 'NODATA_ERROR' in text or 'NO DATA' in text or 'NO_DATA' in text

    @staticmethod
    def error_message(payload: dict) -> str | None:
        # OpenAPI_ServiceResponse / header.resultCode / response.header.resultCode 모두 지원
        if not isinstance(payload, dict):
            return None
        oas = payload.get('OpenAPI_ServiceResponse') or payload.get('openAPI_ServiceResponse')
        if isinstance(oas, dict):
            h = oas.get('cmmMsgHeader') or {}
            code = h.get('returnReasonCode') or h.get('errMsg')
            if code:
                return f"공공데이터포털 API 오류: {h}"
        response_lower = payload.get('response') if isinstance(payload.get('response'), dict) else None
        response_upper = payload.get('Response') if isinstance(payload.get('Response'), dict) else None
        for header in (
            payload.get('header'), payload.get('head'),
            response_lower.get('header') if response_lower else None,
            response_lower.get('head') if response_lower else None,
            response_upper.get('header') if response_upper else None,
            response_upper.get('head') if response_upper else None,
        ):
            if isinstance(header, dict):
                code = str(header.get('resultCode') or header.get('resultCd') or '00')
                msg = header.get('resultMsg') or header.get('resultMessage') or ''
                if code not in {'00', '0', '000', '0000', 'NORMAL_CODE'}:
                    return f'공공데이터포털 API 오류 {code}: {msg}'
        return None

    @staticmethod
    def _unwrap(payload: dict) -> tuple[Any, int | None]:
        """items container와 totalCount를 가능한 응답 봉투에서 꺼낸다."""
        if not isinstance(payload, dict):
            return [], None

        # 공공데이터포털에는 response/Response, header/head, body 생략형 등 여러 봉투가 존재한다.
        if isinstance(payload.get('response'), dict):
            response = payload.get('response')
        elif isinstance(payload.get('Response'), dict):
            response = payload.get('Response')
        else:
            response = payload

        body = response.get('body') if isinstance(response, dict) else None
        if body is None and isinstance(payload.get('body'), dict):
            body = payload.get('body')
        # 주민등록 법정동 API처럼 <Response><head>...<items>...</items></Response>인 경우
        if body is None and isinstance(response, dict):
            body = response
        if body is None:
            body = {}

        total = body.get('totalCount') if isinstance(body, dict) else None
        if total in (None, '') and isinstance(response, dict):
            head = response.get('head') or response.get('header') or {}
            if isinstance(head, dict):
                total = head.get('totalCount')
        try:
            total_int = int(str(total).replace(',', '')) if total not in (None, '') else None
        except (TypeError, ValueError):
            total_int = None

        items = body.get('items') if isinstance(body, dict) else None
        if items is None and isinstance(body, dict) and 'item' in body:
            # 일부 API(공동주택 기본정보 등)는 <body><item>...</item></body> 구조다.
            items = body.get('item')
        if items is None:
            # 일부 API는 root/body 없이 items를 둔다.
            items = payload.get('items') or payload.get('item') or []
        return items, total_int

    @classmethod
    def items(cls, payload: dict) -> list[dict]:
        items, _ = cls._unwrap(payload)
        if isinstance(items, dict):
            # XML: <items><item>...</item></items>
            items = items.get('item', items)
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return []
        return [x for x in items if isinstance(x, dict)]

    @classmethod
    def total_count(cls, payload: dict) -> int | None:
        return cls._unwrap(payload)[1]

    def iter_pages(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        page_size: int = 1000,
        max_pages: int = 1000,
        json_hint: bool = True,
    ) -> Iterable[list[dict]]:
        base = dict(params or {})
        page = 1
        emitted = 0
        while page <= max_pages:
            p = {**base, 'pageNo': page, 'numOfRows': page_size}
            payload = self.get(url, p, json_hint=json_hint)
            rows = self.items(payload)
            total = self.total_count(payload)
            yield rows
            emitted += len(rows)
            if not rows:
                break
            if total is not None and emitted >= total:
                break
            if len(rows) < page_size and total is None:
                break
            page += 1
            if self.pause_seconds:
                time.sleep(self.pause_seconds)

    def get_all(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        page_size: int = 1000,
        max_pages: int = 1000,
        json_hint: bool = True,
    ) -> list[dict]:
        out: list[dict] = []
        for rows in self.iter_pages(url, params, page_size=page_size, max_pages=max_pages, json_hint=json_hint):
            out.extend(rows)
        return out
