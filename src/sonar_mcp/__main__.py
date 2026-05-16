import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from sonar_mcp.client import SonarClient
from sonar_mcp.tools.issues import get_issue_summary, get_issues
from sonar_mcp.tools.projects import list_projects
from sonar_mcp.tools.quality_gate import get_quality_gate


@asynccontextmanager
async def _lifespan(server: Any) -> AsyncGenerator[SonarClient, None]:
    token = os.environ.get("SONAR_TOKEN")
    if not token:
        sys.exit("Error: SONAR_TOKEN environment variable is required.")
    async with SonarClient(token=token) as client:
        yield client


server = FastMCP("sonar-mcp", lifespan=_lifespan)
server.tool()(get_quality_gate)
server.tool()(get_issues)
server.tool()(get_issue_summary)
server.tool()(list_projects)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
