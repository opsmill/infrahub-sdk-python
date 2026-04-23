---
paths:
  - "tests/integration/**/*.py"
---

# Integration test rules

Integration tests run against a real Infrahub instance via testcontainers. Use them for anything that depends on Infrahub's actual behaviour: node creation, branch operations, schema loading, queries. Do not use `httpx_mock` in integration tests.

## Test class structure

Inherit from `TestInfrahubDockerClient` and mix in a schema class when your tests require a custom schema. Use class-scoped fixtures for dataset setup so Infrahub is only populated once per test class:

```python
class TestInfrahubNode(TestInfrahubDockerClient, SchemaAnimal):
    @pytest.fixture(scope="class")
    async def base_dataset(
        self,
        client: InfrahubClient,
        load_schema: None,
    ) -> None:
        await client.branch.create(branch_name="branch01")

    async def test_query_branches(self, client: InfrahubClient, base_dataset: None) -> None:
        branches = await client.branch.all()
        assert "main" in branches
```

## Client fixture

The `client` fixture provides an authenticated `InfrahubClient` connected to the testcontainer instance. Do not construct a client manually in integration tests.

## Cleanup

Clean up any nodes, branches, or schema changes created during a test class. Use class-scoped fixtures with `yield` to ensure teardown runs even on failure:

```python
@pytest.fixture(scope="class")
async def created_branch(self, client: InfrahubClient) -> AsyncGenerator[str, None]:
    await client.branch.create(branch_name="test-branch")
    yield "test-branch"
    await client.branch.delete(branch_name="test-branch")
```
