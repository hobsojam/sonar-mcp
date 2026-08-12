import json
import logging
import os
from time import perf_counter
from typing import Any

from mcp.server.mcpserver import Context

from sonar_mcp.client import SonarClient
from sonar_mcp.exceptions import SonarError
from sonar_mcp.models import QualityGateParams

logger = logging.getLogger(__name__)


async def get_quality_gate(
    project_key: str | None = None,
    organization: str | None = None,
    *,
    ctx: Context[SonarClient, Any],
) -> str:
    """Use this to check whether a project has passed its quality gate.

    Returns the overall status (OK, WARN, or ERROR) and the list of conditions
    that failed, including the metric name, actual value, and threshold. Call
    this first to assess overall project health before drilling into individual
    issues.
    """
    started_at = perf_counter()
    project = project_key if project_key is not None else os.environ.get("SONAR_DEFAULT_PROJECT")
    if not project:
        logger.info(
            "tool_call_completed tool=get_quality_gate outcome=rejected "
            "reason=missing_project_key duration_ms=%.2f",
            (perf_counter() - started_at) * 1000,
        )
        return "Error: project_key is required (or set SONAR_DEFAULT_PROJECT)"
    client: SonarClient = ctx.request_context.lifespan_context
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    try:
        status = await client.get_quality_gate_status(
            QualityGateParams(project_key=project, organization=org)
        )
    except SonarError as e:
        logger.info(
            "tool_call_completed tool=get_quality_gate outcome=error "
            "error_type=%s duration_ms=%.2f",
            type(e).__name__,
            (perf_counter() - started_at) * 1000,
        )
        return f"Error retrieving quality gate status: {e}"
    url = f"https://sonarcloud.io/dashboard?id={project}"
    if org:
        url += f"&org={org}"

    result = json.dumps({**status.model_dump(), "url": url}, indent=2)
    logger.info(
        "tool_call_completed tool=get_quality_gate outcome=success result_count=1 duration_ms=%.2f",
        (perf_counter() - started_at) * 1000,
    )
    return result
