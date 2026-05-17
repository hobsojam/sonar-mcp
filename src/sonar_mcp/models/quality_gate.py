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
