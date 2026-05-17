"""Component tests exercising the full MCP protocol stack in-process.

These tests wire a ClientSession directly to the FastMCP server via anyio
memory streams and mock SonarCloud HTTP at the boundary with respx.  They
verify that the JSON Schema generated from function signatures is correct,
that incoming JSON-RPC tool calls are routed properly, and that return values
are serialised into valid MCP result payloads.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import anyio
import httpx
import pytest
import respx
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.shared.message import SessionMessage
from mcp.types import CallToolResult, ListToolsResult

from sonar_mcp.__main__ import server

_QUALITY_GATE_URL = "https://sonarcloud.io/api/qualitygates/project_status"
_ISSUES_URL = "https://sonarcloud.io/api/issues/search"
_PROJECTS_URL = "https://sonarcloud.io/api/projects/search"

_PASSING_GATE = {"projectStatus": {"status": "OK", "conditions": []}}
_ISSUES_PAGE = {
    "issues": [
        {
            "key": "ISSUE-1",
            "severity": "MAJOR",
            "type": "BUG",
            "status": "OPEN",
            "message": "Something is wrong",
            "component": "my-project:src/foo.py",
            "rule": "python:S1234",
        }
    ],
    "paging": {"pageIndex": 1, "pageSize": 500, "total": 1},
}
_PROJECTS_PAGE = {
    "paging": {"pageIndex": 1, "pageSize": 500, "total": 1},
    "components": [
        {
            "key": "my-project",
            "name": "My Project",
            "organization": "my-org",
            "visibility": "public",
        }
    ],
}


@asynccontextmanager
async def _connected_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[tuple[ClientSession, respx.MockRouter], None]:
    """Yield a (ClientSession, respx.MockRouter) wired in-process to the server.

    The respx mock is activated before the server task group starts so that the
    server task inherits the patched context and all HTTP calls from tool
    handlers are intercepted correctly.

    The server lifespan reads SONAR_TOKEN from the environment, so we set a
    placeholder token before starting.
    """
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    monkeypatch.delenv("SONAR_DEFAULT_ORG", raising=False)
    monkeypatch.delenv("SONAR_DEFAULT_PROJECT", raising=False)

    # Two pairs of memory streams connect client and server.
    # client_read  ← server writes → server_write
    # server_read  ← client writes → client_write
    client_read: MemoryObjectReceiveStream[SessionMessage | Exception]
    client_write: MemoryObjectSendStream[SessionMessage]
    server_read: MemoryObjectReceiveStream[SessionMessage | Exception]
    server_write: MemoryObjectSendStream[SessionMessage]

    server_write, client_read = anyio.create_memory_object_stream(32)
    client_write, server_read = anyio.create_memory_object_stream(32)

    init_opts = server._mcp_server.create_initialization_options()

    # Activate respx before starting the server task so the task inherits the
    # patched async context and intercepts HTTP calls made inside tool handlers.
    async with respx.mock(assert_all_called=False) as mock_router:
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                server._mcp_server.run,
                server_read,
                server_write,
                init_opts,
            )

            async with ClientSession(client_read, client_write) as session:
                await session.initialize()
                yield session, mock_router

            tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------


async def test_tools_list_returns_all_four_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, _):
        result: ListToolsResult = await session.list_tools()

    tool_names = {t.name for t in result.tools}
    assert tool_names == {"get_quality_gate", "get_issues", "get_issue_summary", "list_projects"}


async def test_get_quality_gate_schema_has_expected_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, _):
        result: ListToolsResult = await session.list_tools()

    tool = next(t for t in result.tools if t.name == "get_quality_gate")
    props = tool.inputSchema.get("properties", {})
    assert "project_key" in props
    assert "organization" in props


async def test_get_issues_schema_has_expected_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, _):
        result: ListToolsResult = await session.list_tools()

    tool = next(t for t in result.tools if t.name == "get_issues")
    props = tool.inputSchema.get("properties", {})
    assert "project_key" in props
    assert "organization" in props
    assert "severity" in props
    assert "issue_type" in props
    assert "status" in props


async def test_list_projects_schema_has_expected_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, _):
        result: ListToolsResult = await session.list_tools()

    tool = next(t for t in result.tools if t.name == "list_projects")
    props = tool.inputSchema.get("properties", {})
    assert "organization" in props
    assert "query" in props


async def test_get_issue_summary_schema_has_only_project_and_org_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_issue_summary accepts project_key and organization only, not filter params."""
    async with _connected_client(monkeypatch) as (session, _):
        result: ListToolsResult = await session.list_tools()

    summary_tool = next(t for t in result.tools if t.name == "get_issue_summary")
    props = summary_tool.inputSchema.get("properties", {})
    assert "project_key" in props
    assert "organization" in props
    assert "severity" not in props
    assert "issue_type" not in props


