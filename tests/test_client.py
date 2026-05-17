import base64
import email.utils
import time
import unittest.mock

import httpx
import pytest
import respx

from sonar_mcp.client import SonarClient
from sonar_mcp.exceptions import (
    SonarAuthenticationError,
    SonarError,
    SonarPermissionError,
    SonarRateLimitError,
    SonarResourceNotFoundError,
    SonarValidationError,
)
from sonar_mcp.models import IssuesParams, ProjectsParams, QualityGateParams, QualityGateStatus

_DEFAULT_BASE = "https://sonarcloud.io/api"


# --- General Client Tests ---


async def test_requests_include_basic_auth_with_token_as_username() -> None:
    path = "qualitygates/project_status"
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{path}").mock(return_value=httpx.Response(200))
        async with SonarClient(token="my-token") as client:
            await client._get(path)
        expected = "Basic " + base64.b64encode(b"my-token:").decode()
        assert route.calls[0].request.headers["authorization"] == expected


async def test_default_base_url_routes_to_sonarcloud() -> None:
    path = "qualitygates/project_status"
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{path}").mock(return_value=httpx.Response(200))
        async with SonarClient(token="token") as client:
            await client._get(path)
        assert route.called


async def test_custom_base_url_is_used() -> None:
    custom = "https://custom.sonar.example/api"
    path = "qualitygates/project_status"
    async with respx.mock() as mock:
        route = mock.get(f"{custom}/{path}").mock(return_value=httpx.Response(200))
        async with SonarClient(token="token", base_url=custom) as client:
            await client._get(path)
        assert route.called


# --- Quality Gate Status Tests ---

_QUALITY_GATE_PATH = "qualitygates/project_status"
_QUALITY_GATE_PAYLOAD = {
    "projectStatus": {
        "status": "ERROR",
        "conditions": [
            {
                "metricKey": "coverage",
                "status": "ERROR",
                "actualValue": "82.4",
                "errorThreshold": "85",
            }
        ],
    }
}


async def test_get_quality_gate_status_returns_parsed_status() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(200, json=_QUALITY_GATE_PAYLOAD)
        )
        async with SonarClient(token="token") as client:
            result = await client.get_quality_gate_status(
                QualityGateParams(project_key="my-project", organization="my-org")
            )
        request = route.calls[0].request
        assert b"projectKey=my-project" in request.url.query
        assert b"organization=my-org" in request.url.query
    assert result.status == QualityGateStatus.ERROR
    assert len(result.conditions) == 1
    assert result.conditions[0].metricKey == "coverage"


async def test_get_quality_gate_status_raises_on_401() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(return_value=httpx.Response(401))
        async with SonarClient(token="bad-token") as client:
            with pytest.raises(SonarAuthenticationError):
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))


async def test_get_quality_gate_status_raises_on_404() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(return_value=httpx.Response(404))
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarResourceNotFoundError):
                await client.get_quality_gate_status(QualityGateParams(project_key="nonexistent"))


async def test_get_quality_gate_status_raises_on_400_with_message() -> None:
    payload = {"errors": [{"msg": "Project key is required"}]}
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(400, json=payload)
        )
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarValidationError) as exc:
                await client.get_quality_gate_status(QualityGateParams(project_key=""))
    assert "Project key is required" in str(exc.value)


async def test_get_quality_gate_status_raises_on_403() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarPermissionError) as exc:
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))
    assert "Permission denied" in str(exc.value)


async def test_get_quality_gate_status_403_without_msg_key_falls_back_to_response_text() -> None:
    payload = {"errors": [{"code": "FORBIDDEN"}]}
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(403, json=payload)
        )
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarPermissionError) as exc:
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))
    assert "None" not in str(exc.value)
    assert "FORBIDDEN" in str(exc.value)


async def test_get_quality_gate_status_raises_on_429() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(return_value=httpx.Response(429))
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarRateLimitError):
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))


async def test_get_quality_gate_status_raises_on_500() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(return_value=httpx.Response(500))
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarError) as exc:
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))
    assert "API request failed with status 500" in str(exc.value)


# --- Issues Tests ---

