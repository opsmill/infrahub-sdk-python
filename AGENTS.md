# AGENTS.md

Infrahub Python SDK - async/sync client for Infrahub infrastructure management.

## Commands

```bash
uv sync --all-groups --all-extras   # Install all deps
uv run invoke format                # Format code
uv run invoke lint                  # Full pipeline: ruff, yamllint, ty, mypy, markdownlint, vale
uv run invoke lint-code             # All linters for Python code
uv run invoke docs-generate         # Generate all docs (CLI + SDK)
uv run invoke docs-validate         # Check generated docs match committed version
uv run pytest tests/unit/           # Unit tests
uv run pytest tests/integration/    # Integration tests
```

## Tech stack

Python 3.10-3.13, UV, pydantic >=2.0, httpx, graphql-core

## Code pattern

```python
# Always provide both async and sync versions
client = InfrahubClient()           # async
client = InfrahubClientSync()       # sync

node = await client.get(kind="NetworkDevice")
await node.save()
```

## Project structure

```text
infrahub_sdk/
├── client.py           # Main client implementations
├── config.py           # Pydantic configuration
├── node/               # Node system (core data model)
├── ctl/                # CLI (infrahubctl)
└── pytest_plugin/      # Custom pytest plugin
```

## Markdown style

When editing `.md` or `.mdx` files, run `uv run invoke lint-docs` before committing.

Key rules:

- Use `text` language for directory structure code blocks
- Add blank lines before and after lists
- Always specify language in fenced code blocks (`python`, `bash`, `text`)

## Boundaries

✅ **Always**

- Run `uv run invoke format lint-code` before committing Python code
- Run `uv run invoke docs-generate` after creating, modifying or deleting CLI commands, SDK config, or Python docstrings
- Run markdownlint before committing markdown changes
- Follow async/sync dual pattern for new features
- Use type hints on all function signatures

⚠️ **Ask first**

- Adding new dependencies
- Changing public API signatures

🚫 **Never**

- Push to GitHub automatically (always wait for user approval)
- Mix async/sync inappropriately
- Modify generated code (protocols.py)
- Bypass type checking without justification

## Subdirectory guides

- [docs/AGENTS.md](docs/AGENTS.md) - Documentation (Docusaurus)
- [infrahub_sdk/ctl/AGENTS.md](infrahub_sdk/ctl/AGENTS.md) - CLI development
- [infrahub_sdk/pytest_plugin/AGENTS.md](infrahub_sdk/pytest_plugin/AGENTS.md) - Pytest plugin
- [tests/AGENTS.md](tests/AGENTS.md) - Testing
