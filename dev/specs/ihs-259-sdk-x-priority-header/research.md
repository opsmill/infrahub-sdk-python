# Research: SDK `X-Priority` Request Header

**Feature**: IHS-259 | **Date**: 2026-07-10

This feature has no external unknowns — the wire contract is fixed by INFP-636 and the PRD. "Research" here is the codebase investigation that fixes the *how*. Each decision below is grounded in existing code (`file:line` references from the current tree).

## Decision 1 — Where the `Priority` enum lives and its shape

- **Decision**: `class Priority(str, enum.Enum)` in `infrahub_sdk/constants.py`, members `HIGH = "high"`, `NORMAL = "normal"`, `LOW = "low"`, plus a case-insensitive `_missing_` classmethod.
- **Rationale**: `constants.py` already hosts `InfrahubClientMode(str, enum.Enum)` (`constants.py:4`) and is already imported by both `config.py` (`config.py:11`) and `client.py`. A `str`-valued enum means `Priority.LOW.value == "high"`-style access gives the exact wire token, and the member *is* a `str` so it slots straight into a headers dict. `_missing_` lets `Priority("LOW")` resolve case-insensitively, which pydantic uses when coercing env/file strings.
- **Alternatives considered**:
  - `infrahub_sdk/enums.py` (`OrderDirection`, `enums.py:4`) — viable, but `constants.py` is the home for *client/config-consumed* enums (`InfrahubClientMode`), which is exactly this case.
  - A `Literal["high","normal","low"]` instead of an enum — rejected: FR-001 explicitly requires a `Priority` enum so callers write `Priority.LOW` and cannot typo the contract.

```python
# infrahub_sdk/constants.py
class Priority(str, enum.Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

    @classmethod
    def _missing_(cls, value: object) -> "Priority | None":
        if isinstance(value, str):
            for member in cls:
                if member.value == value.lower():
                    return member
        return None
```

## Decision 2 — Config field name, type, and validation

- **Decision**: add `priority: Priority | None = Field(default=None, description=...)` to `ConfigBase` in `config.py`. No custom validator needed.
- **Rationale**: `ConfigBase(BaseSettings)` uses `model_config = SettingsConfigDict(env_prefix="INFRAHUB_", ...)` (`config.py:39`), so the field auto-binds to `INFRAHUB_PRIORITY`. Pydantic v2 coerces an incoming string to the enum, invoking `Priority._missing_` for case-insensitive matches (FR-002) and raising `ValidationError` for unknown values (FR-007). Default `None` means "no header" (FR-004). Existing enum fields (`mode`, `config.py:57`; `transport`, `config.py:87`) confirm the pattern; the closest optional-typed field is `api_token: str | None` (`config.py:41`).
- **Config field is `priority`, not `x_priority`**: the PRD names `Config.priority`; the `X-` prefix is a wire concern only.
- **`clone()` (`config.py:278`)** iterates `Config.model_fields` for any field not explicitly listed, so `priority` is carried into clones automatically — no change required there.
- **Alternatives considered**: a `@field_validator("priority", mode="before")` to lowercase strings — redundant once `_missing_` handles case; rejected to keep validation in one place (the enum).

## Decision 3 — How the client-wide default rides every transport

- **Decision**: inject the default into the base header dict in `BaseClient.__init__`, adjacent to the existing auth header:

```python
# infrahub_sdk/client.py  (BaseClient.__init__, ~line 218, after X-INFRAHUB-KEY)
if self.config.priority is not None:
    self.headers["X-Priority"] = self.config.priority.value
```

- **Rationale**: every transport path copies and re-merges `self.headers` before sending — `execute_graphql` (`client.py:1244`), `_execute_graphql_with_file` (`client.py:1329`), `_post` (`client.py:1447`), `_get` (`client.py:1470`), `_get_streaming` (`client.py:1497`), `_post_multipart` (`client.py:1374`), and the object-store paths (`object_store.py:46,69,98,141,164,193`). Putting the default in `self.headers` once means it automatically covers GraphQL, multipart upload, and raw blob `_get`/`_post` (FR-003, SC-001) — including batch and blob paths that get no per-call override — with no per-call-site edits. This is exactly how `X-INFRAHUB-KEY` (`client.py:217-218`) already behaves.
- **Alternatives considered**: adding the header at each of the ~10 call sites — rejected as error-prone and easy to miss a transport (the very failure FR-003 guards against).

