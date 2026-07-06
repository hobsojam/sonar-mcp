import json
import logging
import os
from time import perf_counter
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
    started_at = perf_counter()
    client: SonarClient = ctx.request_context.lifespan_context
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    try:
        projects = await client.get_projects(ProjectsParams(organization=org, query=query))
    except SonarError as e:
        logger.info(
            "tool_call_completed tool=list_projects outcome=error error_type=%s duration_ms=%.2f",
            type(e).__name__,
            (perf_counter() - started_at) * 1000,
        )
        return f"Error listing projects: {e}"

    def _url(project_key: str) -> str:
        base = f"https://sonarcloud.io/dashboard?id={project_key}"
        return base + f"&org={org}" if org else base

    result = json.dumps(
        [{**project.model_dump(), "url": _url(project.key)} for project in projects], indent=2
    )
    logger.info(
        "tool_call_completed tool=list_projects outcome=success result_count=%d duration_ms=%.2f",
        len(projects),
        (perf_counter() - started_at) * 1000,
    )
    return result
