# sonar-mcp

> **Note:** This is an unofficial, community-built project and is not affiliated with or endorsed by SonarSource. An official MCP server is available at [docs.sonarsource.com](https://docs.sonarsource.com/agent-centric-development-cycle/developer-tools/mcp-server).

A Model Context Protocol (MCP) server that wraps the SonarCloud REST API, exposing named tools for querying code quality data directly from Claude Code.

## What it does

Registers a set of MCP tools that Claude can call in any session to query SonarCloud without manual HTTP calls or token management. Pass an organization and project key per call, and the server handles auth, request shaping, and response parsing.

## Why should I use it?

You probably shouldn't. There is an [official sonarqube MCP from SonarSource](https://docs.sonarsource.com/agent-centric-development-cycle/developer-tools/mcp-server) which is better supported and has more functionality. I use this implementation because its lightweight and simple and I wrote it (together with Claude) myself as a learning excersize. If for some reason you do not want to use the MCP from SonarSource then this is a simple and easy to setup alternative.

## Tools

| Tool | Description |
|------|-------------|
| `get_quality_gate` | Quality gate status and failing conditions for a project |
| `get_issues` | List issues filtered by severity, type, and status |
| `get_issue_summary` | Aggregate issue counts by severity and type |
| `list_projects` | List projects in a SonarCloud organization with their keys, names, and visibility |

## Tech stack

- Python 3.12+
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- `httpx` — async HTTP client
- `pydantic` — request/response models and validation
- `cachetools` — TTL-based in-memory caching for API responses
- `mypy` (strict) — static type checking
- `ruff` — linting and formatting
- `pytest` + `respx` + `pytest-asyncio` — test suite

## Setup

### 1. Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package and project manager (required; the MCP server registration uses `uv run`)
- A SonarCloud account and API token

**Install uv:**

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via pip (any platform)
pip install uv

# Or via Homebrew (macOS)
brew install uv
```

See the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for other options.

### 2. Install dependencies

```bash
uv sync --all-extras
pre-commit install
```

This creates a virtual environment in `.venv` and installs all dependencies (including dev tools) automatically.

Alternatively, with plain pip:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# or: source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
pre-commit install
```

### 3. Configure environment

Create a `.env` file or set environment variables:

```env
SONAR_TOKEN=your_sonarcloud_token

# Optional defaults — can be overridden per tool call
SONAR_DEFAULT_ORG=your_organization_slug
SONAR_DEFAULT_PROJECT=your_project_key

# Optional log level for the sonar_mcp package (DEBUG, INFO, WARNING, ERROR). Default: WARNING
# LOG_LEVEL=DEBUG
```

| Variable | Required | Description |
|----------|----------|-------------|
| `SONAR_TOKEN` | Yes | SonarCloud API token |
| `SONAR_DEFAULT_ORG` | No | Default organization slug — can be overridden per tool call |
| `SONAR_DEFAULT_PROJECT` | No | Default project key — can be overridden per tool call |
| `LOG_LEVEL` | No | Log level for `sonar_mcp` (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Default: `WARNING` |

### 4. Register with Claude Code

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "sonar": {
      "command": "uv",
      "args": ["run", "python", "-m", "sonar_mcp"],
      "env": {
        "SONAR_TOKEN": "${SONAR_TOKEN}"
      }
    }
  }
}
```

## Running tests

```bash
pytest
```

With type checking:

```bash
mypy src
```

With linting:

```bash
ruff check src tests
```

## Running integration tests

Integration tests call the real SonarCloud API and require the following environment variables to be set:

| Variable | Description |
|----------|-------------|
| `SONAR_TOKEN` | A valid SonarCloud API token |
| `SONAR_DEFAULT_ORG` | The SonarCloud organization slug to test against |
| `SONAR_DEFAULT_PROJECT` | The SonarCloud project key to test against |

Run them with:

```bash
pytest -m integration
```

## Usage examples

Once registered, Claude can call tools directly:

> "What's the quality gate status for project my-app in org my-org?"

> "Show me all blocker and critical bugs in project my-app."

> "Give me an issue summary for my-app — how many open issues by severity?"

## Roadmap

### HTTP retries and observability
This project now implements a small internal retry/backoff strategy for SonarCloud API calls in SonarClient.

- Retries: network errors, 5xx responses, and 429 rate-limits
- Defaults: max_retries=3, base_backoff=0.5s, max_backoff=10s, jitter=20%
- Honors the `Retry-After` header when returned by SonarCloud (integer seconds or RFC 2822 date)
- Optional `metrics_hook` parameter on SonarClient accepts a callable receiving metrics events: `"retry_attempt"` and `"retry_give_up"` with a dict payload

**Known quirk:** `Retry-After` date strings formatted with a `-0000` timezone offset are parsed by Python's `email.utils.parsedate_to_datetime` as naive datetimes, which cannot be subtracted from `datetime.now(UTC)` (offset-aware). This causes a `TypeError` that is silently caught, and the delay falls back to `_backoff_delay`. RFC 2822 dates with a `GMT` or `+0000` offset parse correctly.

Observability: retry attempts are logged at WARNING level and give-up events at ERROR level. The retry behavior can be configured via SonarClient constructor parameters.



| Feature | Status |
|---------|--------|
| Project setup and documentation | Done |
| Pydantic models for SonarCloud API responses | Done |
| `get_quality_gate` tool | Done |
| `get_issues` tool | Done |
| `get_issue_summary` tool | Done |
| Integration tests against real SonarCloud API | Done |
| Register server with Claude Code | Done |
| Deep links to SonarCloud UI in tool responses | Done |
| Standardized error handling for SonarCloud API | Done |
| `list_projects` tool | Done |
| Security scanning with pip-audit and bandit | Done |
| Smart TTL-based caching for API responses | Done |
| Configurable logging via `LOG_LEVEL` env var | Done |
| `SONAR_DEFAULT_PROJECT` fallback in tools | Done |
| Snapshot test for MCP tool schemas | Done |
| In-process MCP protocol component tests | Done |

## Project structure

```
sonar-mcp/
├── src/
│   └── sonar_mcp/
│       ├── __init__.py
│       ├── __main__.py       # MCP server entry point
│       ├── client.py         # SonarCloud HTTP client
│       ├── exceptions.py     # Shared exception types
│       ├── models.py         # Pydantic request/response models
│       └── tools/
│           ├── __init__.py
│           ├── issues.py
│           ├── projects.py
│           └── quality_gate.py
├── tests/
│   ├── snapshots/
│   │   └── tool_schemas.json # Committed snapshot of MCP tool schemas
│   ├── conftest.py
│   ├── test_client.py
│   ├── test_issues.py
│   ├── test_main.py
│   ├── test_mcp_protocol.py
│   ├── test_projects.py
│   ├── test_quality_gate.py
│   └── test_tool_schemas.py
├── pyproject.toml
├── .env.example
├── .gitignore
├── AGENTS.md
├── CLAUDE.md
├── CLAUDE_SECURITY.md
└── README.md
```
