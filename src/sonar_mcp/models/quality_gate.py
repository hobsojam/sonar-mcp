from enum import StrEnum

from pydantic import BaseModel


class QualityGateStatus(StrEnum):
    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"


class QualityGateCondition(BaseModel):
    metricKey: str
    status: QualityGateStatus
    actualValue: str | None = None
    errorThreshold: str | None = None


class QualityGateProjectStatus(BaseModel):
    status: QualityGateStatus
    conditions: list[QualityGateCondition]


class QualityGateParams(BaseModel):
    project_key: str
    organization: str | None = None
