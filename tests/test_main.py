import logging
from unittest.mock import MagicMock

import pytest

from sonar_mcp.__main__ import _configure_logging, _lifespan, server
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


def test_logging_defaults_to_warning_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    _configure_logging()
    assert logging.getLogger("sonar_mcp").level == logging.WARNING


def test_logging_respects_log_level_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    _configure_logging()
    assert logging.getLogger("sonar_mcp").level == logging.DEBUG


def test_logging_falls_back_to_warning_for_invalid_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_LEVEL")
    _configure_logging()
    assert logging.getLogger("sonar_mcp").level == logging.WARNING


async def test_all_four_tools_are_registered() -> None:
    tools = await server.list_tools()
    assert {t.name for t in tools} == {
        "get_quality_gate",
        "get_issues",
        "get_issue_summary",
        "list_projects",
    }
