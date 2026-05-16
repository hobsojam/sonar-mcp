from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel

from sonar_mcp.models import QualityGateParams, QualityGateProjectStatus

_DEFAULT_BASE_URL = "https://sonarcloud.io/api"
_DEFAULT_TIMEOUT = 30.0


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
        response.raise_for_status()
        return _QualityGateResponse.model_validate(response.json()).projectStatus

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
