import httpx
import pytest
import respx

from sonar_mcp.client import SonarClient
from sonar_mcp.exceptions import SonarValidationError
from sonar_mcp.models import QualityGateParams, QualityGateStatus

_QG_PAYLOAD = {
    "projectStatus": {
        "status": "ERROR",
        "conditions": [
            {
                "metricKey": "coverage",
                "status": "ERROR",
                "actualValue": "82.4",
                "errorThreshold": "85",
            }
        ],
    }
}


async def test_retry_on_transport_error_then_success(monkeypatch):
    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    # prepare a client and fake _http.get to fail once then succeed
    async def failing_then_ok_get(url, params=None):
        # first call raises, second returns success
        if not hasattr(failing_then_ok_get, "count"):
            failing_then_ok_get.count = 0
        if failing_then_ok_get.count == 0:
            failing_then_ok_get.count += 1
            raise httpx.RequestError("transport error")
        return httpx.Response(200, json=_QG_PAYLOAD)

    async with SonarClient(token="t", max_retries=2, backoff_base=0.01) as client:
        monkeypatch.setattr(client._http, "get", failing_then_ok_get)
        events = []

        def metrics_hook(name, payload):
            events.append((name, payload))

        client._metrics_hook = metrics_hook

        res = await client.get_quality_gate_status(QualityGateParams(project_key="p"))

    assert res.status == QualityGateStatus.ERROR
    # ensure we attempted to sleep (i.e., retried)
    assert len(sleep_calls) >= 1
    # ensure metrics hook saw a retry_attempt
    assert any(e[0] == "retry_attempt" for e in events)


@respx.mock
async def test_retry_on_429_respects_retry_after(monkeypatch):
    # create two responses: 429 with Retry-After then 200
    path = "qualitygates/project_status"
    pages = iter(
        [
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json=_QG_PAYLOAD),
        ]
    )

    route = respx.get(f"https://sonarcloud.io/api/{path}").mock(side_effect=lambda req: next(pages))

    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    events = []

    def metrics_hook(name, payload):
        events.append((name, payload))

    async with SonarClient(token="t", max_retries=2, backoff_base=0.01) as client:
        client._metrics_hook = metrics_hook
        res = await client.get_quality_gate_status(QualityGateParams(project_key="p"))

    assert res.status == QualityGateStatus.ERROR
    # Retry-After should have caused a sleep of ~1 second
    assert any(abs(d - 1) < 0.001 or d >= 1 for d in sleep_calls)
    assert any(e[0] == "retry_attempt" for e in events)
    assert route.called


@respx.mock
async def test_no_retry_on_400_returns_validation_error():
    path = "qualitygates/project_status"
    payload = {"errors": [{"msg": "Project key is required"}]}
    respx.get(f"https://sonarcloud.io/api/{path}").mock(
        return_value=httpx.Response(400, json=payload)
    )

    async with SonarClient(token="t", max_retries=2) as client:
        with pytest.raises(SonarValidationError):
            await client.get_quality_gate_status(QualityGateParams(project_key=""))