_ISSUES_PATH = "issues/search"
_ISSUE = {
    "key": "issue-1",
    "severity": "MAJOR",
    "type": "BUG",
    "status": "OPEN",
    "message": "Some bug",
    "component": "my-project:src/file.py",
    "rule": "python:S1234",
}


def _page(page_index: int, page_size: int, total: int, issues: list[dict]) -> dict:  # type: ignore[type-arg]
    return {
        "issues": issues,
        "paging": {"pageIndex": page_index, "pageSize": page_size, "total": total},
    }


async def test_get_issues_single_page_returns_all_issues() -> None:
    payload = _page(1, 500, 1, [_ISSUE])
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with SonarClient(token="token") as client:
            issues = await client.get_issues(IssuesParams(project_key="my-project"))
    assert len(issues) == 1
    assert issues[0].key == "issue-1"


async def test_get_issues_multi_page_fetches_all_pages_and_merges() -> None:
    issue_a = {**_ISSUE, "key": "issue-1"}
    issue_b = {**_ISSUE, "key": "issue-2"}
    pages = iter(
        [
            httpx.Response(200, json=_page(1, 1, 2, [issue_a])),
            httpx.Response(200, json=_page(2, 1, 2, [issue_b])),
        ]
    )
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(side_effect=lambda _req: next(pages))
        async with SonarClient(token="token") as client:
            issues = await client.get_issues(IssuesParams(project_key="my-project"))
    assert len(issues) == 2
    assert issues[0].key == "issue-1"
    assert issues[1].key == "issue-2"


async def test_get_issues_raises_on_401() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(return_value=httpx.Response(401))
        async with SonarClient(token="bad-token") as client:
            with pytest.raises(SonarAuthenticationError):
                await client.get_issues(IssuesParams(project_key="my-project"))


async def test_get_projects_returns_all_projects() -> None:
    payload = {
        "paging": {"pageIndex": 1, "pageSize": 100, "total": 1},
        "components": [
            {
                "key": "my-project",
                "name": "My Project",
                "organization": "my-org",
                "visibility": "public",
            }
        ],
    }
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/projects/search").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with SonarClient(token="token") as client:
            projects = await client.get_projects(ProjectsParams(organization="my-org"))
    assert len(projects) == 1
    assert projects[0].key == "my-project"


# --- Caching Tests ---


async def test_get_quality_gate_status_second_call_hits_cache() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(200, json=_QUALITY_GATE_PAYLOAD)
        )
        async with SonarClient(token="token") as client:
            params = QualityGateParams(project_key="my-project", organization="my-org")
            await client.get_quality_gate_status(params)
            await client.get_quality_gate_status(params)
    assert route.call_count == 1


async def test_get_quality_gate_status_different_args_are_not_cached() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(200, json=_QUALITY_GATE_PAYLOAD)
        )
        async with SonarClient(token="token") as client:
            await client.get_quality_gate_status(
                QualityGateParams(project_key="project-a", organization="my-org")
            )
            await client.get_quality_gate_status(
                QualityGateParams(project_key="project-b", organization="my-org")
            )
    assert route.call_count == 2


async def test_get_quality_gate_status_cache_expires_after_ttl() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(200, json=_QUALITY_GATE_PAYLOAD)
        )
        async with SonarClient(token="token", quality_gate_ttl=0) as client:
            params = QualityGateParams(project_key="my-project")
            await client.get_quality_gate_status(params)
            await client.get_quality_gate_status(params)
    assert route.call_count == 2


async def test_get_issues_second_call_hits_cache() -> None:
    payload = _page(1, 500, 1, [_ISSUE])
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with SonarClient(token="token") as client:
            params = IssuesParams(project_key="my-project")
            await client.get_issues(params)
            await client.get_issues(params)
    assert route.call_count == 1


async def test_get_issues_different_args_are_not_cached() -> None:
    payload = _page(1, 500, 1, [_ISSUE])
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with SonarClient(token="token") as client:
            await client.get_issues(IssuesParams(project_key="project-a"))
            await client.get_issues(IssuesParams(project_key="project-b"))
    assert route.call_count == 2


async def test_get_issues_cache_expires_after_ttl() -> None:
    payload = _page(1, 500, 1, [_ISSUE])
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with SonarClient(token="token", issues_ttl=0) as client:
            params = IssuesParams(project_key="my-project")
            await client.get_issues(params)
            await client.get_issues(params)
    assert route.call_count == 2


