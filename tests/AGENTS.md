# tests/AGENTS.md

pytest with async auto-mode enabled.

## Commands

```bash
uv run pytest tests/unit/                    # Unit tests (fast, mocked)
uv run pytest tests/integration/             # Integration tests (real Infrahub)
INFRAHUB_TESTING_FAILOVER=1 uv run pytest tests/integration/test_retry_on_failover.py  # Opt-in failover tests, skipped otherwise
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
- Let `tests/conftest.py` own Rich's rendering environment (see below) instead of pinning
  colour or width per test

🚫 **Never**

- Add `@pytest.mark.asyncio` (globally enabled)
- Make unit tests depend on external services
- Set `TERM=dumb` to disable colour — it pins Rich's width to 80 and ignores `COLUMNS`, which
  truncates the wide tables the CLI-output fixtures record

## CLI output and Rich

Tests that assert on CLI text compare against output whose colour and width Rich decides. Both
are pinned centrally by `pytest_configure` in `tests/conftest.py`, which unsets `FORCE_COLOR`
and sets `NO_COLOR=1` and `COLUMNS=200` before any test module is imported.

The timing matters. Rich snapshots `no_color` when a `Console` is constructed, and treats *any*
`FORCE_COLOR` value — the empty string included — as proof it is writing to a terminal. Many
`infrahub_sdk.ctl` modules build a module-level `Console()`, which runs during collection, so a
fixture or an env override passed to `CliRunner.invoke()` is already too late for those consoles.

Practical consequences:

- A plain `CliRunner()` is fine; it inherits the pinned environment. Pass `env=` only to widen
  `COLUMNS` beyond 200 for a specific test.
- When a test builds its own `Console`, make it explicit —
  `Console(file=StringIO(), width=1000, no_color=True, force_terminal=False)` — so it does not
  depend on the ambient environment at all. Prefer wrapping that in a fixture that patches the
  module-level console and yields it, as `schema_console` in `tests/unit/sdk/test_schema.py`
  does, rather than repeating the `mock.patch` block per test.
- Tests that cover the test infrastructure itself, rather than any SDK behaviour, live in
  `tests/unit/meta/`.
- Prefer fixing the environment over loosening an assertion, so exact-output tests keep their
  value.
