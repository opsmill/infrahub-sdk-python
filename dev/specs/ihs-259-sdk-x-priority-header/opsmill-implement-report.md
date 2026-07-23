# Implementation Report: SDK `X-Priority` Request Header (IHS-259)

**Status**: ✅ DONE

## 1. Header

- **Feature**: SDK `X-Priority` request header (client-wide default + per-request override).
- **Spec dir**: `specs/ihs-259-sdk-x-priority-header/`
- **Base commit**: `6b82d0f` (prep artifacts; tail started here)
- **Head commit**: `2cfe193`
- **Branch**: `dga/feat-x-priority-aa2nd`
- **Tasks**: 35/35 complete (all `[X]`).
- **Wall-clock**: ~1h (implement loop + review + fixes).

## 2. Chunk-by-chunk ledger

| # | Chunk (phase) | Tasks | ✅ / ⚠️ / ❌ | Commit(s) | Notes |
|---|---------------|-------|--------------|-----------|-------|
| 0 | Phase 1 Setup (T001) | 1 | 1 / 0 / 0 | `f4422e5` | Run by orchestrator as preflight; baseline 107 passed. |
| 1 | Phase 2 Foundational (T002–T004) | 3 | 3 / 0 / 0 | `c95dc7a` | `Priority` enum + `_missing_`, export, `Config.priority`. Import smoke-check passed. |
| 2 | Phase 3 US1 (T005–T010) | 6 | 6 / 0 / 0 | `feef536` | Base-header injection; default rides GraphQL/multipart/blob/batch. 14 tests. |
| 3 | Phase 4 US3 (T011–T012) | 2 | 2 / 0 / 0 | `39b566e` | No-header-when-unconfigured; no production change needed. |
| 4 | Phase 5 US2 (T013–T024) | 12 | 10 / 2 / 0 | `af1e6c4` | Per-request override on funnels + high-level + node. **T016/T018 ⚠️ partial**: `client.create` intentionally excluded (issues no request; covered at `node.save`). **Load-bearing merge flip** applied (see §6). 40 tests. |
| 5 | Phase 6 US4 (T025–T027) | 3 | 3 / 0 / 0 | `3feedaa` | Config validation (case-insensitive accept, reject unknown, default None). Justified `# ty: ignore` on deliberate string-coercion tests. |
| 6 | Phase 7 US5 (T028–T029) | 2 | 2 / 0 / 0 | `afbb902` | Parity audit (all wire tests already dual); resolution truth-table parity test (16 cases). |
| 7 | Phase 8 Polish (T030–T035) | 6 | 6 / 0 / 0 | `76b8834` | Docstrings, `docs-generate`+`docs-validate` (green), changelog `1151.added.md`, full-suite run. |

**Review-driven commits** (Phase 6): `8ab2964` (HIGH fix), `2cfe193` (Medium test-gap closure).

## 3. Tasks not completed

None. All 35 tasks are `[X]`.

- **Nuance (not incomplete)**: T016/T018 deliberately excluded `client.create` from the `priority=` kwarg. Reason (from the subagent, confirmed by the code review): `client.create` only constructs an unsaved `InfrahubNode` and issues no HTTP request — the create request is made by `node.save()`/`node.create()`, which DO carry `priority` (T019/T020, tested). Adding an unused kwarg to `client.create` would be a misleading no-op and a lint error. FR-005's "create" surface is therefore satisfied at the request-issuing layer.

## 4. Local-pass evidence

All tests added/modified by this run, observed passing locally (unit; project has no locally-runnable E2E — the "E2E scenario" in the PRD is realized as unit wire-assertions). Aggregated from chunk subagents; final consolidated run: `tests/unit/sdk/ → 1145 passed`.

