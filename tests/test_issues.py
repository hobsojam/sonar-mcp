import json
import os

import httpx
import pytest
import respx
from mcp.server.fastmcp import Context

from sonar_mcp.models import IssueSeverity, IssueStatus, IssueType
from sonar_mcp.tools.issues import get_issue_summary, get_issues

_PATH = "https://sonarcloud.io/api/issues/search"

_ISSUE = {
    "key": "issue-1",
    "severity": "MAJOR",
    "type": "BUG",
    "status": "OPEN",
    "message": "Some bug",
    "component": "my-project:src/file.py",
    "rule": "python:S1234",
}


def _page(issues: list[dict], total: int | None = None) -> dict:  # type: ignore[type-arg]
    return {
        "issues": issues,
        "paging": {"pageIndex": 1, "pageSize": 500, "total": total or len(issues)},
    }


# --- get_issues ---


async def test_get_issues_returns_all_issues_with_no_filters(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        result = await get_issues("my-project", ctx=sonar_ctx)
    issues = json.loads(result)
    assert len(issues) == 1
    assert issues[0]["key"] == "issue-1"
    expected_url = "https://sonarcloud.io/project/issues?id=my-project&issues=issue-1&open=issue-1"
    assert issues[0]["url"] == expected_url


async def test_get_issues_includes_org_in_url(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        result = await get_issues("my-project", organization="my-org", ctx=sonar_ctx)
    issues = json.loads(result)
    assert "org=my-org" in issues[0]["url"]


async def test_get_issues_severity_filter_is_passed_to_api(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        await get_issues("my-project", severity=IssueSeverity.MAJOR, ctx=sonar_ctx)
    assert b"severities=MAJOR" in route.calls[0].request.url.query


async def test_get_issues_type_filter_is_passed_to_api(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        await get_issues("my-project", issue_type=IssueType.BUG, ctx=sonar_ctx)
    assert b"types=BUG" in route.calls[0].request.url.query


async def test_get_issues_status_filter_is_passed_to_api(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        await get_issues("my-project", status=IssueStatus.CONFIRMED, ctx=sonar_ctx)
    assert b"statuses=CONFIRMED" in route.calls[0].request.url.query


async def test_get_issues_falls_back_to_sonar_default_org(
    monkeypatch: pytest.MonkeyPatch,
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    monkeypatch.setenv("SONAR_DEFAULT_ORG", "my-org")
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        await get_issues("my-project", ctx=sonar_ctx)
    assert b"organization=my-org" in route.calls[0].request.url.query


async def test_get_issues_returns_empty_list_when_no_issues(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([])))
        result = await get_issues("my-project", ctx=sonar_ctx)
    assert json.loads(result) == []


async def test_get_issues_returns_error_on_401(sonar_ctx: Context) -> None:  # type: ignore[type-arg]
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(401))
        result = await get_issues("my-project", ctx=sonar_ctx)
    assert "Error retrieving issues" in result
    assert "Authentication failed" in result


async def test_get_issues_returns_error_on_404(sonar_ctx: Context) -> None:  # type: ignore[type-arg]
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(404, text="Project not found"))
        result = await get_issues("nonexistent-project", ctx=sonar_ctx)
    assert "Error retrieving issues" in result
    assert "Resource not found" in result


# --- get_issue_summary ---


_MIXED_ISSUES = [
    {**_ISSUE, "key": "a", "severity": "BLOCKER", "type": "BUG"},
    {**_ISSUE, "key": "b", "severity": "BLOCKER", "type": "VULNERABILITY"},
    {**_ISSUE, "key": "c", "severity": "MAJOR", "type": "CODE_SMELL"},
]


async def test_summary_returns_correct_counts_by_severity(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page(_MIXED_ISSUES)))
        result = await get_issue_summary("my-project", ctx=sonar_ctx)
    counts = json.loads(result)
    assert counts["by_severity"]["BLOCKER"] == 2
    assert counts["by_severity"]["MAJOR"] == 1
    assert counts["by_severity"]["CRITICAL"] == 0
    assert counts["url"] == "https://sonarcloud.io/project/issues?id=my-project&resolved=false"


async def test_summary_includes_org_in_url(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([])))
        result = await get_issue_summary("my-project", organization="my-org", ctx=sonar_ctx)
    counts = json.loads(result)
    assert "org=my-org" in counts["url"]


async def test_summary_returns_correct_counts_by_type(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page(_MIXED_ISSUES)))
        result = await get_issue_summary("my-project", ctx=sonar_ctx)
    counts = json.loads(result)
    assert counts["by_type"]["BUG"] == 1
    assert counts["by_type"]["VULNERABILITY"] == 1
    assert counts["by_type"]["CODE_SMELL"] == 1


