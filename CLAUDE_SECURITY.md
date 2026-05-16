# CLAUDE_SECURITY.md — sonar-mcp

> **This file is committed to version control. It must not contain confidential information, secrets, passwords, API keys, or tokens of any kind.**

Security expectations for all agents and contributors working on this project.

## Credentials and secrets

- **Never log, print, or include the `SONAR_TOKEN` in output, error messages, or test fixtures** — use a placeholder or redacted value in any example output
- **Never hardcode tokens, passwords, or secrets** in source files, test files, or configuration
- **Never commit `.env` files or any file containing real credentials** — `.env` must remain in `.gitignore`
- **Do not create world-readable files containing sensitive data**
- If a secret is accidentally committed, flag it to the user immediately — do not silently remove it and move on

## Git and branch safety

- **Never push directly to `main`** — all changes go via a pull request
- **Never force-push to any shared branch**
- **Never amend or rebase commits that have already been pushed**
- When in doubt about branch state, ask before acting

## Dependencies

- **Do not add new dependencies without checking with the user first** — this includes both runtime and dev dependencies
- When proposing a new dependency, state what it does, why it is needed, and whether a lighter alternative exists
- Pin versions in `pyproject.toml` — do not use unbounded version ranges for direct dependencies

## File system

- **Never delete files outside the project directory** without explicit user confirmation
- **Never overwrite files outside the project directory**
- Do not write to system directories, user home directories, or other projects

## Input handling

- Treat all values passed as tool arguments (project keys, organisation slugs, filter values) as untrusted input — validate via Pydantic before use
- Do not construct shell commands from tool arguments
- Do not pass raw user input directly into HTTP query parameters without validation

## API usage

- Only call the SonarCloud API — do not make HTTP requests to other hosts unless explicitly agreed
- Do not store or cache API responses to disk
- Respect SonarCloud rate limits — do not implement retry loops without backoff

## General

- If an action feels risky or irreversible, stop and ask rather than proceeding
- Security issues found during development should be raised with the user before continuing, not silently fixed and buried in a commit