## Decision 4 — Where and how the per-request override is applied

- **Decision**: add `priority: Priority | None = None` to `execute_graphql` and `_execute_graphql_with_file` (async at `client.py:1201`/`1290`, sync at `client.py:2181`/`2270`). Immediately after the existing `headers = copy.copy(self.headers or {})` + tracker block, add:

```python
if priority is not None:
    headers["X-Priority"] = priority.value
```

- **Rationale**: these two methods are the single funnel for all GraphQL traffic. `copy.copy(self.headers)` already carries the client default, so `if priority is not None: headers["X-Priority"] = priority.value` computes exactly `resolved = per_request if per_request is not None else client_default` (FR-006): `None` keeps the default (or absence); an explicit value overrides it, including an explicit `NORMAL` stepping *up* from a `low` default (spec edge case, SC-003). Implementing it here means the rule exists twice (async + sync), not at every public method.
- **Alternatives considered**: a shared `_apply_priority(headers, priority)` helper — optional nicety; the two-line inline form mirrors the surrounding tracker code and is clearer in context. Left to implementer discretion; both satisfy the contract.

## Decision 5 — Threading the kwarg through higher-level methods

- **Decision**: higher-level methods gain `priority: Priority | None = None` and forward it to the execute methods; they do **not** re-implement resolution.
  - Client: `get` (`client.py:442`), `all`→`filters` (`client.py:905`/`1131`), `create` (`client.py:400`), `create_diff` (`client.py:1695`), `get_diff_summary` (`client.py:1724`), `get_diff_tree` (`client.py:1763`) — and every sync twin.
  - Node: `save` (`node.py:1241`), `create` (`node.py:1602`), `update` (`node.py:1681`), `delete` (`node.py:1214`) — plus sync twins — forward `priority` into `execute_graphql` / `_execute_graphql_with_file`.
- **Rationale**: `get`/`all`/`create` already funnel through `execute_graphql` carrying a `tracker`; adding a parallel `priority` passthrough matches the established shape. Node mutation methods already call the two execute methods (`node.py:1657-1678`), so they only need to forward the new kwarg.
- **Out of scope (v1)**: raw `_get`/`_post`/`_get_streaming` and batch mode expose no per-call override — they inherit the default from `self.headers` (spec Out of Scope + Edge Cases). No `priority` kwarg is added to those.
- **Pagination caveat (from critique E2)**: `all()` renders and calls `execute_graphql` per page (`client.py:1131` / sync `client.py:2907`). Forward `priority` inside the pagination loop so every page request carries it, not only page 1. Cover with a multi-page test.
- **Multipart ordering (from critique E3)**: in `_execute_graphql_with_file`, the existing code pops `content-type` from the copied headers for multipart. Apply the `X-Priority` override **after** the copy/pop so it is not lost; the base default in `self.headers` is unaffected because only `content-type` is removed.

## Decision 6 — Testing strategy

- **Decision**: mirror the `X-Infrahub-Tracker` test style — `pytest-httpx`'s `HTTPXMock.add_response(match_headers={"X-Priority": "low"})`, which only matches when the outgoing request carries that header; and negative assertions that no `X-Priority` is present when unconfigured. Parametrize over `["standard", "sync"]` via the existing `BothClients` fixture (`tests/unit/sdk/conftest.py:33-45`) for parity (FR-008/SC-005).
- **Rationale**: `match_headers` is the repo-standard way to assert on outgoing headers (`test_object_store.py:22-29`, `test_client.py:366+`, `test_diff_summary.py:92+`). The `BothClients` fixture is the repo-standard parity harness.
- **Byte-for-byte no-header check (SC-002)**: assert absence via a request captured by the mock (`httpx_mock.get_requests()` → `"x-priority" not in request.headers`), following the direct-header-read style at `test_rate_limit_retry.py:677`.
- **Config validation (SC-004)**: unit tests constructing `Config(priority=...)` with enum, valid strings in mixed case, and an unknown string expecting `pydantic.ValidationError` (assert with `pytest.raises(..., match=...)`).

## Open questions

None. The wire contract, resolution rule, transport coverage, and testing approach are all fixed by the PRD and confirmed against the current code.
