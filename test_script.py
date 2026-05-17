import asyncio
import os
from unittest.mock import MagicMock
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.server import RequestContext
from sonar_mcp.client import SonarClient
from sonar_mcp.tools.projects import list_projects


async def run_test():
    token = os.environ.get("SONAR_TOKEN")
    if not token:
        print("Error: SONAR_TOKEN not set.")
        return

    async with SonarClient(token=token) as client:
        rc: RequestContext = RequestContext(
            request_id="test", meta=None, session=MagicMock(), lifespan_context=client
        )
        ctx = Context(request_context=rc, fastmcp=MagicMock())

        print("Fetching projects...")
        try:
            result = await list_projects(ctx=ctx)
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(run_test())
