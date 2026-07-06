import asyncio
import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import perf_counter
from types import TracebackType
from typing import Any, Self

import httpx
from cachetools import TTLCache
from pydantic import ValidationError

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
_UNEXPECTED_RESPONSE_SHAPE = "Unexpected response shape from SonarCloud API"

logger = logging.getLogger(__name__)
_SYS_RANDOM = random.SystemRandom()


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
        started_at = perf_counter()
        cache_key = params.model_dump_json()
        if cache_key in self._quality_gate_cache:
            result = self._quality_gate_cache[cache_key]
            self._log_operation_completed(
                "get_quality_gate_status", started_at, result_count=1, page_count=0, cache_hit=True
            )
            return result

        query: dict[str, str] = {"projectKey": params.project_key}
        if params.organization is not None:
            query["organization"] = params.organization
        response = await self._get("qualitygates/project_status", params=query)
        self._handle_response(response, endpoint="qualitygates/project_status")
        try:
            result = QualityGateProjectStatus.model_validate(response.json()["projectStatus"])
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            self._log_invalid_response("qualitygates/project_status", response, exc)
            raise SonarError(_UNEXPECTED_RESPONSE_SHAPE) from exc
        self._quality_gate_cache[cache_key] = result
        self._log_operation_completed(
            "get_quality_gate_status", started_at, result_count=1, page_count=1, cache_hit=False
        )
        return result

    async def get_projects(self, params: ProjectsParams) -> list[Project]:
        started_at = perf_counter()
        cache_key = params.model_dump_json()
        if cache_key in self._projects_cache:
            result = self._projects_cache[cache_key]
            self._log_operation_completed(
                "get_projects", started_at, result_count=len(result), page_count=0, cache_hit=True
            )
            return result

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
            self._handle_response(response, endpoint="projects/search")
            try:
                parsed = ProjectsResponse.model_validate(response.json())
            except (ValidationError, ValueError) as exc:
                self._log_invalid_response("projects/search", response, exc)
                raise SonarError(_UNEXPECTED_RESPONSE_SHAPE) from exc
            all_projects.extend(parsed.components)
            if len(all_projects) >= parsed.paging.total:
                break
            page += 1

        self._projects_cache[cache_key] = all_projects
        self._log_operation_completed(
            "get_projects",
            started_at,
            result_count=len(all_projects),
            page_count=page,
            cache_hit=False,
        )
        return all_projects

    async def get_issues(self, params: IssuesParams) -> list[Issue]:
        started_at = perf_counter()
        cache_key = params.model_dump_json()
        if cache_key in self._issues_cache:
            result = self._issues_cache[cache_key]
            self._log_operation_completed(
                "get_issues", started_at, result_count=len(result), page_count=0, cache_hit=True
            )
            return result

        query: dict[str, str] = {
            "componentKeys": params.project_key,
            "ps": str(_PAGE_SIZE),
        }
        if params.organization is not None:
            query["organization"] = params.organization
        if params.severity is not None:
            query["severities"] = params.severity.value
        if params.issue_type is not None:
            query["types"] = params.issue_type.value
        if params.statuses is not None:
            query["statuses"] = ",".join(s.value for s in params.statuses)

        all_issues: list[Issue] = []
        page = 1
        while True:
            query["p"] = str(page)
            response = await self._get("issues/search", params=query)
            self._handle_response(response, endpoint="issues/search")
            try:
                parsed = IssuesResponse.model_validate(response.json())
            except (ValidationError, ValueError) as exc:
                self._log_invalid_response("issues/search", response, exc)
                raise SonarError(_UNEXPECTED_RESPONSE_SHAPE) from exc
            all_issues.extend(parsed.issues)
            if len(all_issues) >= parsed.paging.total:
                break
            page += 1

        self._issues_cache[cache_key] = all_issues
        self._log_operation_completed(
            "get_issues",
            started_at,
            result_count=len(all_issues),
            page_count=page,
            cache_hit=False,
        )
        return all_issues

    @staticmethod
    def _log_operation_completed(
        operation: str,
        started_at: float,
        *,
        result_count: int,
        page_count: int,
        cache_hit: bool,
    ) -> None:
        logger.info(
            "sonar_operation_completed operation=%s outcome=success cache_hit=%s "
            "duration_ms=%.2f result_count=%d page_count=%d",
            operation,
            str(cache_hit).lower(),
            (perf_counter() - started_at) * 1000,
            result_count,
            page_count,
        )

    @staticmethod
    def _log_invalid_response(endpoint: str, response: httpx.Response, exc: Exception) -> None:
        logger.error(
            "sonar_response_invalid endpoint=%s status_code=%d error_type=%s",
            endpoint,
            response.status_code,
            type(exc).__name__,
        )

    def _handle_response(self, response: httpx.Response, *, endpoint: str) -> None:
        if response.is_success:
            return

        status_code = response.status_code
        try:
            data = response.json()
            errors = data.get("errors", [])
            message = errors[0].get("msg") or response.text if errors else response.text
        except (ValueError, KeyError, TypeError):
            errors = []
            message = response.text

        # Response bodies can contain user-controlled or sensitive data. Keep the
        # diagnostic record useful without copying that content into server logs.
        logger.error("sonar_api_error endpoint=%s status_code=%d", endpoint, status_code)

        if status_code == 401:
            raise SonarAuthenticationError("Authentication failed: Invalid API token")
        if status_code == 403:
            raise SonarPermissionError(f"Permission denied: {message}")
        if status_code == 404:
            raise SonarResourceNotFoundError(f"Resource not found: {message}")
        if status_code == 400:
            raise SonarValidationError(f"Validation failed: {message}")
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
            except Exception as exc:
                logger.debug("metrics_hook_failed error_type=%s", type(exc).__name__)

    async def _get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        url = f"{self._base_url}/{path.lstrip('/')}"
        endpoint = path.lstrip("/")
        started_at = perf_counter()
        attempt = 0
        while True:
            try:
                parameter_names = ",".join(sorted(params)) if params else "none"
                logger.debug(
                    "sonar_http_request_started endpoint=%s parameter_names=%s",
                    endpoint,
                    parameter_names,
                )
                response = await self._http.get(url, params=params)
            except (httpx.RequestError, httpx.TransportError):
                attempt += 1
                if attempt > self._max_retries:
                    logger.error(
                        "sonar_http_request_failed endpoint=%s attempts=%d reason=transport_error",
                        endpoint,
                        attempt,
                    )
                    self._invoke_metrics_hook(
                        "retry_give_up",
                        {"url": url, "attempts": attempt, "reason": "transport_error"},
                    )
                    raise
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "sonar_http_request_retry endpoint=%s attempt=%d max_retries=%d "
                    "reason=transport_error delay_seconds=%.2f",
                    endpoint,
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
                    "sonar_http_request_retry endpoint=%s attempt=%d max_retries=%d "
                    "reason=rate_limited delay_seconds=%.2f",
                    endpoint,
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
                    "sonar_http_request_retry endpoint=%s status_code=%d attempt=%d "
                    "max_retries=%d reason=server_error delay_seconds=%.2f",
                    endpoint,
                    status,
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

            logger.debug(
                "sonar_http_request_completed endpoint=%s status_code=%d "
                "attempts=%d duration_ms=%.2f",
                endpoint,
                status,
                attempt + 1,
                (perf_counter() - started_at) * 1000,
            )
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
