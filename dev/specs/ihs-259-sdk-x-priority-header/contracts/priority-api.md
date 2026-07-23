# API Contract: Priority public surface

**Feature**: IHS-259 | **Scope**: SDK public Python API (async + sync). This is a public-API-signature change (governance-approved in IHS-259).

## New public symbol: `Priority`

```python
from infrahub_sdk.constants import Priority

class Priority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
```

- `str`-valued closed enum. `Priority("LOW") is Priority.LOW` (case-insensitive via `_missing_`).
- Unknown values raise `ValueError` (→ `pydantic.ValidationError` at config load).
- Imported from `infrahub_sdk.constants` (kept out of the top-level `infrahub_sdk` namespace so importing the enum does not pull in `Config` and the client classes).

## Extended: `Config.priority`

```python
class ConfigBase(BaseSettings):
    ...
    priority: Priority | None = Field(
        default=None,
        description="Default request priority emitted as the X-Priority header on every request. "
                    "One of high|medium|low (case-insensitive). When unset, no header is sent.",
    )
```

- Env var: `INFRAHUB_PRIORITY`.
- Accepts a `Priority` or a case-insensitive string; unknown → validation error at load.
- Default `None` → no client-wide default.

## Extended method signatures (new `priority` keyword — both `InfrahubClient` and `InfrahubClientSync`)

Each covered method gains `priority: Priority | None = None` (default `None` preserves current behaviour). The argument is keyword-friendly and additive — existing positional/keyword calls are unaffected.

```python
# Client
def get(self, kind, ..., priority: Priority | None = None) -> ...
def all(self, kind, ..., priority: Priority | None = None) -> ...            # forwards to filters + count
def filters(self, kind, ..., priority: Priority | None = None) -> ...
def count(self, kind, ..., priority: Priority | None = None) -> int
def execute_graphql(self, query, ..., priority: Priority | None = None) -> dict
def _execute_graphql_with_file(self, ..., priority: Priority | None = None) -> ...   # file variant
def create_diff(self, ..., priority: Priority | None = None) -> ...
def get_diff_summary(self, ..., priority: Priority | None = None) -> ...
def get_diff_tree(self, ..., priority: Priority | None = None) -> ...

# Node (InfrahubNode / InfrahubNodeSync)
def save(self, ..., priority: Priority | None = None) -> None
def create(self, ..., priority: Priority | None = None) -> None
def update(self, ..., priority: Priority | None = None) -> None
def delete(self, ..., priority: Priority | None = None) -> None
```

> **Note — `client.create` is intentionally NOT extended.** `InfrahubClient.create()` / `InfrahubClientSync.create()` only build an unsaved `InfrahubNode` in memory and issue no HTTP request, so a `priority=` kwarg there would be a no-op. Per-request priority for creating a node is carried by the node-level `save()` / `create()` (which issue the mutation). Within a node create/update, a resource-pool relationship's follow-up peer fetch inherits the same `priority`.

### Behavioural contract per call

- `priority=None` (default): use the client-wide default (which may itself be `None` → no header). No client state is mutated.
- `priority=Priority.X`: this request carries `X-Priority: x`, overriding the client default for this call only. The next un-annotated call reverts to the client default.
- Resolution: `resolved = per_request if per_request is not None else client_default`.

## Explicitly NOT extended (v1)

- `_get`, `_post`, `_get_streaming` (raw blob transfers) — inherit the client default only; no `priority` kwarg.
- Batch mode — inherits the client default only; no per-call override.

## Backwards-compatibility guarantee

- Adding a keyword-only-friendly parameter with a `None` default and a new optional config field is additive. Any existing caller that sets nothing sees no change in outgoing requests (FR-004 / SC-002).
