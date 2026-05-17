from pydantic import BaseModel

from sonar_mcp.models.common import Paging


class Project(BaseModel):
    key: str
    name: str
    organization: str
    visibility: str
    lastAnalysisDate: str | None = None
    url: str | None = None


class ProjectsResponse(BaseModel):
    paging: Paging
    components: list[Project]


class ProjectsParams(BaseModel):
    organization: str | None = None
    query: str | None = None