_PROJECTS_PAYLOAD = {
    "paging": {"pageIndex": 1, "pageSize": 500, "total": 1},
    "components": [
        {
            "key": "my-project",
            "name": "My Project",
            "organization": "my-org",
            "visibility": "public",
        }
    ],
}


async def test_get_projects_second_call_hits_cache() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/projects/search").mock(
            return_value=httpx.Response(200, json=_PROJECTS_PAYLOAD)
        )
        async with SonarClient(token="token") as client:
            params = ProjectsParams(organization="my-org")
            await client.get_projects(params)
            await client.get_projects(params)
    assert route.call_count == 1


async def test_get_projects_different_args_are_not_cached() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/projects/search").mock(
            return_value=httpx.Response(200, json=_PROJECTS_PAYLOAD)
        )
        async with SonarClient(token="token") as client:
            await client.get_projects(ProjectsParams(organization="org-a"))
            await client.get_projects(ProjectsParams(organization="org-b"))
    assert route.call_count == 2


async def test_get_projects_cache_expires_after_ttl() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/projects/search").mock(
            return_value=httpx.Response(200, json=_PROJECTS_PAYLOAD)
        )
        async with SonarClient(token="token", projects_ttl=0) as client:
            params = ProjectsParams(organization="my-org")
            await client.get_projects(params)
            await client.get_projects(params)
    assert route.call_count == 2


# --- Malformed 200 Response Tests ---


async def test_get_quality_gate_status_raises_sonar_error_on_malformed_200() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(200, json={})
        )
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarError) as exc:
                await client.get_quality_gate_status(QualityGateParams(project_key="my-project"))
    assert "Unexpected response shape" in str(exc.value)


async def test_get_issues_raises_sonar_error_on_malformed_200() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/{_ISSUES_PATH}").mock(return_value=httpx.Response(200, json={}))
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarError) as exc:
                await client.get_issues(IssuesParams(project_key="my-project"))
    assert "Unexpected response shape" in str(exc.value)


async def test_get_projects_raises_sonar_error_on_malformed_200() -> None:
    async with respx.mock() as mock:
        mock.get(f"{_DEFAULT_BASE}/projects/search").mock(return_value=httpx.Response(200, json={}))
        async with SonarClient(token="token") as client:
            with pytest.raises(SonarError) as exc:
                await client.get_projects(ProjectsParams(organization="my-org"))
    assert "Unexpected response shape" in str(exc.value)


async def test_separate_client_instances_have_independent_caches() -> None:
    async with respx.mock() as mock:
        route = mock.get(f"{_DEFAULT_BASE}/{_QUALITY_GATE_PATH}").mock(
            return_value=httpx.Response(200, json=_QUALITY_GATE_PAYLOAD)
        )
        params = QualityGateParams(project_key="my-project")
        async with SonarClient(token="token") as client_a:
            await client_a.get_quality_gate_status(params)
        async with SonarClient(token="token") as client_b:
            await client_b.get_quality_gate_status(params)
    assert route.call_count == 2


# --- Retry and Backoff Tests ---

_RETRY_PATH = "qualitygates/project_status"


async def test_transport_error_retries_and_succeeds_on_second_attempt() -> None:
    call_count = 0

    def side_effect(_req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(200, json=_QUALITY_GATE_PAYLOAD)

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        async with respx.mock() as mock:
            route = mock.get(f"{_DEFAULT_BASE}/{_RETRY_PATH}").mock(side_effect=side_effect)
            async with SonarClient(token="token", backoff_base=0) as client:
                response = await client._get(_RETRY_PATH)
    assert route.call_count == 2
    assert response.status_code == 200


async def test_transport_error_exceeding_max_retries_re_raises() -> None:
    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        async with respx.mock() as mock:
            mock.get(f"{_DEFAULT_BASE}/{_RETRY_PATH}").mock(
                side_effect=httpx.ConnectError("connection reset")
            )
            async with SonarClient(token="token", max_retries=1, backoff_base=0) as client:
                with pytest.raises(httpx.ConnectError):
                    await client._get(_RETRY_PATH)


async def test_429_with_integer_retry_after_retries_and_succeeds() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json=_QUALITY_GATE_PAYLOAD),
        ]
    )

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock) as mock_sleep:
        async with respx.mock() as mock:
            route = mock.get(f"{_DEFAULT_BASE}/{_RETRY_PATH}").mock(
                side_effect=lambda _req: next(responses)
            )
            async with SonarClient(token="token", backoff_base=0) as client:
                response = await client._get(_RETRY_PATH)
    assert route.call_count == 2
    assert response.status_code == 200
    mock_sleep.assert_awaited_once()
    assert mock_sleep.call_args[0][0] == pytest.approx(0.0, abs=1e-9)


