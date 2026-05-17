# CLAUDE.md — sonar-mcp

> **This file is committed to version control. It must not contain confidential information, secrets, passwords, API keys, or tokens of any kind.**

## Security

All security expectations are documented in [CLAUDE_SECURITY.md](CLAUDE_SECURITY.md). Read it before making any changes. It covers credentials, branch safety, dependencies, file system boundaries, and API usage.

## Project overview

A Python MCP server wrapping the SonarCloud REST API. Exposes named tools (`get_quality_gate`, `get_issues`, `get_issue_summary`) so Claude can query SonarCloud directly in any session without manual HTTP calls.

## How we work

**Ask before implementing.** Do not start writing code, scaffolding files, or making structural decisions without agreement from the user. When facing a choice — project layout, API design, error handling approach, test strategy — ask first. One focused question is better than a long list of options or an unsolicited implementation.

**TDD.** Tests are written before implementation. The workflow is:
1. Model the SonarCloud API response shapes in Pydantic
2. Write tests that describe the expected tool behaviour
3. Implement until the tests pass

**Agree on scope before each piece of work.** Confirm what we're building in a given session before touching any file.

## Code standards

- **mypy strict mode** — all code must pass `mypy --strict`. No `Any` unless genuinely unavoidable and documented.
- **Pydantic models** for all SonarCloud request parameters and API responses — no raw dicts crossing boundaries.
- **ruff** for linting and formatting.
- **Tests use `pytest` + `pytest-asyncio` + `respx`** — mock only at the HTTP boundary, never internal code. `asyncio_mode = "auto"` configured in `pyproject.toml`. Test names should read as specifications.
- **No comments explaining what the code does** — names should do that. Only comment when the *why* is non-obvious: a hidden constraint, an API quirk, a workaround.
- **No speculative abstractions** — build what is needed now. Don't design for hypothetical future tools or providers.
- **No unnecessary error handling** — validate at the boundary (SonarCloud HTTP responses). Trust internal code.

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

## Project structure

```
sonar-mcp/
├── src/
│   └── sonar_mcp/
│       ├── __init__.py
│       ├── __main__.py       # MCP server entry point
│       ├── client.py         # SonarCloud HTTP client
│       ├── models.py         # Pydantic request/response models
│       └── tools/
│           ├── quality_gate.py
│           └── issues.py
├── tests/
│   ├── conftest.py
│   ├── test_quality_gate.py
│   └── test_issues.py
├── pyproject.toml
├── .env.example
├── .gitignore
├── AGENTS.md
├── CLAUDE.md
├── CLAUDE_SECURITY.md
└── README.md
```

## Configuration

The server reads from environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SONAR_TOKEN` | Yes | SonarCloud API token |
| `SONAR_DEFAULT_ORG` | No | Default organization slug |
| `SONAR_DEFAULT_PROJECT` | No | Default project key |

`organization` and `project_key` can be passed as tool arguments and will override the defaults.

## SonarCloud API

Base URL: `https://sonarcloud.io/api`

Authentication: HTTP Basic auth with the token as the username and an empty password.

Key endpoints:
- `GET /qualitygates/project_status` — quality gate status
- `GET /issues/search` — issues list

## Definition of done for each tool

- Pydantic models for input parameters and API response
- Tests written first, covering happy path and key error cases (401, 404, malformed response)
- Implementation passes all tests
- mypy strict passes
- ruff passes

## Git Workflow

- Each new feature must be developed on its own branch, branched from `main`.
- Branch naming: `feat/<short-description>` (e.g. `feat/quality-gate-tool`).
- Every feature branch must have its own PR targeting `main` before being merged.
- **Never commit feature work directly to `main`.**
- **Before any non-trivial new work**, always run `git pull origin main` and merge any changes into the current branch before proceeding. Do not start new work on a stale branch.
- **Before creating a new branch**, always `git pull origin main` first so the branch starts from the latest main. Never branch from a stale local main.
- **Before switching branches**, always commit and push all finished work on the current branch. If there are uncommitted changes that are not ready to commit (broken, incomplete, or uncertain), do not switch branch silently — ask the user whether to stash, discard, or fix them first.
- **Always include the co-author trailer** in every commit message:
  ```
  Co-Authored-By: Claude Code <noreply@anthropic.com>
  ```

## Documentation

- Work is tracked in GitHub Issues — do not create local task files or checklists.
- **Any suggested improvement, inconsistency, or problem noticed during work must be filed as a GitHub issue immediately**, even if it is out of scope for the current task. Use `gh issue create --repo hobsojam/sonar-mcp`. Do not mention it only in a PR description or conversation and move on.
- **Always update `README.md` when a feature is completed** — mark it as done in the roadmap and update the project structure if new files were added.
- Documentation updates must be committed on the same branch as the feature work, before the PR is created.
