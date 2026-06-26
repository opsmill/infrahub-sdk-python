---
paths:
  - "tests/unit/**/*.py"
---

# Unit test rules

Unit tests cover pure logic, data transformations, schema parsing, and error handling. Use `httpx_mock` to simulate HTTP responses at the transport boundary. Do not substitute a mocked unit test for behaviour that depends on Infrahub's actual server responses — write an integration test for that.

## HTTP mocking with `httpx_mock`

Add the module-level marker when any fixture or test in the file reuses mocked responses:

```python
pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)
```

Use `is_reusable=True` on fixtures that serve multiple tests:

```python
@pytest.fixture
async def mock_branch_list(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"Branch": [...]}},
        match_headers={"X-Infrahub-Tracker": "query-branch-all"},
        is_reusable=True,
    )
    return httpx_mock
```

## Testing both async and sync clients

Use the `BothClients` fixture from `tests/unit/sdk/conftest.py` when behaviour must be verified for both client variants. Parametrize over `["standard", "sync"]`:

```python
@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_branch_list(clients: BothClients, client_type: str, mock_branch_list: HTTPXMock) -> None:
    if client_type == "standard":
        branches = await clients.standard.branch.all()
    else:
        branches = clients.sync.branch.all()
    assert list(branches.keys()) == ["main", "branch01"]
```

Assert the actual expected value. Assertions like `assert result is not None` or `assert result` do not verify behaviour — they only confirm something was returned.

## Test file layout

Mirror the source structure:

```text
infrahub_sdk/client.py           → tests/unit/sdk/test_client.py
infrahub_sdk/ctl/commands/get.py → tests/unit/ctl/test_get.py
```

## No external dependencies

Unit tests must not connect to external services, local file access is fine. If a test requires a running Infrahub instance, it belongs in `tests/integration/`.
