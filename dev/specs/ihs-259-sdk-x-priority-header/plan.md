# Implementation Plan: SDK `X-Priority` Request Header

**Branch**: `dga/feat-x-priority-aa2nd` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/ihs-259-sdk-x-priority-header/spec.md`

## Summary

Add a first-class request-priority concept to the SDK, emitted as an `X-Priority: high|normal|low` HTTP header. Two configuration surfaces: a client-wide default via `Config.priority` (rides every transport by being injected into the client's base `self.headers`) and a per-request `priority=` keyword argument on the covered public methods (resolved as `per_request if per_request is not None else client_default`). When nothing is configured, no header is emitted — byte-for-byte identical to today. Both `InfrahubClient` (async) and `InfrahubClientSync` (sync) behave identically. No server-side logic, no 429 handling.

**Technical approach** (grounded in the existing `X-Infrahub-Tracker` prior art):

1. New `Priority(str, enum.Enum)` in `infrahub_sdk/constants.py` with members `HIGH="high"`, `NORMAL="normal"`, `LOW="low"` and a case-insensitive `_missing_` classmethod.
2. New `Config.priority: Priority | None = None` field (auto-binds to `INFRAHUB_PRIORITY` via the existing `env_prefix`). Pydantic + the enum give validation and case-insensitive string coercion for free; unknown values raise at config load.
3. Inject the configured default once into `BaseClient.__init__`'s base `self.headers` (right next to the `X-INFRAHUB-KEY` line). Because every transport already merges `self.headers`, the default automatically rides GraphQL, multipart upload, and raw blob `_get`/`_post`.
4. Add `priority: Priority | None = None` to `execute_graphql` and `_execute_graphql_with_file` (async + sync). These are the single points where the per-request header is applied: `if priority is not None: headers["X-Priority"] = priority.value` on the already-copied header dict — which realises the resolution rule exactly (a `None` per-request keeps whatever the base default was; an explicit value, including `NORMAL`, overrides it).
5. Thread the `priority` kwarg through the higher-level callers so they forward it to the two execute methods: client `get`, `all` (via `filters`), `create`, `create_diff`/`get_diff_summary`/`get_diff_tree`; node `save`/`create`/`update`/`delete`. Raw blob `_get`/`_post` and batch mode inherit the client default only (no per-call override in v1).

**Two load-bearing details surfaced by the critique** (see [critiques/](./critiques/)):

- **Pagination**: `all()` calls `execute_graphql` once per page via `filters`. The `priority` kwarg must be forwarded on **every** page request, not just the first — covered by a multi-page test.
- **Multipart ordering**: `_execute_graphql_with_file` pops `content-type` from the copied header dict for multipart. `X-Priority` must be applied **after** that pop (and the default already in `self.headers` survives it, since only `content-type` is removed). Covered by an explicit multipart override test.
- **Batch/blob inheritance**: verified by test (SC-006) — a configured default must ride batch-mode and raw blob requests even though neither exposes a per-request override.

## Technical Context

**Language/Version**: Python 3.10–3.13

**Primary Dependencies**: pydantic >=2.0, pydantic-settings, httpx, graphql-core

**Storage**: N/A (stateless HTTP header)

**Testing**: pytest, pytest-httpx (`HTTPXMock` with `match_headers=`), pytest async auto-mode

**Target Platform**: Library consumed by network-automation code, `infrahubctl`, and the Infrahub Ansible collection

**Project Type**: Single-project Python library (async + sync dual client)

**Performance Goals**: No measurable overhead — a single dict insertion per request; no new network round-trips

**Constraints**: Zero behaviour change when unconfigured (byte-for-byte identical headers); async/sync parity; no new dependencies; no changes to generated `protocols.py`

**Scale/Scope**: ~1 new enum, 1 new config field, header injection in `BaseClient.__init__`, and a `priority` kwarg on ~10 public methods across two clients plus the node module

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is an unpopulated template with no ratified principles, so there are no formal constitutional gates to evaluate. In its place, the binding constraints are the repository's `AGENTS.md` boundaries:

- **Async/sync dual pattern (Always)** — satisfied: every change is applied to both clients; FR-008 / User Story 5 make parity a first-class, tested requirement.
- **Type hints on all signatures (Always)** — satisfied: the new enum and every touched signature are fully typed (`Priority | None`).
- **Do not modify generated `protocols.py` (Never)** — satisfied: no generated code is touched.
- **No new dependencies (Ask first)** — satisfied: none added.
- **Changing public API signatures (Ask first)** — this feature *intentionally* changes public signatures (new enum, new config field, new `priority` kwarg). This is the explicit, PRD-approved purpose of the ticket (governance gate checked in IHS-259); documented as an accepted assumption in the spec.
- **Docs regeneration (Always, after config/docstring changes)** — handled: `uv run invoke docs-generate` is a task in Phase 4.

**Result**: PASS (no unjustified violations). Re-checked post-design: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/ihs-259-sdk-x-priority-header/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (public API + wire contract)
│   ├── priority-api.md
│   └── x-priority-header.md
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
infrahub_sdk/
├── constants.py         # ADD: Priority(str, enum.Enum) + case-insensitive _missing_
├── config.py            # ADD: Config.priority field (ConfigBase), imports Priority
├── client.py            # EDIT: BaseClient.__init__ base-header injection;
│                        #       priority kwarg on execute_graphql + _execute_graphql_with_file
│                        #       (async + sync); thread through get/all/filters/create/diff methods
└── node/
    └── node.py          # EDIT: priority kwarg on save/create/update/delete (async + sync),
                         #       forwarded to client execute methods

tests/unit/sdk/
├── test_config.py       # ADD: Config.priority validation (enum/string/case/reject-unknown)
├── test_priority.py     # ADD (new): Priority enum + resolution behaviour
├── test_client.py       # ADD: header-on-the-wire assertions (default, override, omit) both clients
├── test_object_store.py # ADD: blob transports carry the default
└── conftest.py          # reuse BothClients fixture pattern

docs/                    # regenerated via `uv run invoke docs-generate`
```

**Structure Decision**: Single-project library layout (the existing SDK structure). All production changes are confined to `constants.py`, `config.py`, `client.py`, and `node/node.py`; no new modules are required beyond the enum, which lives with the other client enums in `constants.py`.

## Design Decisions (detail)

See [research.md](./research.md) for the full decision log. Highlights:

- **Config field is named `priority`, not `x_priority`** — the PRD specifies `Config.priority`; the `X-` prefix belongs to the wire header, not the config surface. Auto-binds to `INFRAHUB_PRIORITY`.
- **Default injected into base `self.headers`, not at each call site** — this is the mechanism that guarantees FR-003 (every transport) without touching blob/batch code paths, and mirrors how `X-INFRAHUB-KEY` already rides every request.
- **Per-request application lives in `execute_graphql` / `_execute_graphql_with_file` only** — every high-level method funnels through these two, so the resolution rule is implemented once per client (twice total) instead of at ~10 call sites. Higher-level methods only *forward* the kwarg.
- **Resolution is realised by override-if-present on the copied header dict** — `copy.copy(self.headers)` already carries the default; `if priority is not None: headers["X-Priority"] = priority.value` yields exactly `per_request if per_request is not None else client_default`, including the explicit-`NORMAL`-beats-`low`-default edge case.
- **Case-insensitivity via `Priority._missing_`** — handles `LOW`/`Low`/`low` from env/file config and raises for unknown values, satisfying FR-002 and FR-007 with no bespoke validator.

## Complexity Tracking

No constitutional violations to justify — this section is intentionally empty.
