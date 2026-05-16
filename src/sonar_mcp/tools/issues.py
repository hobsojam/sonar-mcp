import json
import os

from sonar_mcp.client import SonarClient
from sonar_mcp.models import IssueSeverity, IssuesParams, IssueStatus, IssueType


async def get_issues(
    project_key: str,
    organization: str | None = None,
    severity: IssueSeverity | None = None,
    type: IssueType | None = None,
    status: IssueStatus | None = None,
) -> str:
    """Use this to retrieve individual issues from a SonarCloud project.

    Returns the full list of issues, auto-paginated. Optionally filter by
    severity, type, or status. Use get_issue_summary instead if you only need
    aggregate counts.
    """
    token = os.environ["SONAR_TOKEN"]
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    async with SonarClient(token=token) as client:
        issues = await client.get_issues(
            IssuesParams(
                project_key=project_key,
                organization=org,
                severity=severity,
                type=type,
                statuses=[status] if status is not None else None,
            )
        )
    return json.dumps([issue.model_dump() for issue in issues], indent=2)


async def get_issue_summary(project_key: str, organization: str | None = None) -> str:
    """Use this to get a high-level breakdown of unresolved issues in a SonarCloud project,
    grouped by severity and type.

    Counts issues with status OPEN, CONFIRMED, or REOPENED (all unresolved states).
    Returns counts only — use get_issues if you need the individual issue details.
    """
    token = os.environ["SONAR_TOKEN"]
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    async with SonarClient(token=token) as client:
        issues = await client.get_issues(
            IssuesParams(
                project_key=project_key,
                organization=org,
                statuses=[IssueStatus.OPEN, IssueStatus.CONFIRMED, IssueStatus.REOPENED],
            )
        )

    by_severity = {s.value: 0 for s in IssueSeverity}
    by_type = {t.value: 0 for t in IssueType}
    for issue in issues:
        by_severity[issue.severity.value] += 1
        by_type[issue.type.value] += 1

    return json.dumps({"by_severity": by_severity, "by_type": by_type}, indent=2)
