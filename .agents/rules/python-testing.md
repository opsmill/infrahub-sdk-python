---
paths:
  - "tests/**/*.py"
---

# Python testing rules

## No `unittest.mock`

Do not use `unittest.mock`, `MagicMock`, or `patch`. The only sanctioned mocking tools are:

- `httpx_mock` (pytest-httpx) — for intercepting HTTP calls at the transport layer
- `monkeypatch` — for patching stdlib functions (for example: `ssl.create_default_context`)

Everything else is substituted by injecting a real implementation of the collaborator's interface, which [the component design rules](./component-design.md) exist to make possible. Two doubles are worth writing for an injected collaborator: a `Recording*` one that keeps the calls in order (assert the exact sequence and values, not "was called"), and - where the code claims to survive that collaborator failing - a `Failing*` one that raises, to prove the claim.

Time is handled the same way: a component that needs the current time takes it as a parameter (`now: datetime | None = None`) so tests pass a fixed value, rather than patching the clock.

## Async tests

`asyncio_mode = "auto"` is configured globally. Do not add `@pytest.mark.asyncio`. Do not add loop scope markers manually — this is handled in `conftest.py`.

```python
# Correct
async def test_client_fetches_branch(httpx_mock: HTTPXMock) -> None:
    ...

# Wrong — decorator not needed
@pytest.mark.asyncio
async def test_client_fetches_branch(httpx_mock: HTTPXMock) -> None:
    ...
```

## Parametrized tests

Use a dataclass with `name` as the first field and pass it as the `id` in `pytest.param`. Always use keyword arguments when constructing cases:

```python
@dataclass
class BranchCase:
    name: str
    branch_name: str
    expected_conflict: bool

BRANCH_CASES = [
    BranchCase(name="no-conflict", branch_name="feature-x", expected_conflict=False),
    BranchCase(name="conflict", branch_name="main", expected_conflict=True),
]

@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in BRANCH_CASES])
async def test_branch_conflict(case: BranchCase) -> None:
    ...
```

## Exception assertions

Always pass `match=` to `pytest.raises()`:

```python
with pytest.raises(Error, match=r"^Cannot use an unsaved node as the graph traversal source; save it first\.$"):
    await client.traverse_paths(source=unsaved_node, destination=saved_node)
```

Make `match` cover the whole stable message, anchored with `^...$` where practical, rather than a short fragment. A fragment keeps passing even when the rest of the wording regresses. Match only a substring when the message has a genuinely variable part (an id, a path, a count) that cannot be pinned down.

## Assert exact expectations

Assert the exact value, the exact collection (full list, set or dict equality, not `in` or `issubset`), and the exact message. Never assert mere existence or non-emptiness - `assert result is not None`, `assert result` and `len(result) > 0` all pass while the behaviour under test is broken. Where a count matters, assert the number, so a run that silently measures zero fails.

Pin literal expected values. Never compute the expectation with the same serializer, query builder, or library call the implementation uses - that only asserts the code agrees with itself.

A test for a rejected operation must also read the target back and assert nothing changed.

## Don't test the framework

Skip tests that only exercise library behaviour: plain `Enum` value or round-trip checks, pydantic field constraints (`ge`, `min_length`, ...), `SettingsConfigDict` env plumbing, or "the model has field X". Rule of thumb: if the test would still pass after deleting our implementation and reinstalling the library, it belongs to the library.

Testing that *our* config maps a specific env var onto a specific field, or that a validator we wrote rejects a value, is ours and is worth a test. Testing that pydantic enforces `ge=0` is not.

## Pick the cheapest test tier

If the logic needs only in-memory inputs (a schema object, a dataclass, a pure function), write a unit test with no `httpx_mock` and no client at all - don't reach for a mocked client because a neighbouring test uses one. Reserve `tests/integration/` for behaviour that genuinely depends on a running Infrahub; starting a testcontainer to exercise a pure function costs minutes on every CI run.

## Don't leak process-global state

Tests share one interpreter, and a run may be distributed across xdist workers (`-n`, `--dist loadscope`), so anything left behind changes the outcome of whichever test runs next. Touch `logging` levels, handlers or filters, module-level registries and singletons, `sys.modules`, the working directory, or environment variables only through `monkeypatch`, which restores for you, or a save/restore fixture (change it, `yield`, restore it). `clean_env_vars` in `tests/conftest.py` is the shape to copy.

Install only the piece under test, and remove it after the `yield`. Never call an application-wide initialisation routine from a test body: it owns the whole process, undoes nothing, and reconfigures every later test in that worker.

## Fixtures and helpers

- Shared fixtures live in the nearest `conftest.py` to the tests that use them.
- JSON/YAML test data belongs in `tests/fixtures/` and is loaded via `read_fixture()` from `tests/helpers/fixtures.py`.
- Use `change_directory()` and `temp_repo_and_cd()` from `tests/helpers/utils.py` for filesystem-dependent tests.
- Do not duplicate fixture data inline when a fixture file already exists.

## Naming

Do not reference issue numbers, GitHub URLs, or ticket identifiers in test names or docstrings.
