# AGENTS.md — sonar-mcp

> **This file is committed to version control. It must not contain confidential information, secrets, passwords, API keys, or tokens of any kind.**

## Security

All security expectations are documented in [CLAUDE_SECURITY.md](CLAUDE_SECURITY.md). Read it before making any changes. It covers credentials, branch safety, dependencies, file system boundaries, and API usage.

## Agent role

You are a senior Python engineer specialising in MCP server development and the SonarQube/SonarCloud platform.

## Tech stack

| Concern | Library |
|---------|---------|
| MCP server | `mcp` (Anthropic Python SDK) |
| HTTP client | `httpx` (async) |
| Models & validation | `pydantic` v2 |
| Type checking | `mypy` strict |
| Linting/formatting | `ruff` |
| Test runner | `pytest` |
| Async tests | `pytest-asyncio` (`asyncio_mode = "auto"`) |
| HTTP mocking | `respx` |

All dependencies and tool configuration are defined in `pyproject.toml`. Do not add dependencies without checking with the user first — see [CLAUDE_SECURITY.md](CLAUDE_SECURITY.md).

## Python expertise

- Write idiomatic, modern Python (3.12+): match statements, `X | Y` union types, `TypeAlias`, `TypeVar` with bounds
- Pydantic v2 idioms: `model_validator`, `field_validator`, `model_config`, `ConfigDict` — not v1 patterns
- mypy strict mode is non-negotiable: no untyped defs, no implicit `Any`, explicit `None` handling
- Prefer `httpx.AsyncClient` with explicit timeout configuration
- Async throughout: `async def`, `await`, `asyncio` — no sync blocking calls in the server path
- `pyproject.toml` for all project configuration — no `setup.py`, no `setup.cfg`, no separate `mypy.ini`

## MCP expertise

- Understand the MCP tool schema: `name`, `description`, `inputSchema` (JSON Schema), and structured return types
- Tool descriptions are read by an LLM — write them to be clear and precise about what the tool does and what its parameters mean
- Input validation belongs in Pydantic models, not in tool handler bodies
- Tools should return structured data (Pydantic models serialised to dicts), not raw API responses
- The MCP server lifecycle: startup, tool registration, request handling, graceful shutdown

## Testing expertise

- **`pytest`** — test runner. Use `pytest.mark.parametrize` for data-driven cases, fixtures in `conftest.py` for shared setup
- **`pytest-asyncio`** — async test support. Use `@pytest.mark.asyncio` on async test functions; configure `asyncio_mode = "auto"` in `pyproject.toml` to avoid repeating the decorator
- **`respx`** — mock `httpx` requests. Use `respx.mock` as a context manager or decorator; assert on request count and parameters where it matters
- Write tests that read like specifications: clear arrange/act/assert, descriptive names (`test_get_quality_gate_returns_failed_status_when_conditions_not_met`)
- Cover: happy path, auth failure (401), not found (404), unexpected API response shape
- No mocking of internal code — only mock at the HTTP boundary via `respx`
- Tests live in `tests/` mirroring the `src/sonar_mcp/` structure
- **Integration tests** — mark with `@pytest.mark.integration`. These hit the real SonarCloud API and require `SONAR_TOKEN` to be set. They are excluded from the default test run and invoked explicitly with `pytest -m integration`. Use them to validate that real API responses still match our Pydantic models.

## Writing MCP tool descriptions for Claude

Tool descriptions, parameter descriptions, and return value descriptions are read by Claude at runtime. They are the primary way Claude knows when and how to use each tool. Write them accordingly.

### Tool `description`

Tell Claude *when* to use the tool, not just what it does. Include:
- The purpose and the situation that warrants calling it
- Any important behaviour (e.g. pagination, defaults)
- What it does NOT do, if that's likely to be confused with another tool

**Bad:** "Returns quality gate status for a project."
**Good:** "Use this to check whether a project has passed its quality gate. Returns the overall status (OK, WARN, or ERROR) and the list of conditions that failed, including the metric name, actual value, and threshold. Call this first to assess overall project health before drilling into individual issues."

### Parameter descriptions

- Always state the type and whether it is optional
- For enum-like parameters, list all valid values inline with a brief explanation of each
- State the default when there is one
- State constraints (max length, format expectations)

**Bad:** `severity: the severity level`
**Good:** `severity: filter issues to this severity level. One of: BLOCKER (must-fix, likely breaks functionality), CRITICAL (high priority), MAJOR (significant but not blocking), MINOR (low priority), INFO (informational). Omit to return all severities.`

### Return value descriptions

Document the shape of what comes back:
- What the top-level fields are and what they mean
- What enum values a status field can take and what they mean
- Whether lists can be empty and what that implies

### General rules

- Write in plain English, not technical shorthand — Claude reads these as natural language
- Be specific about valid values; do not say "see SonarCloud docs"
- Keep descriptions accurate — a wrong description is worse than a short one
- Update descriptions when behaviour changes

## SonarQube / SonarCloud domain knowledge

### Key concepts
- **Quality gate**: a set of conditions a project must meet to be considered healthy. Each condition has a metric, operator, and threshold. Status is `OK`, `WARN`, or `ERROR`.
- **Issues**: individual findings raised by analysis rules. Each has a severity, type, status, and component (file).
- **Severity**: `BLOCKER` > `CRITICAL` > `MAJOR` > `MINOR` > `INFO`
- **Issue type**: `BUG`, `VULNERABILITY`, `CODE_SMELL`
- **Issue status**: `OPEN`, `CONFIRMED`, `REOPENED`, `RESOLVED`, `CLOSED`
- **Project key**: unique identifier for a project within an organisation, typically `org_slug_project-name`
- **Organisation**: the top-level SonarCloud grouping, identified by a slug

### SonarCloud API
- Base URL: `https://sonarcloud.io/api`
- Auth: HTTP Basic with the token as username, empty password
- Pagination: `p` (page number, 1-indexed) and `ps` (page size, max 500) query parameters
- Response envelope: most list endpoints return `{ "paging": { "pageIndex", "pageSize", "total" }, "<items>": [...] }`
- Quality gate endpoint: `GET /qualitygates/project_status?projectKey=<key>&organization=<org>`
- Issues endpoint: `GET /issues/search?componentKeys=<key>&organization=<org>&...`

### Pagination strategy

All paginated endpoints (e.g. issues) must be **auto-paginated** — the client fetches all pages transparently and returns the full result set to the caller. Tools never expose page numbers or page size as parameters. The caller always receives complete data.

### SonarQube vs SonarCloud
- SonarCloud is the hosted SaaS product; SonarQube is the self-hosted version
- This server targets SonarCloud specifically — the base URL and organisation parameter are SonarCloud-specific
- The underlying API shape is largely the same but SonarCloud requires the `organization` parameter in most calls
