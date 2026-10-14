# Quickstart: Validating `only`

**Feature**: INFP-532 | **Spec**: [spec.md](./spec.md) | **Contract**: [contracts/public-api.md](./contracts/public-api.md)

This guide lists the checks that show the feature works. The contract defines the expected behaviour; this guide does not repeat it.

## Prerequisites

```bash
uv sync --all-groups --all-extras
```

Integration tests need a running Docker daemon (testcontainers).

## 1. Unit tests

```bash
uv run pytest tests/unit/sdk/ -q
```

Expected:

- Every existing query-generation test in `tests/unit/sdk/test_node.py` and `tests/unit/sdk/test_hierarchical_nodes.py` passes without being edited (SC-003).
- The new tests for `only` pass on both clients. They cover query generation, the unchanged query after a schema change, the errors raised before any request, the table of reads that raise, the operations that must not raise, and `fetch(only=...)`.
- `tests/unit/sdk/test_client.py::test_validate_method_signature` passes, so the async and sync signatures match.
- `tests/unit/sdk/test_exceptions_public_names.py` and `tests/unit/sdk/test_exceptions.py` pass with the three new errors registered.

## 2. Integration tests

```bash
uv run pytest tests/integration/ -q -k only
```

Expected: the tests on the animal schema (`infrahub_sdk/testing/schemas/animal.py`) pass on both clients, against a real Infrahub server. They cover a generic kind, an HFID through a relationship and an implementing kind with its own HFID.

## 3. Manual check against a running Infrahub

With a local Infrahub that has the animal schema loaded:

```python
from infrahub_sdk import InfrahubClientSync
from infrahub_sdk.exceptions import FieldNotLoadedError

client = InfrahubClientSync()
dogs = client.all(kind="TestingDog", only=["name", "owner"])
dog = dogs[0]

dog.name.value               # the dog's name
dog.breed.is_loaded          # False
dog.owner.fetch(only=["name"])
dog.owner.peer.name.value    # the owner's name

try:
    dog.breed.value
except FieldNotLoadedError as exc:
    print(exc)               # names TestingDog.breed and only=['name', 'owner']
```

Set `INFRAHUB_ADDRESS` (and `INFRAHUB_API_TOKEN` if needed) before running the script. The queries the SDK sends can be inspected with the client's request recorder, or in the server's GraphQL logs: they contain only `id`, `display_label`, `__typename` and the named fields.

## 4. Lint, types and generated docs

```bash
uv run invoke format lint-code
uv run invoke docs-generate
uv run invoke docs-validate
uv run invoke lint-docs
```

Expected: no errors from ruff, mypy or ty, and the regenerated reference pages under `docs/docs/python-sdk/sdk_ref/` are committed.
