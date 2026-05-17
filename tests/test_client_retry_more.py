import time

import httpx
import pytest
import respx

from sonar_mcp.client import SonarClient
from sonar_mcp.exceptions import SonarError
from sonar_mcp.models import QualityGateParams


async def test_give_up_after_max_retries_transport_error(monkeypatch):
    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    async def always_fail_get(url, params=None):
        raise httpx.RequestError("transport error")

    events = []

    def metrics_hook(name, payload):
        events.append((name, payload))

    async with SonarClient(token="t", max_retries=2, backoff_base=0.01) as client:
        monkeypatch.setattr(client._http, "get", always_fail_get)
        client._metrics_hook = metrics_hook

        with pytest.raises(httpx.RequestError):
            await client.get_quality_gate_status(QualityGateParams(project_key="p"))

    # We should have slept for each retry attempt
    assert len(sleep_calls) >= 2
    # metrics should include retry_attempt events and a give_up
    assert any(e[0] == "retry_attempt" for e in events)
    assert any(e[0] == "retry_give_up" for e in events)


@respx.mock
async def test_server_error_retries_and_raises(monkeypatch):
    path = "qualitygates/project_status"
    # three 500 responses; with max_retries=2 client should retry twice then return final 500
    pages = iter(
        [
            httpx.Response(500, text="server error a"),
            httpx.Response(500, text="server error b"),
            httpx.Response(500, text="server error c"),
        ]
    )

    respx.get(f"https://sonarcloud.io/api/{path}").mock(side_effect=lambda req: next(pages))

    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    events = []

    def metrics_hook(name, payload):
        events.append((name, payload))

    async with SonarClient(token="t", max_retries=2, backoff_base=0.01) as client:
        client._metrics_hook = metrics_hook
        with pytest.raises(SonarError):
            await client.get_quality_gate_status(QualityGateParams(project_key="p"))

    # Should have retried (slept) twice
    assert len(sleep_calls) >= 2
    # metrics should include retry_attempts for server_error
    assert sum(1 for e in events if e[0] == "retry_attempt") >= 2


@respx.mock
async def test_retry_after_http_date_parsed(monkeypatch):
    path = "qualitygates/project_status"
    # build an HTTP-date string ~2 seconds in the future
    date_str = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time() + 2))

    pages = iter(
        [
            httpx.Response(429, headers={"Retry-After": date_str}),
            httpx.Response(200, json={"projectStatus": {"status": "OK", "conditions": []}}),
        ]
    )

    respx.get(f"https://sonarcloud.io/api/{path}").mock(side_effect=lambda req: next(pages))

    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    async with SonarClient(token="t", max_retries=2, backoff_base=0.01) as client:
        res = await client.get_quality_gate_status(QualityGateParams(project_key="p"))

    # Ensure we observed a sleep reflective of Retry-After (allow jitter); expect at least ~1.5s
    assert sleep_calls, "expected sleep_calls to be populated"
    assert any(d >= 1.5 for d in sleep_calls)
    # result should indicate OK status
    assert str(res.status) == "OK"


async def test_metrics_hook_called_on_give_up_transport(monkeypatch):
    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    async def always_fail_get(url, params=None):
        raise httpx.RequestError("transport error")

    events = []

    def metrics_hook(name, payload):
        events.append((name, payload))

    async with SonarClient(token="t", max_retries=1, backoff_base=0.01) as client:
        monkeypatch.setattr(client._http, "get", always_fail_get)
        client._metrics_hook = metrics_hook

        with pytest.raises(httpx.RequestError):
            await client.get_quality_gate_status(QualityGateParams(project_key="p"))

    # One retry attempt and then give_up
    assert any(e[0] == "retry_attempt" for e in events)
    assert any(e[0] == "retry_give_up" for e in events)
    assert len(sleep_calls) >= 1
