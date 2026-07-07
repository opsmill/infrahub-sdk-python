# Opsmill Implement Report: SDK retry with backoff on HTTP 429 responses

**Status**: ✅ DONE

## 1. Header

- **Feature**: SDK retry with backoff on HTTP 429 responses (Jira IHS-249, GitHub #1124)
- **Spec dir**: `specs/ihs-249-sdk-429-retry/` (real path `dev/specs/ihs-249-sdk-429-retry/`, via the `specs → dev/specs` symlink)
- **Base commit**: `a55cbaa` (prep artifacts, pre-implementation)
- **Head commit**: `8917fb9`
- **Commits produced** (7): `c71238c` (foundational machinery) → `ed0457c` (US1) → `32abfd5` (US2) → `d309335` (US3) → `1727b96` (US4) → `d68d734` (polish) → `8917fb9` (review fixes)
- **Wall-clock**: implement loop + review ≈ 55 min of subagent runtime (6 impl chunks + 3 review agents + 1 fix agent).

## 2. Chunk-by-chunk ledger

| # | Chunk (phase) | Tasks | ✅ | ⚠️ | ❌ | Commit | Notes flagged upward |
|---|---------------|-------|----|----|----|--------|----------------------|
| 1 | Phase 1+2 Setup + Foundational | T001–T010 (10) | 10 | 0 | 0 | `c71238c` | Streaming retry uses `ExitStack`/`AsyncExitStack`; failed 429 stream read+closed, successful stream left open until caller done. Logs only URL/attempt/delay (no secrets). No client tests here (deferred to later chunks). |
| 2 | Phase 3 US1 | T011, T012 (2) | 2 | 0 | 0 | `ed0457c` | T012 needed no `client.py` change — the `_request` retry + non-429 passthrough already correct. |
| 3 | Phase 4 US2 | T013 (1) | 1 | 0 | 0 | `32abfd5` | HTTP-date case asserted with an inclusive time window (driver parses against `datetime.now`); fixed-form cases assert exactly. |
| 4 | Phase 5 US3 | T014, T015 (2) | 2 | 0 | 0 | `d309335` | Scripted 429 responses attach `request=httpx.Request(...)` so `raise_for_status()` yields `HTTPStatusError` (test fabrication; driver correct). T015 satisfied without code change. |
| 5 | Phase 6 US4 | T016 (1) | 1 | 0 | 0 | `1727b96` | Disabled path asserted at `_request` level (raw 429 returned, no `RateLimitError`). Parity compared with a deterministic `Retry-After: 5` (exact cross-client comparison, no jitter noise). |
| 6 | Phase 7 Polish | T017–T021 (5) | 4 | 1 | 0 | `d68d734` | T020 ⚠️: `docs-generate` regenerated 10 UNRELATED files with pre-existing drift that also fail markdownlint (broken `--fix` referencing a missing `.markdownlint.yaml`); committed only the feature's `config.mdx`. Multipart rewind noted as defensive (httpx rewinds seekable files itself). |

All 21 tasks are `[X]` in `tasks.md`.

## 3. Tasks not completed

None. All T001–T021 completed and ticked.

## 4. Local-pass evidence (REQUIRED)

Runner: `uv run pytest`. Environment for every row: **Python 3.12.13, pytest 9.0.3, pytest-httpx 0.36.0, asyncio mode=AUTO, project `.venv` (`uv sync --all-groups --all-extras`); no external infrastructure required** (all tests run locally; no E2E deferred). Rows are grouped by test function; the bracketed count is the number of parametrized variants, all PASSED.

| Test id | Type | Run command | Passed at (ISO 8601) | Env context | Verbatim pass line |
|---------|------|-------------|----------------------|-------------|--------------------|
| `test_rate_limit.py` handler suite (17 tests: compute_backoff growth/clamp, jittered_delay bounds/variance, parse_retry_after delta/http-date/past-zero/malformed×5, next_delay honour/fallback/clamp, should_retry budget×2) | unit (pure) | `uv run pytest tests/unit/test_rate_limit.py tests/unit/sdk/test_rate_limit_retry.py -v` | 2026-07-07T12:20:50Z | as above | `17 passed in 0.02s` |
| `test_request_retries_429_then_succeeds` [standard, sync] | unit (client) | `uv run pytest tests/unit/sdk/test_rate_limit_retry.py -v` | 2026-07-07T12:24:28Z | as above | `6 passed in 0.02s` |
| `test_request_passes_non_429_through_untouched` [standard-200, standard-500, sync-200, sync-500] | unit (client) | `uv run pytest tests/unit/sdk/test_rate_limit_retry.py -v` | 2026-07-07T12:24:28Z | as above | `6 passed in 0.02s` |
| `test_request_honours_retry_after` [±delta/http-date/zero/past/above-max × standard+sync = 10] | unit (client) | `uv run pytest tests/unit/sdk/test_rate_limit_retry.py tests/unit/test_rate_limit.py -p no:randomly` | 2026-07-07T12:28:31Z | as above | `35 passed in 0.04s` |
| `test_request_malformed_retry_after_falls_back_to_backoff` [standard, sync] | unit (client) | `uv run pytest tests/unit/sdk/test_rate_limit_retry.py ... -p no:randomly` | 2026-07-07T12:28:31Z | as above | `35 passed in 0.04s` |
| `test_request_exhausts_retries_and_raises_rate_limit_error` [standard, sync] | unit (client) | `uv run pytest tests/unit/sdk/test_rate_limit_retry.py tests/unit/test_rate_limit.py` | 2026-07-07T12:34:00Z | as above | `37 passed in 0.05s` |
| `test_request_disabled_surfaces_raw_429_without_retry` [standard, sync] | unit (client) | `uv run pytest tests/unit/sdk/test_rate_limit_retry.py -v` | 2026-07-07T12:37:14Z | as above | `30 passed in 0.06s` |
| `test_request_max_retries_controls_attempt_count` [standard-0/1/3, sync-0/1/3] | unit (client) | `uv run pytest tests/unit/sdk/test_rate_limit_retry.py -v` | 2026-07-07T12:37:14Z | as above | `30 passed in 0.06s` |
| `test_async_sync_parity_on_identical_429_sequence` [retry-after-then-success, retry-after-exhaust] | unit (client) | `uv run pytest tests/unit/sdk/test_rate_limit_retry.py -v` | 2026-07-07T12:37:14Z | as above | `30 passed in 0.06s` |
| `test_all_request_paths_retry_429_then_succeed` [{standard,sync}×{regular,multipart,streaming} = 6] | unit (client, httpx_mock) | `uv run pytest tests/unit/sdk/test_rate_limit_retry.py::test_all_request_paths_retry_429_then_succeed tests/unit/sdk/test_rate_limit_retry.py::test_multipart_body_survives_retry -v` | 2026-07-07T12:42:57Z | as above | `8 passed` |
| `test_multipart_body_survives_retry` [standard, sync] | unit (client, httpx_mock) | (same as row above) | 2026-07-07T12:42:57Z | as above | `8 passed` |
| `test_parse_retry_after_negative_delta_floored_to_zero` | unit (pure) | `uv run pytest tests/unit/test_rate_limit.py tests/unit/sdk/test_rate_limit_retry.py` | 2026-07-07T13:01:20Z | as above | `62 passed in 0.13s` |
| `test_parse_retry_after_pathological_huge_value_returns_none` | unit (pure) | (same as row above) | 2026-07-07T13:01:20Z | as above | `62 passed in 0.13s` |
| `test_backoff_grows_exponentially_and_clamps` [standard, sync] | unit (client) | (same as row above) | 2026-07-07T13:01:20Z | as above | `62 passed in 0.13s` |
| `test_jitter_differs_between_instances` [standard, sync] | unit (client) | (same as row above) | 2026-07-07T13:01:20Z | as above | `62 passed in 0.13s` |
| `test_rewind_multipart_files_resets_every_file_object` | unit (direct helper) | (same as row above) | 2026-07-07T13:01:20Z | as above | `62 passed in 0.13s` |

**Final aggregate gate** (orchestrator-run): `uv run pytest tests/unit/test_rate_limit.py tests/unit/sdk/test_rate_limit_retry.py -q` → `62 passed`. No `MISSING` rows; no deferred-E2E rows (feature has no E2E surface — it is a pure client-library behaviour exercised via mocked transports).

## 5. Review findings

Reviewed the full diff `a55cbaa..HEAD` with three independent agents (code correctness + async/sync parity + type design; error handling / silent failures; test coverage quality).

| Severity | File / test | Summary | Disposition |
|----------|-------------|---------|-------------|
| HIGH | `rate_limit.py` `parse_retry_after` | Negative `Retry-After` (e.g. `-5`) not floored → sync `time.sleep(-5.0)` raises `ValueError` (crash) + async/sync divergence; negative leaks into `RateLimitError.retry_after`. | **Fixed inline** (`8917fb9`): floor delta-seconds at `0.0`. |
| MEDIUM/HIGH | `rate_limit.py` `parse_retry_after` | Pathological huge digit string raises uncaught `OverflowError` (crash); violates FR-004 fall-back. | **Fixed inline** (`8917fb9`): `except OverflowError: return None`, kept `except ValueError: pass` so HTTP-date fall-through still works. |
| HIGH (test) | `test_rate_limit_retry.py` | SC-003/FR-002 exponential-growth + jitter-divergence unguarded at driver level — a bug pinning `attempt=0` would pass the suite. | **Fixed inline** (`8917fb9`): added `test_backoff_grows_exponentially_and_clamps` (identity-patched jitter → deterministic growth) + `test_jitter_differs_between_instances`, async+sync. |
| HIGH (test) | `test_rate_limit_retry.py` | Multipart regression test passed even if `_rewind_multipart_files` were deleted (httpx rewinds seekable files itself). | **Fixed inline** (`8917fb9`): added direct `test_rewind_multipart_files_resets_every_file_object` that fails if the helper is gutted. |
| LOW | `client.py` `_rewind_multipart_files` | Non-seekable stream retried after 429 would silently send an empty/truncated body (suppressed `seek` error). Real callers pass seekable files, so low impact. | **Deferred** — see §6. |
| LOW | `client.py` `_rewind_multipart_files` | `seek(0)` is forced on the first attempt too (harmless for current fresh-file usage; a subtle change vs. reading from current position). | **Deferred** (no action). |
| LOW | `rate_limit.py` `parse_retry_after` | Fractional `Retry-After: 10.5` → falls back to computed backoff (RFC 7231 defines delta-seconds as integer, so this is spec-compliant). | **No action** (correct per spec). |
| LOW | tests | Untested: `err.retry_after is None` exhaustion path, disabled path on multipart/streaming, Config defaults/validators, explicit auth-path test. | **Deferred** (shared chokepoint / shared guard make these low-risk; recorded for a future hardening pass). |

## 6. Autonomous decisions

1. **Chunk merge**: merged Phase 1 (Setup — 2 stub-creation tasks) into Phase 2 (Foundational). Phase 1 only creates empty stubs that Phase 2 immediately fills; running them as separate clean-context subagents would produce a throwaway "empty class" commit. This is a cohesive-seam merge, not merging two independent increments — review granularity is preserved because the foundational machinery is one natural unit.
2. **`docs-generate` scope (T020)**: `uv run invoke docs-generate` regenerated 10 files unrelated to this feature (`client.mdx`, `node/*`, `graph_traversal/*`) reflecting pre-existing docstring drift, and those regenerated files fail markdownlint because the tool's `--fix` step references a missing `.markdownlint.yaml` and silently no-ops. The subagent reverted the 10 unrelated files and committed only the feature-relevant `config.mdx` (the 4 new `rate_limit_*` fields). **Flag for the user**: this docs-tooling breakage (broken markdownlint `--fix`, plus a `docs-validate`-vs-`lint-docs` conflict) is a pre-existing repo issue worth a separate follow-up; and a full clean `docs-generate` commit for the unrelated drift may be wanted independently.
3. **Multipart rewind is defensive**: reviewers confirmed httpx's `FileField.render_data()` already `seek(0)`s seekable files on every render, so `_rewind_multipart_files` is redundant for the seekable file objects real callers pass, and cannot help non-seekable streams. It is kept as harmless defence-in-depth and is now directly unit-guarded, but the original critique E2/X1 concern was largely already mitigated by httpx itself.
4. **`Retry-After` except split**: the code-review's literal suggestion `except (ValueError, OverflowError): return None` would have broken the HTTP-date branch (an HTTP-date fails `int()` with `ValueError` and must fall through to date parsing). Split into `except OverflowError: return None` + `except ValueError: pass` to preserve HTTP-date handling — verified by the still-green HTTP-date tests.
5. **Deferred LOW findings** (§5): recorded rather than fixed, since none affects the shipped behaviour for real callers and fixing them (e.g. surfacing an error on non-seekable-stream retry) is a design choice better made explicitly.

## 7. Suggested next steps

1. **Open a PR** for branch `dga/feat-409-retry-ivj0i` (base `stable`) — the feature is complete, tested (62 passing), and reviewed. Ensure both towncrier fragments (`changelog/1124.added.md`, `1124.changed.md`) are included; the `429 → RateLimitError` behaviour change is a caller-visible change flagged in the changed fragment.
2. **Optional hardening** (deferred LOW findings): decide whether a 429 retry on a non-seekable multipart stream should raise a clear error instead of silently sending an empty body; add the small missing tests (`retry_after is None` exhaustion, Config defaults/validators).
3. **Separate follow-up** for the repo's `docs-generate`/markdownlint tooling breakage (missing `.markdownlint.yaml`; unrelated `.mdx` drift) — outside this feature's scope.
4. **Branch-name note**: the branch is `dga/feat-409-retry-ivj0i` (says 409) but the feature is HTTP **429** throughout; a pre-existing branch-name typo, harmless, mentioned so the PR title uses 429.