async def test_summary_returns_zero_counts_when_no_issues(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([])))
        result = await get_issue_summary("my-project", ctx=sonar_ctx)
    counts = json.loads(result)
    assert all(v == 0 for v in counts["by_severity"].values())
    assert all(v == 0 for v in counts["by_type"].values())


async def test_summary_passes_all_unresolved_statuses_to_api(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([])))
        await get_issue_summary("my-project", ctx=sonar_ctx)
    query = route.calls[0].request.url.query
    assert b"OPEN" in query
    assert b"CONFIRMED" in query
    assert b"REOPENED" in query


async def test_summary_falls_back_to_sonar_default_org(
    monkeypatch: pytest.MonkeyPatch,
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    monkeypatch.setenv("SONAR_DEFAULT_ORG", "my-org")
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([])))
        await get_issue_summary("my-project", ctx=sonar_ctx)
    assert b"organization=my-org" in route.calls[0].request.url.query


async def test_summary_returns_error_on_401(sonar_ctx: Context) -> None:  # type: ignore[type-arg]
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(401))
        result = await get_issue_summary("my-project", ctx=sonar_ctx)
    assert "Error retrieving issue summary" in result
    assert "Authentication failed" in result


# --- integration tests ---


def _make_integration_ctx() -> tuple[str, str, str] | None:
    token = os.environ.get("SONAR_TOKEN", "")
    org = os.environ.get("SONAR_DEFAULT_ORG", "")
    project = os.environ.get("SONAR_DEFAULT_PROJECT", "")
    if not all([token, org, project]):
        return None
    return token, org, project


@pytest.mark.integration
async def test_integration_get_issues_returns_list() -> None:
    from unittest.mock import MagicMock

    from mcp.server.fastmcp.server import RequestContext

    from sonar_mcp.client import SonarClient

    creds = _make_integration_ctx()
    if not creds:
        pytest.skip("SONAR_TOKEN, SONAR_DEFAULT_ORG, SONAR_DEFAULT_PROJECT required")
    token, org, project = creds
    async with SonarClient(token=token) as client:
        rc: RequestContext = RequestContext(  # type: ignore[type-arg]
            request_id="test", meta=None, session=MagicMock(), lifespan_context=client
        )
        ctx = Context(request_context=rc, fastmcp=MagicMock())
        result = await get_issues(project, organization=org, ctx=ctx)
    assert isinstance(json.loads(result), list)


@pytest.mark.integration
async def test_integration_get_issues_with_severity_filter() -> None:
    from unittest.mock import MagicMock

    from mcp.server.fastmcp.server import RequestContext

    from sonar_mcp.client import SonarClient

    creds = _make_integration_ctx()
    if not creds:
        pytest.skip("SONAR_TOKEN, SONAR_DEFAULT_ORG, SONAR_DEFAULT_PROJECT required")
    token, org, project = creds
    async with SonarClient(token=token) as client:
        rc: RequestContext = RequestContext(  # type: ignore[type-arg]
            request_id="test", meta=None, session=MagicMock(), lifespan_context=client
        )
        ctx = Context(request_context=rc, fastmcp=MagicMock())
        result = await get_issues(
            project, organization=org, severity=IssueSeverity.BLOCKER, ctx=ctx
        )
    issues = json.loads(result)
    assert all(i["severity"] == "BLOCKER" for i in issues)


@pytest.mark.integration
async def test_integration_get_issue_summary_has_valid_counts() -> None:
    from unittest.mock import MagicMock

    from mcp.server.fastmcp.server import RequestContext

    from sonar_mcp.client import SonarClient

    creds = _make_integration_ctx()
    if not creds:
        pytest.skip("SONAR_TOKEN, SONAR_DEFAULT_ORG, SONAR_DEFAULT_PROJECT required")
    token, org, project = creds
    async with SonarClient(token=token) as client:
        rc: RequestContext = RequestContext(  # type: ignore[type-arg]
            request_id="test", meta=None, session=MagicMock(), lifespan_context=client
        )
        ctx = Context(request_context=rc, fastmcp=MagicMock())
        result = await get_issue_summary(project, organization=org, ctx=ctx)
    summary = json.loads(result)
    assert all(v >= 0 for v in summary["by_severity"].values())
    assert all(v >= 0 for v in summary["by_type"].values())
    assert sum(summary["by_severity"].values()) == sum(summary["by_type"].values())
