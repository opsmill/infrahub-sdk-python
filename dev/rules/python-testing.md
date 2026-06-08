---
paths:
  - "tests/**/*.py"
---

# Python testing rules

## No `unittest.mock`

Do not use `unittest.mock`, `MagicMock`, or `patch`. The only sanctioned mocking tools are:

- `httpx_mock` (pytest-httpx) — for intercepting HTTP calls at the transport layer
- `monkeypatch` — for patching stdlib functions (for example: `ssl.create_default_context`)

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
with pytest.raises(NodeNotFoundError, match="Could not find node with id"):
    await client.get(kind="NetworkDevice", id="missing")
```

## Fixtures and helpers

- Shared fixtures live in the nearest `conftest.py` to the tests that use them.
- JSON/YAML test data belongs in `tests/fixtures/` and is loaded via `read_fixture()` from `tests/helpers/fixtures.py`.
- Use `change_directory()` and `temp_repo_and_cd()` from `tests/helpers/utils.py` for filesystem-dependent tests.
- Do not duplicate fixture data inline when a fixture file already exists.

## Naming

Do not reference issue numbers, GitHub URLs, or ticket identifiers in test names or docstrings.
