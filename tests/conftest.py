import os
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.server import RequestContext

from sonar_mcp.client import SonarClient


@pytest.fixture
async def sonar_ctx() -> AsyncGenerator[Context, None]:  # type: ignore[type-arg]
    async with SonarClient(token="test-token") as client:
        rc: RequestContext = RequestContext(  # type: ignore[type-arg]
            request_id="test",
            meta=None,
            session=MagicMock(),
            lifespan_context=client,
        )
        yield Context(request_context=rc, fastmcp=MagicMock())


@pytest.fixture
async def integration_ctx() -> AsyncGenerator[tuple[Context, str, str], None]:  # type: ignore[type-arg]
    token = os.environ.get("SONAR_TOKEN", "")
    org = os.environ.get("SONAR_DEFAULT_ORG", "")
    project = os.environ.get("SONAR_DEFAULT_PROJECT", "")
    if not all([token, org, project]):
        pytest.skip("SONAR_TOKEN, SONAR_DEFAULT_ORG, and SONAR_DEFAULT_PROJECT must be set")
    async with SonarClient(token=token) as client:
        rc: RequestContext = RequestContext(  # type: ignore[type-arg]
            request_id="test",
            meta=None,
            session=MagicMock(),
            lifespan_context=client,
        )
        yield Context(request_context=rc, fastmcp=MagicMock()), org, project
