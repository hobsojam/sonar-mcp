import os

from sonar_mcp.client import SonarClient
from sonar_mcp.models import QualityGateParams


async def get_quality_gate(project_key: str, organization: str | None = None) -> str:
    """Use this to check whether a project has passed its quality gate.

    Returns the overall status (OK, WARN, or ERROR) and the list of conditions
    that failed, including the metric name, actual value, and threshold. Call
    this first to assess overall project health before drilling into individual
    issues.
    """
    token = os.environ["SONAR_TOKEN"]
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    async with SonarClient(token=token) as client:
        status = await client.get_quality_gate_status(
            QualityGateParams(project_key=project_key, organization=org)
        )
    return status.model_dump_json(indent=2)
