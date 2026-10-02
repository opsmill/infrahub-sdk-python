# Quickstart: Validating Field Selection with `only` and Known-State Access

A run guide that proves the feature works end to end. Contracts are in [contracts/public-api.md](contracts/public-api.md) and the state rules in [data-model.md](data-model.md).

## Prerequisites

```bash
uv sync --all-groups --all-extras
```

Integration scenarios also need Docker for testcontainers.

## 1. Unit suites

```bash
uv run pytest tests/unit/sdk/test_node_selection.py tests/unit/sdk/test_node_field_access.py -q
uv run pytest tests/unit/ -q
```

**Expected**:

- Both new suites pass for every case, each parametrised over the async and sync clients.
- The full unit suite passes with `error::infrahub_sdk.exceptions.FieldNotLoadedWarning` in `filterwarnings`, which proves no SDK-internal path reads an unknown field (FR-027).

## 2. Query shape (SC-001, SC-004, SC-008)

From a unit test or a REPL with a mocked schema:

```python
node = InfrahubNode(client=client, schema=tag_schema, branch="main")
data = await node.generate_query_data(only=["name"])
```

**Expected**: `data["BuiltinTag"]["edges"]["node"]` has exactly `id`, `display_label`, `__typename` and `name`. Without `only`, the envelope no longer contains `hfid`, and everything else matches the previous release. After adding attributes to `tag_schema`, the `only=["name"]` output is unchanged.

## 3. Rejections before any request (SC-006, FR-005)

```python
await client.all(kind="BuiltinTag", only=["name"], include=["description"])  # SelectionConflictError
await client.all(kind="BuiltinTag", only=["nmae"])                           # SelectionFieldNotFoundError: nmae
```

**Expected**: Both raise, and `httpx_mock` records no GraphQL data request.

## 4. Known-state reads (SC-005, SC-007)

```python
tag = (await client.filters(kind="BuiltinTag", exclude=["description"]))[0]
tag.description.is_loaded   # False
tag.description.value       # None + FieldNotLoadedWarning naming exclude=['description']

strict = (await client.filters(kind="BuiltinTag", only=["name"]))[0]
strict.description.value    # FieldNotLoadedError

new = await client.create(kind="BuiltinTag", name="red")
new.description.value       # None, no warning
await new.save()
new.description.value       # FieldNotLoadedWarning (origin unknown)
```

Flip the switch with `monkeypatch.setattr(field_access, "_STRICT_FIELD_ACCESS", True)` and repeat: every warning becomes `FieldNotLoadedError` with the same message, and the "new" read still returns `None` silently.

## 5. Hydration (User Story 3)

```python
group = await client.get(kind="CoreStandardGroup", name__value="g1", only=["members"])
await group.members.fetch(only=["name"])
```

**Expected**: One request per concrete member kind, each selecting `name` only when that kind defines it. `member.peer.name.value` is readable, and any other peer field raises.

## 6. Integration (live server)

```bash
uv run pytest tests/integration/test_node.py -k "only" -q
```

**Expected**: Against a live Infrahub, `only=["name"]` returns nodes exposing `name` and the floor. Reading `description` raises, and hydrating a relationship with `only` makes exactly that peer field readable.

## 7. Lint, types, docs

```bash
uv run invoke format lint-code
uv run invoke docs-generate && uv run invoke docs-validate
uv run invoke lint-docs
```

**Expected**: All pass, and the regenerated `sdk_ref` pages document `only`, `is_loaded` and the hydration parameters.