| Test id | Type | Run command | Passed at (ISO 8601) | Env | Verbatim pass line |
|---------|------|-------------|----------------------|-----|--------------------|
| `test_config.py::test_invalid_priority_rejected` | unit | `uv run pytest tests/unit/sdk/test_config.py -q` | 2026-07-11T14:47:13Z | n/a | `Pytest: 25 passed` |
| `test_config.py::test_priority_case_insensitive_acceptance` (12 params) | unit | `uv run pytest tests/unit/sdk/test_config.py -q` | 2026-07-11T14:47:13Z | n/a | `Pytest: 25 passed` |
| `test_config.py::test_priority_from_env_var` (3 params) | unit | `uv run pytest tests/unit/sdk/test_config.py -q` | 2026-07-11T14:47:13Z | n/a | `Pytest: 25 passed` |
| `test_config.py::test_priority_default_is_none` | unit | `uv run pytest tests/unit/sdk/test_config.py -q` | 2026-07-11T14:47:13Z | n/a | `Pytest: 25 passed` |
| `test_priority.py::test_priority_header_on_graphql_query` (×2 clients) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_priority_header_on_graphql_mutation` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_priority_header_on_blob_download` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_priority_header_on_blob_upload` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_priority_header_on_multipart_upload` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_priority_header_on_batched_requests` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_priority_medium_is_always_emitted` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_no_priority_header_on_graphql_when_unconfigured` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_no_priority_header_on_blob_download_when_unconfigured` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_no_priority_header_on_blob_upload_when_unconfigured` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_no_priority_header_on_multipart_upload_when_unconfigured` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_unconfigured_headers_unchanged_versus_baseline` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_no_default_client_then_no_leak` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_beats_default_then_reverts` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_medium_beats_low_default` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_get` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_all_carries_on_every_page` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_save_create_path` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_save_update_path` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_node_delete` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_diff_method` (create_diff, ×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_get_diff_summary` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_get_diff_tree` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_override_on_multipart_upload` (×2) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_priority.py::test_resolution_truth_table_parity` (16 params) | unit | `uv run pytest tests/unit/sdk/test_priority.py -q` | 2026-07-11T15:12:59Z | n/a | `Pytest: 64 passed` |
| `test_relogin_headers.py::test_relogin_retry_uses_refreshed_auth_header` (×2) | unit | `uv run pytest tests/unit/sdk/test_relogin_headers.py -p no:cacheprovider` | 2026-07-11T15:08:18Z | n/a | `4 passed in 0.02s` |
| `test_relogin_headers.py::test_merge_request_headers_reasserts_live_auth` (×2) | unit | `uv run pytest tests/unit/sdk/test_relogin_headers.py -p no:cacheprovider` | 2026-07-11T15:08:18Z | n/a | `4 passed in 0.02s` |

**Consolidated final runs**: `tests/unit/sdk/ → 1145 passed` (2026-07-11); full `tests/unit/ → 1588 passed, 8 failed, 1 xfailed` — the 8 failures are **pre-existing** (`ctl/` menu/repo/schema/task app CLI-rendering + `pytest_plugin` fixture), fail identically on base `6b82d0f`, and none reference priority.

## 5. Review findings

Dual-lens review (correctness/types/errors, tests, comments/simplify) across `6b82d0f..HEAD`.

| Severity | File | Summary | Disposition |
|----------|------|---------|-------------|
| 🔴 High | `client.py` (8 transport helpers) | Merge-order flip let a stale per-request header snapshot overwrite the freshly-refreshed `Authorization` on the relogin retry → password-auth token-refresh broken. | **Fixed inline** (`8ab2964`) — added `BaseClient._merge_request_headers` re-asserting live auth after the per-request merge; regression test proves it (removing fix → 4 failures). |
| 🟡 Medium | `test_priority.py` | Node `delete()` per-request override untested on the wire. | **Fixed inline** (`2cfe193`). |
| 🟡 Medium | `test_priority.py` | `save()` update-path override untested (only create branch). | **Fixed inline** (`2cfe193`). |
| 🟢 Low | `test_priority.py` | Only `create_diff` of the 3 diff methods tested. | **Fixed inline** (`2cfe193`) — added summary + tree. |
| 🟢 Low | `client.py` | `get`/`create_diff`/`get_diff_summary` have no docstring, so `priority` is undocumented there (pre-existing lack of docstrings; feature widens the gap). | **Deferred** — cosmetic; matches existing docstring density. |
| 🟢 Low | `node.py` | Node docstrings omit the "when None → client default" sentence the client docstrings include. | **Deferred** — accurate, just terser. |
| 🟢 Low (advisory) | `client.py` | `if priority is not None: headers[...] = ...` duplicated across 4 funnels; a helper could remove it + the `# noqa: PLR0912`. | **Deferred** — advisory; async/sync split limits gains. |

Positive observations from review: `Priority._missing_` correct (case-insensitive, no recursion, non-str safe); resolution applied exactly once per funnel; async/sync parity complete; type hints clean; no silent failures; test assertions are genuinely on-the-wire (a reverted feature would fail the mocks), parity is real (sync path exercised), multi-page `all` truly asserts every page.

## 6. Autonomous decisions

1. **Ran T001 in the orchestrator** (env sync + baseline) rather than dispatching a subagent for a one-line check; ticked it with a fixup commit.
2. **`client.create` excluded from `priority=`** (T016/T018 ⚠️): it issues no request; the create request path (`node.save`/`create`) carries priority and is tested. Review confirmed this is correct and no request-issuing FR-005 surface was missed.
3. **Merge-order flip** (chunk 4): the subagent discovered the transport helpers let base `self.headers` overwrite per-request headers (defeating the override) and flipped precedence. This was load-bearing and correct for the feature — but the review then caught that it broke the relogin auth-refresh path; the final fix (`_merge_request_headers`) preserves BOTH invariants (per-request wins for non-auth keys; live auth always wins). Full suite confirms no regression.
4. **Closed two Medium + one Low test gap inline** (`2cfe193`) although the workflow only mandates inline fixes for High+. Rationale: these are the core override surfaces; an untested forwarding call site could silently regress. Cheap, low-risk, high-value. No production bug was found while doing so.
5. **Deferred the Low docstring/simplify findings** — cosmetic, no correctness impact; recorded above for a follow-up.
6. **`docs-generate` drift**: regeneration also touched 8 unrelated `.mdx` files already stale vs. the generator; all regenerated output was committed so `docs-validate` stays green (the only way to keep it passing).

## 7. Suggested next steps

1. **Open a PR** for `dga/feat-x-priority-aa2nd` → `stable` (this is a public-API change per IHS-259 governance; the PR description should call that out).
2. (Optional) Address the deferred Low findings: add one-line docstrings with the `priority` Args entry to `get`/`create_diff`/`get_diff_summary`, and consider the `_apply_priority` helper to drop the two `# noqa: PLR0912`.
3. The 8 pre-existing `ctl`/`pytest_plugin` unit failures are unrelated to this feature but exist on `stable`'s merge-base — worth a separate ticket if not already tracked.
4. Run `speckit-opsmill-extract` if you want ADRs/guidelines mined from this spec dir.
