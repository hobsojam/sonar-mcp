import json
import logging
import os
from typing import Any

from mcp.server.fastmcp import Context

from sonar_mcp.client import SonarClient
from sonar_mcp.exceptions import SonarError
from sonar_mcp.models import IssueSeverity, IssuesParams, IssueStatus, IssueType

logger = logging.getLogger(__name__)


async def get_issues(
    project_key: str | None = None,
    organization: str | None = None,
    severity: IssueSeverity | None = None,
    issue_type: IssueType | None = None,
    status: IssueStatus | None = None,
    *,
    ctx: Context[Any, SonarClient, Any],
) -> str:
    """Use this to retrieve individual issues from a SonarCloud project.

    Returns the full list of issues, auto-paginated. Optionally filter by
    severity, issue_type, or status. Use get_issue_summary instead if you only need
    aggregate counts.
    """
    project = project_key if project_key is not None else os.environ.get("SONAR_DEFAULT_PROJECT")
    if not project:
        return "Error: project_key is required (or set SONAR_DEFAULT_PROJECT)"
    client: SonarClient = ctx.request_context.lifespan_context
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    logger.info(
        "get_issues project=%s org=%s severity=%s issue_type=%s status=%s",
        project,
        org,
        severity,
        issue_type,
        status,
    )
    try:
        issues = await client.get_issues(
            IssuesParams(
                project_key=project,
                organization=org,
                severity=severity,
                type=issue_type,
                statuses=[status] if status is not None else None,
            )
        )
    except SonarError as e:
        return f"Error retrieving issues: {e}"

    def _url(issue_key: str) -> str:
        base = (
            f"https://sonarcloud.io/project/issues?id={project}&issues={issue_key}&open={issue_key}"
        )
        return base + f"&org={org}" if org else base

    return json.dumps(
        [{**issue.model_dump(), "url": _url(issue.key)} for issue in issues], indent=2
    )


async def get_issue_summary(
    project_key: str | None = None,
    organization: str | None = None,
    *,
    ctx: Context[Any, SonarClient, Any],
) -> str:
    """Use this to get a high-level breakdown of unresolved issues in a SonarCloud project,
    grouped by severity and type.

    Counts issues with status OPEN, CONFIRMED, or REOPENED (all unresolved states).
    Returns counts only — use get_issues if you need the individual issue details.
    """
    project = project_key if project_key is not None else os.environ.get("SONAR_DEFAULT_PROJECT")
    if not project:
        return "Error: project_key is required (or set SONAR_DEFAULT_PROJECT)"
    client: SonarClient = ctx.request_context.lifespan_context
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    logger.info("get_issue_summary project=%s org=%s", project, org)
    try:
        issues = await client.get_issues(
            IssuesParams(
                project_key=project,
                organization=org,
                statuses=[IssueStatus.OPEN, IssueStatus.CONFIRMED, IssueStatus.REOPENED],
            )
        )
    except SonarError as e:
        return f"Error retrieving issue summary: {e}"

    by_severity = {s.value: 0 for s in IssueSeverity}
    by_type = {t.value: 0 for t in IssueType}
    for issue in issues:
        by_severity[issue.severity.value] += 1
        by_type[issue.type.value] += 1

    url = f"https://sonarcloud.io/project/issues?id={project}&resolved=false"
    if org:
        url += f"&org={org}"

    return json.dumps({"by_severity": by_severity, "by_type": by_type, "url": url}, indent=2)
