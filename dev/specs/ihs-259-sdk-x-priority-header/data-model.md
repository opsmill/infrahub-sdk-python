# Data Model: SDK `X-Priority` Request Header

**Feature**: IHS-259 | **Date**: 2026-07-10

This feature introduces no persisted data. The "entities" are in-memory types and the wire header. Below: the new/changed types, their fields, validation rules, and the state/resolution logic.

## Entity: `Priority` (new)

A closed enumeration representing request priority. Owned by the SDK; no lifecycle beyond its value.

| Member   | Wire value | Meaning                                                        |
|----------|-----------|----------------------------------------------------------------|
| `HIGH`   | `high`    | Prefer this request; server should protect it under load.      |
| `MEDIUM` | `medium`  | Default server treatment; equivalent to absent header.         |
| `LOW`    | `low`     | Sheddable first; intended for background/bulk workloads.       |

- **Base type**: `str, enum.Enum` — each member *is* its lowercase wire token, so it drops directly into a header dict.
- **Location**: `infrahub_sdk/constants.py` (beside `InfrahubClientMode`).
- **Validation / coercion rules**:
  - Exact string match: `Priority("low") == Priority.LOW`.
  - Case-insensitive match via `_missing_`: `Priority("LOW")`, `Priority("Low")` → `Priority.LOW` (FR-002).
  - Unknown value (`Priority("lowe")`) → `ValueError` (surfaced as `pydantic.ValidationError` at config load) (FR-007).
- **No ordering semantics**: the enum is a closed label set, not a comparable ranking. The SDK does not compare priorities; it only serialises the resolved value.

## Entity: `Config.priority` (extended field)

Extends `ConfigBase` (`infrahub_sdk/config.py`).

| Attribute | Value |
|-----------|-------|
| Field name | `priority` |
| Type | `Priority \| None` |
| Default | `None` (no client-wide default → header omitted) |
| Env var | `INFRAHUB_PRIORITY` (via `env_prefix="INFRAHUB_"`) |
| Accepts | a `Priority` value, or a case-insensitive string (`"high"/"medium"/"low"`, any case) |
| Validation | pydantic + `Priority` enum; unknown value → `ValidationError` at load time |
| Carried by `clone()` | Yes (automatic — `clone()` iterates `Config.model_fields`) |

- **Meaning of values**:
  - `None` → no client-wide default; no header unless a per-request override is given.
  - `Priority.X` → every request from this client carries `X-Priority: x` unless overridden per request.

## Entity: Base request headers `self.headers` (extended)

The client's base header dict, built once in `BaseClient.__init__` (`infrahub_sdk/client.py`).

- **Before**: `{"content-type": "application/json"[, "X-INFRAHUB-KEY": <token>]}`.
- **After**: additionally `"X-Priority": <config.priority.value>` **iff** `config.priority is not None`.
- **Invariant (FR-004/SC-002)**: when `config.priority is None`, the dict is byte-for-byte what it is today — no `X-Priority` key.
- Every transport copies this dict per request, so the default rides all of them.

## Entity: `X-Priority` wire header (new, external contract)

| Attribute | Value |
|-----------|-------|
| Header name | `X-Priority` (exact) |
| Value | one of `high` / `medium` / `low` (lowercase) |
| Presence | present only when the resolved priority is non-`None` |
| Server semantics (per INFP-636) | case-insensitive; absent or unknown treated as `medium` |

See [contracts/x-priority-header.md](./contracts/x-priority-header.md).

## Resolution logic (the core rule)

Per request, the emitted header is determined by:

```text
resolved = per_request if per_request is not None else client_default
if resolved is None:  omit the X-Priority header
else:                 send  X-Priority: resolved.value
```

Realised in code as: the client default is already in the copied `self.headers`; then `if per_request is not None: headers["X-Priority"] = per_request.value`.

### Resolution truth table

| Client default | Per-request arg | Emitted header        |
|----------------|-----------------|-----------------------|
| `None`         | `None`          | *(none)*              |
| `None`         | `HIGH`          | `X-Priority: high`    |
| `None`         | `MEDIUM`        | `X-Priority: medium`  |
| `LOW`          | `None`          | `X-Priority: low`     |
| `LOW`          | `HIGH`          | `X-Priority: high`    |
| `LOW`          | `MEDIUM`        | `X-Priority: medium`  (explicit step-up wins) |
| `MEDIUM`       | `None`          | `X-Priority: medium`  |
| `HIGH`         | `LOW`           | `X-Priority: low`     |

- There is no per-request way to force "send no header" once a default is set; passing `MEDIUM` explicitly is the accepted equivalent (spec Edge Cases).
- A per-request value never mutates client state — the next un-annotated call reverts to the client default (SC-003).

## Coverage of the per-request override

| Surface | Client default rides it? | Per-request `priority=` override? |
|---------|--------------------------|-----------------------------------|
| `execute_graphql` + file variant | Yes | **Yes** |
| `get`, `all`, `filters`, `count` | Yes | **Yes** |
| diff methods (`create_diff`, `get_diff_summary`, `get_diff_tree`) | Yes | **Yes** |
| node `save` / `create` / `update` / `delete` | Yes | **Yes** (forwarded) |
| resource-pool peer fetch within a node create/update | Yes | **Yes** (inherits the operation's `priority`) |
| `client.create` (builds an unsaved node, issues no request) | n/a | No (nothing to send) |
| raw blob `_get` / `_post` / `_get_streaming` | Yes | No (v1) |
| batch mode | Yes | No (v1) |
