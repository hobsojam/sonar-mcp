import json
import os

import httpx
import pytest
import respx

from sonar_mcp.tools.quality_gate import get_quality_gate

_PATH = "https://sonarcloud.io/api/qualitygates/project_status"

_PASSING = {"projectStatus": {"status": "OK", "conditions": []}}
_FAILING = {
    "projectStatus": {
        "status": "ERROR",
        "conditions": [
            {
                "metricKey": "coverage",
                "status": "ERROR",
                "actualValue": "72.4",
                "errorThreshold": "80",
            }
        ],
    }
}


async def test_returns_ok_status_for_passing_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_PASSING))
        result = await get_quality_gate("my-project")
    assert '"status": "OK"' in result


async def test_returns_error_status_and_conditions_for_failing_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_FAILING))
        result = await get_quality_gate("my-project")
    assert '"status": "ERROR"' in result
    assert '"metricKey": "coverage"' in result


async def test_falls_back_to_sonar_default_org(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    monkeypatch.setenv("SONAR_DEFAULT_ORG", "my-org")
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_PASSING))
        await get_quality_gate("my-project")
    assert b"organization=my-org" in route.calls[0].request.url.query


async def test_raises_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "bad-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            await get_quality_gate("my-project")


async def test_raises_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await get_quality_gate("nonexistent-project")


@pytest.mark.integration
async def test_get_quality_gate_returns_valid_json_with_status() -> None:
    token = os.environ.get("SONAR_TOKEN")
    organization = os.environ.get("SONAR_DEFAULT_ORG")
    project_key = os.environ.get("SONAR_DEFAULT_PROJECT")

    if not token or not organization or not project_key:
        pytest.skip("SONAR_TOKEN, SONAR_DEFAULT_ORG, and SONAR_DEFAULT_PROJECT must be set")

    result = await get_quality_gate(project_key, organization)

    assert result, "result must be a non-empty string"
    parsed = json.loads(result)
    assert "status" in parsed
