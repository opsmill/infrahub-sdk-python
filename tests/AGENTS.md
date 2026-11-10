# tests/AGENTS.md

pytest with async auto-mode enabled.

## Commands

```bash
uv run pytest tests/unit/                    # Unit tests (fast, mocked)
uv run pytest tests/integration/             # Integration tests (real Infrahub)
uv run invoke tests-integration --shard listed  # One CI shard of the integration tests (listed or other)
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

## Integration test shards

CI runs the integration tests in two parallel jobs, because a single job took about 30 minutes, close to the job timeout. Each job runs one shard:

- `listed`: the files in `INTEGRATION_TEST_SHARDS` in `tasks.py`.
- `other`: every other file in `tests/integration/`. A new test file runs here without any change to `tasks.py`.

The files are grouped only to give the two jobs about the same duration. Most of the time goes to starting Infrahub: each test class starts its own Infrahub instance, which takes 40 to 70 seconds before its first test.

### Move files between shards

Move files between shards when one job takes more than about 5 minutes longer than the other:

1. Get the durations from the latest CI run on `stable`. Running the suite locally takes about 30 minutes and needs Docker, so use CI.

   ```bash
   gh run list --workflow ci.yml --branch stable --limit 1
   gh run view <run-id> --json jobs --jq '.jobs[] | select(.name | startswith("integration-tests")) | "\(.name) \(.startedAt) \(.completedAt)"'
   gh run view --job <job-id> --log
   ```

2. In each job log, read the `slowest durations` table that `--durations=0` prints at the end of the pytest output. Add up the `setup` and `call` times for each file.
3. Move files into or out of `INTEGRATION_TEST_SHARDS["listed"]` in `tasks.py` so that both shards have about the same total.
4. No other change is needed. The `other` shard ignores exactly the listed files, so every test still runs in one shard. A misspelled or deleted file name in the list makes the `listed` job fail with `file or directory not found`.

To add a third shard, add a key to `INTEGRATION_TEST_SHARDS` and the same name to the `shard` matrix of the `integration-tests-latest-infrahub` job in `.github/workflows/ci.yml`. A shard that is missing from the matrix never runs in CI.

Both shards upload coverage to Codecov with the `integration-tests` flag. Codecov merges the uploads for a commit, so the flag covers the whole suite.

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

The timing matters. Rich snapshots `no_color` when a `Console` is constructed, and treats a set
`FORCE_COLOR` as proof it is writing to a terminal — on Rich 12.6 through 13 *any* value, the
empty string included; from Rich 14 any non-empty value. Removing the variable is the only strategy correct on
both, which is why the hook removes it rather than overriding it. Many `infrahub_sdk.ctl` modules
build a module-level `Console()`, which runs during collection, so a fixture or an env override
passed to `CliRunner.invoke()` is already too late for those consoles.

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