async def test_429_with_http_date_retry_after_sleeps_for_future_delta() -> None:
    # usegmt=True produces an offset-aware datetime that parsedate_to_datetime can compare to UTC
    future_date = email.utils.formatdate(time.time() + 2, usegmt=True)
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": future_date}),
            httpx.Response(200, json=_QUALITY_GATE_PAYLOAD),
        ]
    )

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock) as mock_sleep:
        async with respx.mock() as mock:
            route = mock.get(f"{_DEFAULT_BASE}/{_RETRY_PATH}").mock(
                side_effect=lambda _req: next(responses)
            )
            async with SonarClient(token="token", backoff_base=0) as client:
                response = await client._get(_RETRY_PATH)
    assert route.call_count == 2
    assert response.status_code == 200
    mock_sleep.assert_awaited_once()
    assert mock_sleep.call_args[0][0] > 0


async def test_429_with_unparseable_retry_after_falls_back_to_backoff_delay() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "not-a-date"}),
            httpx.Response(200, json=_QUALITY_GATE_PAYLOAD),
        ]
    )

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock) as mock_sleep:
        async with respx.mock() as mock:
            route = mock.get(f"{_DEFAULT_BASE}/{_RETRY_PATH}").mock(
                side_effect=lambda _req: next(responses)
            )
            async with SonarClient(token="token", backoff_base=0) as client:
                response = await client._get(_RETRY_PATH)
    assert route.call_count == 2
    assert response.status_code == 200
    mock_sleep.assert_awaited_once()


async def test_5xx_retries_and_succeeds_on_second_attempt() -> None:
    responses = iter(
        [
            httpx.Response(500),
            httpx.Response(200, json=_QUALITY_GATE_PAYLOAD),
        ]
    )

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        async with respx.mock() as mock:
            route = mock.get(f"{_DEFAULT_BASE}/{_RETRY_PATH}").mock(
                side_effect=lambda _req: next(responses)
            )
            async with SonarClient(token="token", backoff_base=0) as client:
                response = await client._get(_RETRY_PATH)
    assert route.call_count == 2
    assert response.status_code == 200


async def test_metrics_hook_receives_retry_attempt_on_transport_error() -> None:
    call_count = 0

    def side_effect(_req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(200, json=_QUALITY_GATE_PAYLOAD)

    hook = unittest.mock.MagicMock()

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        async with respx.mock() as mock:
            mock.get(f"{_DEFAULT_BASE}/{_RETRY_PATH}").mock(side_effect=side_effect)
            async with SonarClient(token="token", backoff_base=0, metrics_hook=hook) as client:
                await client._get(_RETRY_PATH)

    hook.assert_called()
    event_names = [call[0][0] for call in hook.call_args_list]
    assert "retry_attempt" in event_names
    retry_call = next(c for c in hook.call_args_list if c[0][0] == "retry_attempt")
    assert "url" in retry_call[0][1]


async def test_metrics_hook_receives_retry_give_up_after_max_retries_exhausted() -> None:
    hook = unittest.mock.MagicMock()

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        async with respx.mock() as mock:
            mock.get(f"{_DEFAULT_BASE}/{_RETRY_PATH}").mock(
                side_effect=httpx.ConnectError("connection reset")
            )
            async with SonarClient(
                token="token", max_retries=1, backoff_base=0, metrics_hook=hook
            ) as client:
                with pytest.raises(httpx.ConnectError):
                    await client._get(_RETRY_PATH)

    event_names = [call[0][0] for call in hook.call_args_list]
    assert "retry_give_up" in event_names
