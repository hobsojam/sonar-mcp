import json

import httpx
import respx
from mcp.server.fastmcp import Context

from sonar_mcp.tools.projects import list_projects

_PATH = "https://sonarcloud.io/api/projects/search"

_PROJECT = {
    "key": "my-project",
    "name": "My Project",
    "organization": "my-org",
    "visibility": "public",
}


def _page(components: list[dict]) -> dict:  # type: ignore[type-arg]
    return {
        "paging": {"pageIndex": 1, "pageSize": 100, "total": len(components)},
        "components": components,
    }


async def test_list_projects_returns_formatted_list(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([_PROJECT])))
        result = await list_projects(organization="my-org", ctx=sonar_ctx)
    projects = json.loads(result)
    assert len(projects) == 1
    assert projects[0]["key"] == "my-project"
    assert projects[0]["url"] == "https://sonarcloud.io/dashboard?id=my-project&org=my-org"


async def test_list_projects_includes_query_param(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        route = mock.get(_PATH).mock(return_value=httpx.Response(200, json=_page([])))
        await list_projects(query="my-query", ctx=sonar_ctx)
    assert b"q=my-query" in route.calls[0].request.url.query


async def test_list_projects_returns_error_on_401(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(401))
        result = await list_projects(organization="my-org", ctx=sonar_ctx)
    assert "Error listing projects" in result
    assert "Authentication failed" in result


async def test_list_projects_returns_error_on_403(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(403, text="Forbidden"))
        result = await list_projects(organization="my-org", ctx=sonar_ctx)
    assert "Error listing projects" in result
    assert "Permission denied" in result


async def test_list_projects_returns_error_on_404(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    async with respx.mock() as mock:
        mock.get(_PATH).mock(return_value=httpx.Response(404, text="Organization not found"))
        result = await list_projects(organization="nonexistent-org", ctx=sonar_ctx)
    assert "Error listing projects" in result
    assert "Resource not found" in result


_PROJECT_A = {
    "key": "project-a",
    "name": "Project A",
    "organization": "my-org",
    "visibility": "public",
}

_PROJECT_B = {
    "key": "project-b",
    "name": "Project B",
    "organization": "my-org",
    "visibility": "private",
}


async def test_list_projects_returns_all_projects_across_multiple_pages(
    sonar_ctx: Context,  # type: ignore[type-arg]
) -> None:
    page1 = {
        "paging": {"pageIndex": 1, "pageSize": 500, "total": 2},
        "components": [_PROJECT_A],
    }
    page2 = {
        "paging": {"pageIndex": 2, "pageSize": 500, "total": 2},
        "components": [_PROJECT_B],
    }
    async with respx.mock() as mock:
        mock.get(_PATH).mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )
        result = await list_projects(organization="my-org", ctx=sonar_ctx)
    projects = json.loads(result)
    assert len(projects) == 2
    keys = {p["key"] for p in projects}
    assert keys == {"project-a", "project-b"}
