from enum import StrEnum

from pydantic import BaseModel


class QualityGateStatus(StrEnum):
    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"


class QualityGateCondition(BaseModel):
    metricKey: str
    status: QualityGateStatus
    actualValue: str
    errorThreshold: str


class QualityGateProjectStatus(BaseModel):
    status: QualityGateStatus
    conditions: list[QualityGateCondition]
    url: str | None = None


class QualityGateParams(BaseModel):
    project_key: str
    organization: str | None = None


class Paging(BaseModel):
    pageIndex: int
    pageSize: int
    total: int


class IssueSeverity(StrEnum):
    BLOCKER = "BLOCKER"
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


class IssueType(StrEnum):
    BUG = "BUG"
    VULNERABILITY = "VULNERABILITY"
    CODE_SMELL = "CODE_SMELL"


class IssueStatus(StrEnum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    REOPENED = "REOPENED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Issue(BaseModel):
    key: str
    severity: IssueSeverity
    type: IssueType
    status: IssueStatus
    message: str
    component: str
    rule: str
    url: str | None = None


class IssuesResponse(BaseModel):
    issues: list[Issue]
    paging: Paging


class IssuesParams(BaseModel):
    project_key: str
    organization: str | None = None
    severity: IssueSeverity | None = None
    type: IssueType | None = None
    statuses: list[IssueStatus] | None = None
