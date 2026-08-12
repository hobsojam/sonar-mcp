import json
import logging
import os
from time import perf_counter
from typing import Any

from mcp.server.mcpserver import Context

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
    ctx: Context[SonarClient, Any],
) -> str:
    """Use this to retrieve individual issues from a SonarCloud project.

    Returns the full list of issues, auto-paginated. Optionally filter by
    severity, issue_type, or status. Use get_issue_summary instead if you only need
    aggregate counts.
    """
    started_at = perf_counter()
    project = project_key if project_key is not None else os.environ.get("SONAR_DEFAULT_PROJECT")
    if not project:
        logger.info(
            "tool_call_completed tool=get_issues outcome=rejected "
            "reason=missing_project_key duration_ms=%.2f",
            (perf_counter() - started_at) * 1000,
        )
        return "Error: project_key is required (or set SONAR_DEFAULT_PROJECT)"
    client: SonarClient = ctx.request_context.lifespan_context
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    try:
        issues = await client.get_issues(
            IssuesParams(
                project_key=project,
                organization=org,
                severity=severity,
                issue_type=issue_type,
                statuses=[status] if status is not None else None,
            )
        )
    except SonarError as e:
        logger.info(
            "tool_call_completed tool=get_issues outcome=error error_type=%s duration_ms=%.2f",
            type(e).__name__,
            (perf_counter() - started_at) * 1000,
        )
        return f"Error retrieving issues: {e}"

    def _url(issue_key: str) -> str:
        base = (
            f"https://sonarcloud.io/project/issues?id={project}&issues={issue_key}&open={issue_key}"
        )
        return base + f"&org={org}" if org else base

    result = json.dumps(
        [{**issue.model_dump(), "url": _url(issue.key)} for issue in issues], indent=2
    )
    logger.info(
        "tool_call_completed tool=get_issues outcome=success result_count=%d duration_ms=%.2f",
        len(issues),
        (perf_counter() - started_at) * 1000,
    )
    return result


async def get_issue_summary(
    project_key: str | None = None,
    organization: str | None = None,
    *,
    ctx: Context[SonarClient, Any],
) -> str:
    """Use this to get a high-level breakdown of unresolved issues in a SonarCloud project,
    grouped by severity and type.

    Counts issues with status OPEN, CONFIRMED, or REOPENED (all unresolved states).
    Returns counts only — use get_issues if you need the individual issue details.
    """
    started_at = perf_counter()
    project = project_key if project_key is not None else os.environ.get("SONAR_DEFAULT_PROJECT")
    if not project:
        logger.info(
            "tool_call_completed tool=get_issue_summary outcome=rejected "
            "reason=missing_project_key duration_ms=%.2f",
            (perf_counter() - started_at) * 1000,
        )
        return "Error: project_key is required (or set SONAR_DEFAULT_PROJECT)"
    client: SonarClient = ctx.request_context.lifespan_context
    org: str | None = (
        organization if organization is not None else os.environ.get("SONAR_DEFAULT_ORG")
    )
    try:
        issues = await client.get_issues(
            IssuesParams(
                project_key=project,
                organization=org,
                statuses=[IssueStatus.OPEN, IssueStatus.CONFIRMED, IssueStatus.REOPENED],
            )
        )
    except SonarError as e:
        logger.info(
            "tool_call_completed tool=get_issue_summary outcome=error "
            "error_type=%s duration_ms=%.2f",
            type(e).__name__,
            (perf_counter() - started_at) * 1000,
        )
        return f"Error retrieving issue summary: {e}"
    by_severity = {s.value: 0 for s in IssueSeverity}
    by_type = {t.value: 0 for t in IssueType}
    for issue in issues:
        by_severity[issue.severity.value] += 1
        by_type[issue.type.value] += 1

    url = f"https://sonarcloud.io/project/issues?id={project}&resolved=false"
    if org:
        url += f"&org={org}"

    result = json.dumps({"by_severity": by_severity, "by_type": by_type, "url": url}, indent=2)
    logger.info(
        "tool_call_completed tool=get_issue_summary outcome=success "
        "result_count=%d duration_ms=%.2f",
        len(issues),
        (perf_counter() - started_at) * 1000,
    )
    return result
