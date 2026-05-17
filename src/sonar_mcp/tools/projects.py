import json
import logging
import os
from typing import Any

from mcp.server.fastmcp import Context

from sonar_mcp.client import SonarClient
from sonar_mcp.exceptions import SonarError
from sonar_mcp.models import ProjectsParams

logger = logging.getLogger(__name__)


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
    logger.info("list_projects org=%s query=%s", org, query)
    try:
        projects = await client.get_projects(ProjectsParams(organization=org, query=query))
    except SonarError as e:
        return f"Error listing projects: {e}"

    def _url(project_key: str) -> str:
        base = f"https://sonarcloud.io/dashboard?id={project_key}"
        return base + f"&org={org}" if org else base

    return json.dumps(
        [{**project.model_dump(), "url": _url(project.key)} for project in projects], indent=2
    )