# ---------------------------------------------------------------------------
# tools/call happy paths
# ---------------------------------------------------------------------------


async def test_call_get_quality_gate_returns_ok_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, mock):
        mock.get(_QUALITY_GATE_URL).mock(return_value=httpx.Response(200, json=_PASSING_GATE))
        result: CallToolResult = await session.call_tool(
            "get_quality_gate", {"project_key": "my-project"}
        )

    assert not result.isError
    assert len(result.content) == 1
    text = result.content[0].text  # type: ignore[union-attr]
    assert '"status": "OK"' in text


async def test_call_get_issues_returns_issue_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, mock):
        mock.get(_ISSUES_URL).mock(return_value=httpx.Response(200, json=_ISSUES_PAGE))
        result: CallToolResult = await session.call_tool(
            "get_issues", {"project_key": "my-project"}
        )

    assert not result.isError
    text = result.content[0].text  # type: ignore[union-attr]
    assert "ISSUE-1" in text


async def test_call_get_issue_summary_returns_counts_by_severity_and_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, mock):
        mock.get(_ISSUES_URL).mock(return_value=httpx.Response(200, json=_ISSUES_PAGE))
        result: CallToolResult = await session.call_tool(
            "get_issue_summary", {"project_key": "my-project"}
        )

    assert not result.isError
    text = result.content[0].text  # type: ignore[union-attr]
    assert "by_severity" in text
    assert "by_type" in text


async def test_call_list_projects_returns_project_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, mock):
        mock.get(_PROJECTS_URL).mock(return_value=httpx.Response(200, json=_PROJECTS_PAGE))
        result: CallToolResult = await session.call_tool(
            "list_projects", {"organization": "my-org"}
        )

    assert not result.isError
    text = result.content[0].text  # type: ignore[union-attr]
    assert "my-project" in text


# ---------------------------------------------------------------------------
# tools/call — missing required parameters (tool-level error, not protocol)
# ---------------------------------------------------------------------------


async def test_call_get_quality_gate_without_project_key_returns_error_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no project_key and no env var, the tool returns a descriptive error string."""
    async with _connected_client(monkeypatch) as (session, _):
        result: CallToolResult = await session.call_tool("get_quality_gate", {})

    text = result.content[0].text  # type: ignore[union-attr]
    assert "project_key is required" in text


async def test_call_get_issues_without_project_key_returns_error_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, _):
        result: CallToolResult = await session.call_tool("get_issues", {})

    text = result.content[0].text  # type: ignore[union-attr]
    assert "project_key is required" in text


# ---------------------------------------------------------------------------
# tools/call — SonarCloud error surfaces as clean error string
# ---------------------------------------------------------------------------


async def test_call_get_quality_gate_sonar_401_returns_clean_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, mock):
        mock.get(_QUALITY_GATE_URL).mock(return_value=httpx.Response(401))
        result: CallToolResult = await session.call_tool(
            "get_quality_gate", {"project_key": "my-project"}
        )

    text = result.content[0].text  # type: ignore[union-attr]
    assert "Error" in text
    assert "Authentication" in text


async def test_call_get_issues_sonar_401_returns_clean_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, mock):
        mock.get(_ISSUES_URL).mock(return_value=httpx.Response(401))
        result: CallToolResult = await session.call_tool(
            "get_issues", {"project_key": "my-project"}
        )

    text = result.content[0].text  # type: ignore[union-attr]
    assert "Error" in text
    assert "Authentication" in text


async def test_call_list_projects_sonar_401_returns_clean_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _connected_client(monkeypatch) as (session, mock):
        mock.get(_PROJECTS_URL).mock(return_value=httpx.Response(401))
        result: CallToolResult = await session.call_tool("list_projects", {})

    text = result.content[0].text  # type: ignore[union-attr]
    assert "Error" in text
    assert "Authentication" in text
