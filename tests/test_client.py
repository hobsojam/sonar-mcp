import base64

import httpx
import pytest
import respx

from sonar_mcp.client import SonarClient
from sonar_mcp.models import QualityGateParams, QualityGateStatus

_DEFAULT_BASE = "https://sonarcloud.io/api"
_PATH = "qualitygates/project_status"


async def test_requests_include_basic_auth_with_token_as_username() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_PATH}").mock(return_value=httpx.Response(200))
        async with SonarClient(token="my-token") as client:
            await client.get(_PATH)
        expected = "Basic " + base64.b64encode(b"my-token:").decode()
        assert route.calls[0].request.headers["authorization"] == expected


async def test_default_base_url_routes_to_sonarcloud() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_PATH}").mock(return_value=httpx.Response(200))
        async with SonarClient(token="token") as client:
            await client.get(_PATH)
        assert route.called


async def test_custom_base_url_is_used() -> None:
    custom = "https://custom.sonar.example/api"
    async with respx.mock() as mock:
        route = mock.get(f"{custom}/{_PATH}").mock(return_value=httpx.Response(200))
        async with SonarClient(token="token", base_url=custom) as client:
            await client.get(_PATH)
        assert route.called


_QUALITY_GATE_PAYLOAD = {
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


async def test_get_quality_gate_status_returns_parsed_status() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_PATH}").mock(
            return_value=httpx.Response(200, json=_QUALITY_GATE_PAYLOAD)
        )
        async with SonarClient(token="token") as client:
            result = await client.get_quality_gate_status(
                QualityGateParams(project_key="my-project", organization="my-org")
            )
        request = route.calls[0].request
        assert b"projectKey=my-project" in request.url.query
        assert b"organization=my-org" in request.url.query
    assert result.status == QualityGateStatus.ERROR
    assert len(result.conditions) == 1
    assert result.conditions[0].metricKey == "coverage"


async def test_get_quality_gate_status_raises_on_401() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_PATH}").mock(return_value=httpx.Response(401))
        async with SonarClient(token="bad-token") as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))


async def test_get_quality_gate_status_raises_on_404() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_PATH}").mock(return_value=httpx.Response(404))
        async with SonarClient(token="token") as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_quality_gate_status(QualityGateParams(project_key="nonexistent"))
