import os
from typing import Any

from mcp.server.fastmcp import Context

from sonar_mcp.client import SonarClient
from sonar_mcp.models import QualityGateParams


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
    status = await client.get_quality_gate_status(
        QualityGateParams(project_key=project_key, organization=org)
    )
    return status.model_dump_json(indent=2)
