# tests/AGENTS.md

pytest with async auto-mode enabled.

## Commands

```bash
uv run pytest tests/unit/                    # Unit tests (fast, mocked)
uv run pytest tests/integration/             # Integration tests (real Infrahub)
uv run pytest -n 4                           # Parallel execution
uv run pytest --cov infrahub_sdk             # With coverage
uv run pytest tests/unit/test_client.py      # Single file
```

## Structure

```text
tests/
├── unit/           # Fast, mocked, no external deps
│   ├── ctl/        # CLI command tests
│   └── sdk/        # SDK tests
│       ├── pool/   # Resource pool allocation tests
│       ├── spec/   # Object spec tests
│       ├── checks/ # InfrahubCheck tests
│       └── ...     # Core SDK tests (client, node, schema, etc.)
├── integration/    # Real Infrahub via testcontainers
├── fixtures/       # Test data (JSON, YAML)
└── helpers/        # Test utilities
```

## Test Patterns

```python
# Async test - NO decorator needed (auto mode)
async def test_async_operation(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="http://localhost:8000/api/graphql",
        json={"data": {"result": "success"}},
    )
    client = InfrahubClient()
    result = await client.execute(query="...")
    assert result is not None

# Sync test
def test_sync_operation():
    client = InfrahubClientSync()
    # ...

# CLI test
def test_cli_command():
    runner = CliRunner()
    result = runner.invoke(app, ["command", "--flag"])
    assert result.exit_code == 0
```

## Boundaries

✅ **Always**

- Use `httpx_mock` fixture for HTTP mocking
- Clean up resources in integration tests

🚫 **Never**

- Add `@pytest.mark.asyncio` (globally enabled)
- Make unit tests depend on external services
