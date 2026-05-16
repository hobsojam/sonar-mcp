import json
import os
from typing import Any

from mcp.server.fastmcp import Context

from sonar_mcp.client import SonarClient
from sonar_mcp.models import ProjectsParams


async def list_projects(
    organization: str | None = None,
    query: str | None = None,
    *,
    ctx: Context[Any, SonarClient, Any],
) -> str:
    """Use this to list projects in a SonarCloud organization.

    Returns a list of projects with their keys, names, and visibility.
    This is useful for discovering which projects are available for analysis.
    """
    client: SonarClient = ctx.request_context.lifespan_context
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    projects = await client.get_projects(ProjectsParams(organization=org, query=query))

    for project in projects:
        url = f"https://sonarcloud.io/dashboard?id={project.key}"
        if org:
            url += f"&org={org}"
        project.url = url

    return json.dumps([project.model_dump() for project in projects], indent=2)
