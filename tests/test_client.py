import base64

import httpx
import pytest
import respx

from sonar_mcp.client import SonarClient
from sonar_mcp.exceptions import (
    SonarAuthenticationError,
    SonarError,
    SonarPermissionError,
    SonarRateLimitError,
    SonarResourceNotFoundError,
    SonarValidationError,
)
from sonar_mcp.models import IssuesParams, QualityGateParams, QualityGateStatus

_DEFAULT_BASE = "https://sonarcloud.io/api"


# --- General Client Tests ---


async def test_requests_include_basic_auth_with_token_as_username() -> None:
    path = "qualitygates/project_status"
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{path}").mock(return_value=httpx.Response(200))
        async with SonarClient(token="my-token") as client:
            await client.get(path)
        expected = "Basic " + base64.b64encode(b"my-token:").decode()
        assert route.calls[0].request.headers["authorization"] == expected


async def test_default_base_url_routes_to_sonarcloud() -> None:
    path = "qualitygates/project_status"
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{path}").mock(return_value=httpx.Response(200))
        async with SonarClient(token="token") as client:
            await client.get(path)
        assert route.called


async def test_custom_base_url_is_used() -> None:
    custom = "https://custom.sonar.example/api"
    path = "qualitygates/project_status"
    async with respx.mock() as mock:
        route = mock.get(f"{custom}/{path}").mock(return_value=httpx.Response(200))
        async with SonarClient(token="token", base_url=custom) as client:
            await client.get(path)
        assert route.called


# --- Quality Gate Status Tests ---

_QUALITY_GATE_PATH = "qualitygates/project_status"
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
        route = mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
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
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(return_value=httpx.Response(401))
        async with SonarClient(token="bad-token") as client:
            with pytest.raises(SonarAuthenticationError):
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))


async def test_get_quality_gate_status_raises_on_404() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(return_value=httpx.Response(404))
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarResourceNotFoundError):
                await client.get_quality_gate_status(QualityGateParams(project_key="nonexistent"))


async def test_get_quality_gate_status_raises_on_400_with_message() -> None:
    payload = {"errors": [{"msg": "Project key is required"}]}
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(400, json=payload)
        )
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarValidationError) as exc:
                await client.get_quality_gate_status(QualityGateParams(project_key=""))
    assert "Project key is required" in str(exc.value)


async def test_get_quality_gate_status_raises_on_403() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarPermissionError) as exc:
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))
    assert "Permission denied" in str(exc.value)


async def test_get_quality_gate_status_raises_on_429() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(return_value=httpx.Response(429))
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarRateLimitError):
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))


async def test_get_quality_gate_status_raises_on_500() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(return_value=httpx.Response(500))
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarError) as exc:
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))
    assert "API request failed with status 500" in str(exc.value)


# --- Issues Tests ---

_ISSUES_PATH = "issues/search"
_ISSUE = {
    "key": "issue-1",
    "severity": "MAJOR",
    "type": "BUG",
    "status": "OPEN",
    "message": "Some bug",
    "component": "my-project:src/file.py",
    "rule": "python:S1234",
}


def _page(page_index: int, page_size: int, total: int, issues: list[dict]) -> dict:  # type: ignore[type-arg]
    return {
        "issues": issues,
        "paging": {"pageIndex": page_index, "pageSize": page_size, "total": total},
    }


async def test_get_issues_single_page_returns_all_issues() -> None:
    payload = _page(1, 500, 1, [_ISSUE])
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with SonarClient(token="token") as client:
            issues = await client.get_issues(IssuesParams(project_key="my-project"))
    assert len(issues) == 1
    assert issues[0].key == "issue-1"


async def test_get_issues_multi_page_fetches_all_pages_and_merges() -> None:
    issue_a = {**_ISSUE, "key": "issue-1"}
    issue_b = {**_ISSUE, "key": "issue-2"}
    pages = iter(
        [
            httpx.Response(200, json=_page(1, 1, 2, [issue_a])),
            httpx.Response(200, json=_page(2, 1, 2, [issue_b])),
        ]
    )
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(side_effect=lambda _req: next(pages))
        async with SonarClient(token="token") as client:
            issues = await client.get_issues(IssuesParams(project_key="my-project"))
    assert len(issues) == 2
    assert issues[0].key == "issue-1"
    assert issues[1].key == "issue-2"


async def test_get_issues_raises_on_401() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(return_value=httpx.Response(401))
        async with SonarClient(token="bad-token") as client:
            with pytest.raises(SonarAuthenticationError):
                await client.get_issues(IssuesParams(project_key="my-project"))


async def test_get_issues_raises_on_404() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(return_value=httpx.Response(404))
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarResourceNotFoundError):
                await client.get_issues(IssuesParams(project_key="nonexistent"))
