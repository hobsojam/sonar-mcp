import asyncio
import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any, Self

import httpx
from cachetools import TTLCache
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

_DEFAULT_QUALITY_GATE_TTL = 300
_DEFAULT_ISSUES_TTL = 60
_DEFAULT_PROJECTS_TTL = 300

_CACHE_MAX_SIZE = 256

logger = logging.getLogger(__name__)
_SYS_RANDOM = random.SystemRandom()


class _QualityGateResponse(BaseModel):
    projectStatus: QualityGateProjectStatus


class SonarClient:
    def __init__(
        self,
        token: str,
        base_url: str = _DEFAULT_BASE_URL,
        quality_gate_ttl: float = _DEFAULT_QUALITY_GATE_TTL,
        issues_ttl: float = _DEFAULT_ISSUES_TTL,
        projects_ttl: float = _DEFAULT_PROJECTS_TTL,
        *,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        backoff_max: float = 10.0,
        jitter_frac: float = 0.2,
        metrics_hook: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            auth=(token, ""),
            timeout=_DEFAULT_TIMEOUT,
        )
        self._quality_gate_cache: TTLCache[str, QualityGateProjectStatus] = TTLCache(
            maxsize=_CACHE_MAX_SIZE, ttl=quality_gate_ttl
        )
        self._issues_cache: TTLCache[str, list[Issue]] = TTLCache(
            maxsize=_CACHE_MAX_SIZE, ttl=issues_ttl
        )
        self._projects_cache: TTLCache[str, list[Project]] = TTLCache(
            maxsize=_CACHE_MAX_SIZE, ttl=projects_ttl
        )

        # Retry configuration
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._jitter_frac = jitter_frac
        self._metrics_hook = metrics_hook

    async def get_quality_gate_status(self, params: QualityGateParams) -> QualityGateProjectStatus:
        cache_key = params.model_dump_json()
        if cache_key in self._quality_gate_cache:
            return self._quality_gate_cache[cache_key]

        query: dict[str, str] = {"projectKey": params.project_key}
        if params.organization is not None:
            query["organization"] = params.organization
        response = await self._get("qualitygates/project_status", params=query)
        self._handle_response(response)
        result = _QualityGateResponse.model_validate(response.json()).projectStatus
        self._quality_gate_cache[cache_key] = result
        return result

    async def get_projects(self, params: ProjectsParams) -> list[Project]:
        cache_key = params.model_dump_json()
        if cache_key in self._projects_cache:
            return self._projects_cache[cache_key]

        query: dict[str, str] = {"ps": str(_PAGE_SIZE)}
        if params.organization is not None:
            query["organization"] = params.organization
        if params.query is not None:
            query["q"] = params.query

        all_projects: list[Project] = []
        page = 1
        while True:
            query["p"] = str(page)
            response = await self._get("projects/search", params=query)
            self._handle_response(response)
            parsed = ProjectsResponse.model_validate(response.json())
            all_projects.extend(parsed.components)
            if len(all_projects) >= parsed.paging.total:
                break
            page += 1

        self._projects_cache[cache_key] = all_projects
        return all_projects

    async def get_issues(self, params: IssuesParams) -> list[Issue]:
        cache_key = params.model_dump_json()
        if cache_key in self._issues_cache:
            return self._issues_cache[cache_key]

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
            response = await self._get("issues/search", params=query)
            self._handle_response(response)
            parsed = IssuesResponse.model_validate(response.json())
            all_issues.extend(parsed.issues)
            if len(all_issues) >= parsed.paging.total:
                break
            page += 1

        self._issues_cache[cache_key] = all_issues
        return all_issues

    def _handle_response(self, response: httpx.Response) -> None:
        if response.is_success:
            return

        status_code = response.status_code
        try:
            data = response.json()
            errors = data.get("errors", [])
            message = errors[0].get("msg") if errors else response.text
        except (ValueError, KeyError, TypeError):
            errors = []
            message = response.text

        logger.error("SonarCloud API error %s: %s", status_code, message)

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

    def _backoff_delay(self, attempt: int) -> float:
        delay: float = min(self._backoff_base * (2 ** (attempt - 1)), self._backoff_max)
        jitter: float = _SYS_RANDOM.uniform(1 - self._jitter_frac, 1 + self._jitter_frac)
        return delay * jitter

    def _parse_retry_after(self, header: str | None, attempt: int) -> float:
        if header is not None:
            try:
                return float(int(header))
            except ValueError:
                pass
            try:
                dt = parsedate_to_datetime(header)
                return max(0.0, (dt - datetime.now(UTC)).total_seconds())
            except Exception:
                logger.debug("Unparseable Retry-After header %r; using backoff", header)
        return self._backoff_delay(attempt)

    def _invoke_metrics_hook(self, event: str, payload: dict[str, Any]) -> None:
        if self._metrics_hook:
            try:
                self._metrics_hook(event, payload)
            except Exception as e:
                logger.debug("metrics hook error: %s", e)

    async def _get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        url = f"{self._base_url}/{path.lstrip('/')}"
        attempt = 0
        while True:
            try:
                logger.debug("GET %s params=%s", url, params)
                response = await self._http.get(url, params=params)
                logger.debug("%s %s", response.status_code, url)
            except (httpx.RequestError, httpx.TransportError):
                attempt += 1
                if attempt > self._max_retries:
                    logger.exception("Giving up on request %s after transport errors", url)
                    self._invoke_metrics_hook(
                        "retry_give_up",
                        {"url": url, "attempts": attempt, "reason": "transport_error"},
                    )
                    raise
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "Retrying request %s (attempt %d/%d) after transport error; sleeping %.2fs",
                    url,
                    attempt,
                    self._max_retries,
                    delay,
                )
                self._invoke_metrics_hook(
                    "retry_attempt",
                    {"url": url, "attempt": attempt, "reason": "transport_error", "delay": delay},
                )
                await asyncio.sleep(delay)
                continue

            status = response.status_code
            if status == 429 and attempt < self._max_retries:
                attempt += 1
                delay = self._parse_retry_after(response.headers.get("Retry-After"), attempt)
                logger.warning(
                    "Rate limited on %s (attempt %d/%d); sleeping %.2fs",
                    url,
                    attempt,
                    self._max_retries,
                    delay,
                )
                self._invoke_metrics_hook(
                    "retry_attempt",
                    {"url": url, "attempt": attempt, "reason": "rate_limited", "delay": delay},
                )
                await asyncio.sleep(delay)
                continue

            if 500 <= status < 600 and attempt < self._max_retries:
                attempt += 1
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "Server error %d on %s (attempt %d/%d); sleeping %.2fs",
                    status,
                    url,
                    attempt,
                    self._max_retries,
                    delay,
                )
                self._invoke_metrics_hook(
                    "retry_attempt",
                    {"url": url, "attempt": attempt, "reason": "server_error", "delay": delay},
                )
                await asyncio.sleep(delay)
                continue

            return response

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
