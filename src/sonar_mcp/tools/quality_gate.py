import logging
import os
from typing import Any

from mcp.server.fastmcp import Context

from sonar_mcp.client import SonarClient
from sonar_mcp.exceptions import SonarError
from sonar_mcp.models import QualityGateParams

logger = logging.getLogger(__name__)


async def get_quality_gate(
    project_key: str,
    organization: str | None = None,
    *,
    ctx: Context[Any, SonarClient, Any],
) -> str:
    """Use this to check whether a project has passed its quality gate.

    Returns the overall status (OK, WARN, or ERROR) and the list of conditions
    that failed, including the metric name, actual value, and threshold. Call
    this first to assess overall project health before drilling into individual
    issues.
    """
    client: SonarClient = ctx.request_context.lifespan_context
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    logger.info("get_quality_gate project=%s org=%s", project_key, org)
    try:
        status = await client.get_quality_gate_status(
            QualityGateParams(project_key=project_key, organization=org)
        )
    except SonarError as e:
        return f"Error retrieving quality gate status: {e}"

    url = f"https://sonarcloud.io/dashboard?id={project_key}"
    if org:
        url += f"&org={org}"
    status.url = url

    return status.model_dump_json(indent=2)
