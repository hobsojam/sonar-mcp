import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import Context

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


async def test_returns_ok_status_for_passing_gate(
    monkeypatch: pytest.MonkeyPatch,
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    monkeypatch.delenv("SONAR_DEFAULT_ORG", raising=False)
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_PASSING))
        result = await get_quality_gate("my-project", ctx=sonar_ctx)
    assert '"status": "OK"' in result
    assert '"url": "https://sonarcloud.io/dashboard?id=my-project"' in result


async def test_includes_org_in_url_if_provided(sonar_ctx: Context) -> None:  # type: ignore[type-arg]
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_PASSING))
        result = await get_quality_gate("my-project", organization="my-org", ctx=sonar_ctx)
    assert '"url": "https://sonarcloud.io/dashboard?id=my-project&org=my-org"' in result


async def test_condition_without_threshold_fields_is_parsed_successfully(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    payload = {
        "projectStatus": {
            "status": "OK",
            "conditions": [{"metricKey": "coverage", "status": "OK"}],
        }
    }
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=payload))
        result = await get_quality_gate("my-project", ctx=sonar_ctx)
    assert '"status": "OK"' in result
    assert '"metricKey": "coverage"' in result


async def test_returns_error_status_and_conditions_for_failing_gate(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_FAILING))
        result = await get_quality_gate("my-project", ctx=sonar_ctx)
    assert '"status": "ERROR"' in result
    assert '"metricKey": "coverage"' in result


async def test_falls_back_to_sonar_default_org(
    monkeypatch: pytest.MonkeyPatch,
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    monkeypatch.setenv("SONAR_DEFAULT_ORG", "my-org")
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_PASSING))
        await get_quality_gate("my-project", ctx=sonar_ctx)
    assert b"organization=my-org" in route.calls[0].request.url.query


async def test_returns_error_message_on_401(sonar_ctx: Context) -> None:  # type: ignore[type-arg]
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(401))
        result = await get_quality_gate("my-project", ctx=sonar_ctx)
    assert "Error retrieving quality gate status" in result
    assert "Authentication failed" in result


async def test_returns_error_message_on_404(sonar_ctx: Context) -> None:  # type: ignore[type-arg]
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(404, text="Project not found"))
        result = await get_quality_gate("nonexistent-project", ctx=sonar_ctx)
    assert "Error retrieving quality gate status" in result
    assert "Resource not found" in result


@pytest.mark.integration
async def test_get_quality_gate_returns_valid_json_with_status(
    integration_ctx: tuple[Context, str, str],  # type: ignore[type-arg]
) -> None:
    ctx, org, project = integration_ctx
    result = await get_quality_gate(project, org, ctx=ctx)
    assert result, "result must be a non-empty string"
    parsed = json.loads(result)
    assert "status" in parsed
