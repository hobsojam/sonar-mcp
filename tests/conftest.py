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
