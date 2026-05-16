import json

import httpx
import pytest
import respx

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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        result = await get_issues("my-project")
    issues = json.loads(result)
    assert len(issues) == 1
    assert issues[0]["key"] == "issue-1"


async def test_get_issues_severity_filter_is_passed_to_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        await get_issues("my-project", severity=IssueSeverity.MAJOR)
    assert b"severities=MAJOR" in route.calls[0].request.url.query


async def test_get_issues_type_filter_is_passed_to_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        await get_issues("my-project", type=IssueType.BUG)
    assert b"types=BUG" in route.calls[0].request.url.query


async def test_get_issues_status_filter_is_passed_to_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        await get_issues("my-project", status=IssueStatus.OPEN)
    assert b"statuses=OPEN" in route.calls[0].request.url.query


async def test_get_issues_falls_back_to_sonar_default_org(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    monkeypatch.setenv("SONAR_DEFAULT_ORG", "my-org")
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_ISSUE])))
        await get_issues("my-project")
    assert b"organization=my-org" in route.calls[0].request.url.query


async def test_get_issues_returns_empty_list_when_no_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([])))
        result = await get_issues("my-project")
    assert json.loads(result) == []


async def test_get_issues_raises_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "bad-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            await get_issues("my-project")


async def test_get_issues_raises_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await get_issues("nonexistent-project")


# --- get_issue_summary ---


_MIXED_ISSUES = [
    {**_ISSUE, "key": "a", "severity": "BLOCKER", "type": "BUG"},
    {**_ISSUE, "key": "b", "severity": "BLOCKER", "type": "VULNERABILITY"},
    {**_ISSUE, "key": "c", "severity": "MAJOR", "type": "CODE_SMELL"},
]


async def test_summary_returns_correct_counts_by_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page(_MIXED_ISSUES)))
        result = await get_issue_summary("my-project")
    counts = json.loads(result)
    assert counts["by_severity"]["BLOCKER"] == 2
    assert counts["by_severity"]["MAJOR"] == 1
    assert counts["by_severity"]["CRITICAL"] == 0


async def test_summary_returns_correct_counts_by_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page(_MIXED_ISSUES)))
        result = await get_issue_summary("my-project")
    counts = json.loads(result)
    assert counts["by_type"]["BUG"] == 1
    assert counts["by_type"]["VULNERABILITY"] == 1
    assert counts["by_type"]["CODE_SMELL"] == 1


async def test_summary_returns_zero_counts_when_no_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([])))
        result = await get_issue_summary("my-project")
    counts = json.loads(result)
    assert all(v == 0 for v in counts["by_severity"].values())
    assert all(v == 0 for v in counts["by_type"].values())


async def test_summary_falls_back_to_sonar_default_org(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    monkeypatch.setenv("SONAR_DEFAULT_ORG", "my-org")
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([])))
        await get_issue_summary("my-project")
    assert b"organization=my-org" in route.calls[0].request.url.query


async def test_summary_propagates_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "bad-token")
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            await get_issue_summary("my-project")
