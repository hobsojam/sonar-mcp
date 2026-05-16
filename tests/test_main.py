from unittest.mock import MagicMock

import pytest

from sonar_mcp.__main__ import _lifespan, server
from sonar_mcp.client import SonarClient


async def test_lifespan_exits_when_sonar_token_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SONAR_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="SONAR_TOKEN"):
        async with _lifespan(MagicMock()):
            pass


async def test_lifespan_yields_sonar_client_when_token_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "test-token")
    async with _lifespan(MagicMock()) as client:
        assert isinstance(client, SonarClient)


async def test_all_three_tools_are_registered() -> None:
    tools = await server.list_tools()
    assert {t.name for t in tools} == {"get_quality_gate", "get_issues", "get_issue_summary"}
