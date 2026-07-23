# Quickstart / Validation Guide: SDK `X-Priority` Request Header

**Feature**: IHS-259 | **Date**: 2026-07-10

How to exercise and validate the feature end-to-end. See [contracts/priority-api.md](./contracts/priority-api.md) for the API surface and [data-model.md](./data-model.md) for the resolution truth table.

## Prerequisites

```bash
uv sync --all-groups --all-extras
```

## Usage examples (what the feature enables)

### Client-wide default (P1)

```python
from infrahub_sdk import InfrahubClient, Config
from infrahub_sdk.constants import Priority

# A client dedicated to background work tags every request low.
client = InfrahubClient(config=Config(address="http://localhost:8000", priority=Priority.LOW))

# Every request below carries `X-Priority: low` with no call-site changes:
await client.all(kind="BuiltinTag")          # GraphQL
await client.execute_graphql(query=MY_QUERY) # GraphQL
# ...multipart uploads and blob get/post from this client also carry it.
```

Via environment / file config (case-insensitive):

```bash
export INFRAHUB_PRIORITY=LOW   # accepted; normalised to Priority.LOW
```

### Per-request override (P2)

```python
client = InfrahubClient(config=Config(address="http://localhost:8000", priority=Priority.LOW))

# This one user-triggered call steps up to high; the rest stay low.
node = await client.get(kind="BuiltinTag", name__value="blue", priority=Priority.HIGH)

# Explicit MEDIUM beats a LOW default for this call only:
await client.execute_graphql(query=MY_QUERY, priority=Priority.MEDIUM)  # -> X-Priority: medium
```

### Zero behaviour change when unconfigured (P1)

```python
client = InfrahubClient(config=Config(address="http://localhost:8000"))  # no priority
await client.all(kind="BuiltinTag")  # NO X-Priority header — identical to pre-feature SDK
```

### Invalid value rejected at config load (P2)

```python
Config(address="http://localhost:8000", priority="lowe")  # raises pydantic.ValidationError
```

## Validation scenarios (map to Success Criteria)

Run the unit suite:

```bash
uv run pytest tests/unit/sdk/test_priority.py tests/unit/sdk/test_config.py \
              tests/unit/sdk/test_client.py tests/unit/sdk/test_object_store.py -q
```

| Scenario | How it is asserted | Criterion |
|----------|--------------------|-----------|
| Default rides GraphQL, multipart, blob | `httpx_mock.add_response(match_headers={"X-Priority": "low"})` for each transport; request only matches if header present | SC-001 |
| Unconfigured client emits no header | capture request via `httpx_mock.get_requests()`, assert `"x-priority" not in request.headers` | SC-002 |
| Per-request override, then revert | override call matches `{"X-Priority": "high"}`; next un-annotated call matches the default (or no header) | SC-003 |
| Explicit `MEDIUM` beats `LOW` default | override call matches `{"X-Priority": "medium"}` | SC-003 (edge) |
| Invalid value rejected | `pytest.raises(pydantic.ValidationError, match=...)` on `Config(priority="lowe")` | SC-004 |
| Case-insensitive config accepted | `Config(priority="LOW").priority is Priority.LOW` | FR-002 |
| Async/sync parity | parametrize every wire test over `["standard", "sync"]` via the `BothClients` fixture | SC-005 |

## Full quality gate (run before commit)

```bash
uv run invoke format lint-code
uv run invoke docs-generate      # required: new Config field + docstrings
uv run invoke docs-validate
uv run pytest tests/unit/
```

## Expected outcomes

- All new unit tests pass for both `standard` and `sync` clients.
- `docs-validate` passes (generated docs include the new `Config.priority` field).
- No change to any test that exercises an unconfigured client (backwards compatibility intact).
