import base64

import httpx
import respx

from sonar_mcp.client import SonarClient

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
