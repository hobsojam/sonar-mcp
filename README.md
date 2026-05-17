# sonar-mcp

A Model Context Protocol (MCP) server that wraps the SonarCloud REST API, exposing named tools for querying code quality data directly from Claude Code.

## What it does

Registers a set of MCP tools that Claude can call in any session to query SonarCloud without manual HTTP calls or token management. Pass an organization and project key per call, and the server handles auth, request shaping, and response parsing.

## Tools

| Tool | Description |
|------|-------------|
| `get_quality_gate` | Quality gate status and failing conditions for a project |
| `get_issues` | List issues filtered by severity, type, and status |
| `get_issue_summary` | Aggregate issue counts by severity and type |

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

- Python 3.12+
- A SonarCloud account and API token

### 2. Install dependencies

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
```

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

| Feature | Status |
|---------|--------|
| Project setup and documentation | Done |
| Pydantic models for SonarCloud API responses | Done |
| `get_quality_gate` tool | Done |
| `get_issues` tool | Done |
| `get_issue_summary` tool | Done |
| Integration tests against real SonarCloud API | Done |
| Register server with Claude Code | Done |
| Smart TTL-based caching for API responses | Done |

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
│   ├── conftest.py
│   ├── test_client.py
│   ├── test_issues.py
│   ├── test_main.py
│   ├── test_projects.py
│   └── test_quality_gate.py
├── pyproject.toml
├── .env.example
├── .gitignore
├── AGENTS.md
├── CLAUDE.md
├── CLAUDE_SECURITY.md
└── README.md
```
