from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel

from sonar_mcp.exceptions import (
    SonarAuthenticationError,
    SonarError,
    SonarPermissionError,
    SonarRateLimitError,
    SonarResourceNotFoundError,
    SonarValidationError,
)
from sonar_mcp.models import (
    Issue,
    IssuesParams,
    IssuesResponse,
    Project,
    ProjectsParams,
    ProjectsResponse,
    QualityGateParams,
    QualityGateProjectStatus,
)

_DEFAULT_BASE_URL = "https://sonarcloud.io/api"
_DEFAULT_TIMEOUT = 30.0
_PAGE_SIZE = 500


class _QualityGateResponse(BaseModel):
    projectStatus: QualityGateProjectStatus


class SonarClient:
    def __init__(self, token: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            auth=(token, ""),
            timeout=_DEFAULT_TIMEOUT,
        )

    async def get_quality_gate_status(self, params: QualityGateParams) -> QualityGateProjectStatus:
        query: dict[str, str] = {"projectKey": params.project_key}
        if params.organization is not None:
            query["organization"] = params.organization
        response = await self.get("qualitygates/project_status", params=query)
        self._handle_response(response)
        return _QualityGateResponse.model_validate(response.json()).projectStatus

    async def get_projects(self, params: ProjectsParams) -> list[Project]:
        query: dict[str, str] = {"ps": str(_PAGE_SIZE)}
        if params.organization is not None:
            query["organization"] = params.organization
        if params.query is not None:
            query["q"] = params.query

        all_projects: list[Project] = []
        page = 1
        while True:
            query["p"] = str(page)
            response = await self.get("projects/search", params=query)
            self._handle_response(response)
            parsed = ProjectsResponse.model_validate(response.json())
            all_projects.extend(parsed.components)
            if len(all_projects) >= parsed.paging.total:
                break
            page += 1
        return all_projects

    async def get_issues(self, params: IssuesParams) -> list[Issue]:
        query: dict[str, str] = {
            "componentKeys": params.project_key,
            "ps": str(_PAGE_SIZE),
        }
        if params.organization is not None:
            query["organization"] = params.organization
        if params.severity is not None:
            query["severities"] = params.severity.value
        if params.type is not None:
            query["types"] = params.type.value
        if params.statuses is not None:
            query["statuses"] = ",".join(s.value for s in params.statuses)

        all_issues: list[Issue] = []
        page = 1
        while True:
            query["p"] = str(page)
            response = await self.get("issues/search", params=query)
            self._handle_response(response)
            parsed = IssuesResponse.model_validate(response.json())
            all_issues.extend(parsed.issues)
            if len(all_issues) >= parsed.paging.total:
                break
            page += 1
        return all_issues

    def _handle_response(self, response: httpx.Response) -> None:
        if response.is_success:
            return

        status_code = response.status_code
        try:
            data = response.json()
            errors = data.get("errors", [])
            message = errors[0].get("msg") if errors else response.text
        except Exception:
            errors = []
            message = response.text

        if status_code == 401:
            raise SonarAuthenticationError("Authentication failed: Invalid API token")
        if status_code == 403:
            raise SonarPermissionError(f"Permission denied: {message}")
        if status_code == 404:
            raise SonarResourceNotFoundError(f"Resource not found: {message}")
        if status_code == 400:
            raise SonarValidationError(f"Validation failed: {message}", errors=errors)
        if status_code == 429:
            raise SonarRateLimitError("Rate limit exceeded")

        raise SonarError(f"API request failed with status {status_code}: {message}")

    async def get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        return await self._http.get(f"{self._base_url}/{path.lstrip('/')}", params=params)

    async def __aenter__(self) -> Self:
        await self._http.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._http.__aexit__(exc_type, exc_val, exc_tb)
