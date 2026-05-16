import httpx
import pytest
import respx

from sonar_mcp.client import SonarClient
from sonar_mcp.models import IssuesParams

_BASE = "https://sonarcloud.io/api"
_PATH = f"{_BASE}/issues/search"

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
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=payload))
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
        mock.get(_PATH).mock(side_effect=lambda _req: next(pages))
        async with SonarClient(token="token") as client:
            issues = await client.get_issues(IssuesParams(project_key="my-project"))
    assert len(issues) == 2
    assert issues[0].key == "issue-1"
    assert issues[1].key == "issue-2"


async def test_get_issues_raises_on_401() -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(401))
        async with SonarClient(token="bad-token") as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_issues(IssuesParams(project_key="my-project"))


async def test_get_issues_raises_on_404() -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(404))
        async with SonarClient(token="token") as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_issues(IssuesParams(project_key="nonexistent"))
