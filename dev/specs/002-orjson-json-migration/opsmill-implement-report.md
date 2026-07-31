# Implementation Report: Standardize SDK JSON serialization on orjson

## 1. Header

- **Feature**: Standardize SDK JSON serialization on orjson
- **Spec dir**: `specs/002-orjson-json-migration/`
- **Base commit**: `3830042` (HEAD at start)
- **Head commit**: `ebd1e0d` (after implementation; Phase 6 review added no code changes)
- **Branch**: `dga/feat-orjson-pd5o6`
- **Status**: **COMPLETE** — all 34 tasks `[X]`; §4 local-pass evidence has no `MISSING` rows.
- **Wall-clock**: ~40 min of sequential subagent execution (8 chunks) plus orchestrator verification.

## 2. Chunk-by-chunk ledger

| # | Chunk | Tasks | Outcome | Commit | Notes flagged upward |
|---|---|---|---|---|---|
| 1 | Setup (dependency) | T001–T002 | 2 ✅ | `1d84182` | Ordering override: added orjson, **kept ujson** so unmigrated modules keep importing; removal deferred to chunk 8. |
| 2 | Core (utils.py) | T003 | 1 ✅ | `debbc20` | Adapted 3 existing `decode_json` tests to the new `response.content` path; dict_hash 3 committed vectors still byte-identical. |
| 3 | Encode sites | T004–T011 | 8 ✅ | `2e9e422` | Found 8 pre-existing CLI-test failures (bracketed worktree path), unrelated. |
| 4 | Decode sites | T012–T016 | 5 ✅ | `ee902a3` | T014: confirmed guarded decode was `response.json()`, switched to `orjson.loads(response.content)`. Loosened one filter-test error-message assertion (orjson wording differs). |
| 5 | File I/O + export | T017–T019 | 3 ✅ | `4c8cd86` | recorder/playback collapsed to `write_text`/`read_text` by linter; round-trip sanity-checked. |
| 6 | pytest-plugin items | T020–T024 | 5 ✅ | `68d5835` | Decode-error pattern applied; no plugin test asserts the failure text. |
| 7 | Tests & verification | T025–T029 | 5 ✅ | `cd9c7ac` | Added non-ASCII dict_hash vector, datetime characterization, round-trip test, mock-free decode-invalid test; T029 confirmed no plugin-text change needed. |
| 8 | Finalize/Polish | T030–T034 | 5 ✅ | `ebd1e0d` | Removed ujson+types-ujson; all import greps empty; ruff+mypy green; migrated 4 test files that still imported ujson; fixed `test_query_echo` (4→2 echo indent) that T029 missed; added changelog fragment; captured perf. |

## 3. Tasks not completed

None. All 34 tasks are `[X]` in `tasks.md`.

## 4. Local-pass evidence (REQUIRED)

All timestamps 2026-07-15 UTC; environment `n/a` unless noted.

| Test id | Type | Run command | Passed at | Env | Verbatim pass line |
|---|---|---|---|---|---|
| `tests/unit/sdk/test_utils.py::test_dict_hash` (modified, T025) | unit | `uv run pytest tests/unit/sdk/test_utils.py -q` | 04:43:29Z | n/a | `28 passed in 0.03s` |
| `tests/unit/sdk/test_utils.py::test_decode_json_malformed_bytes_raises` (new, T028) | unit | `uv run pytest tests/unit/sdk/test_utils.py -q` | 04:43:29Z | n/a | `28 passed in 0.03s` |
| `tests/unit/sdk/test_utils.py` decode_json tests (adapted, T003) | unit | `uv run pytest tests/unit/sdk/test_utils.py -q` | 04:23:05Z | n/a | `27 passed in 0.02s` |
| `tests/unit/ctl/formatters/test_json.py::test_format_detail_renders_datetime_as_str_form` (new, T026) | unit | `uv run pytest tests/unit/ctl/formatters/test_json.py -q` | 04:44:04Z | n/a | `12 passed in 0.03s` |
| `tests/unit/sdk/test_recorder_playback.py::test_recorder_playback_round_trip` (new, T027) | unit | `uv run pytest tests/unit/sdk/test_recorder_playback.py -q` | 04:43:35Z | n/a | `1 passed in 0.02s` |
| `tests/unit/sdk/test_infrahub_filters.py::test_malformed_json_raises_error` (modified, T013) | unit | `uv run pytest tests/unit -k "filter" -q` | 04:32:28Z | n/a | included in `296 passed` |
| `tests/unit/sdk/test_client.py::test_query_echo` (modified, chunk 8) | unit | `uv run pytest tests/unit/ -q` | 04:56:03Z | n/a | now passing (in `1442 passed`) |
| test swaps in `tests/unit/ctl/conftest.py`, `tests/unit/sdk/conftest.py`, `tests/unit/sdk/graphql/test_multipart.py`, `tests/integration/test_export_import.py` (ujson→orjson) | unit/integration | `uv run pytest tests/unit/ -q` | 04:56:03Z | n/a | `1442 passed` (unit); integration file not run locally (see §6) |

Full-suite gate (chunk 8): `uv run pytest tests/unit/ -q` → `8 failed, 1442 passed, 1 xfailed`. **All 8 failures verified pre-existing/environmental** (bracketed worktree path `[dev03]` — Rich strips `[...]` as markup in path assertions; CLI-subprocess/pytester rendering). Confirmed by running base-commit `3830042` code in an equally-bracketed throwaway worktree: the same schema/menu/repo/task/jinja2 tests fail there too. Zero JSON-related regressions.

## 5. Review findings (Phase 6)

Ran code, errors, tests, comments, types, simplify lenses over `3830042..HEAD`.

| Severity | Lens | File | Summary | Disposition |
|---|---|---|---|---|
| — | errors | pytest_plugin/items/* | **Positive**: migration incidentally fixed a latent bug — old `except ujson.JSONDecodeError` never caught stdlib error from `response.json()`. | n/a |
| Medium | tests | transfer/exporter/json.py | `OPT_NON_STR_KEYS` int-key coercion untested. | Deferred — flags guard always-string-keyed GraphQL data (never triggers in practice); real-path test disproportionately heavy. Recommended follow-up. |
| Low | tests | test_infrahub_filters.py | Error-message assertion loosened to a prefix (orjson wording differs from stdlib). | Accepted — tightening to orjson-specific text would be version-brittle. |
| Low | code | `utils.py:95`, `schema/__init__.py:276` | `orjson.loads(response.content)` assumes UTF-8 vs httpx charset detection. | Accepted — Infrahub API always emits UTF-8. |
| Low | code | dict_hash → query_groups | Non-ASCII param hash shifts (raw UTF-8 vs escaped). | Accepted — documented in changelog (one-time tracking-group rename). |
| Low | code | recorder/pytest diffs | Indent 4→2 (orjson supports only `OPT_INDENT_2`). | Accepted — cosmetic; machine-reparsed / symmetric diffs; `test_query_echo` updated. |
| Low | simplify | multiple | Shared `OPT_INDENT_2\|OPT_SORT_KEYS` constant / `dumps_str` helper / `read_bytes` over `read_text`. | Advisory — not applied (would widen the mechanical diff). |

No Critical/High findings → no inline review fixes required.

## 6. Autonomous decisions

- **Dependency-removal ordering** (chunk 1): kept `ujson` installed through the migration and removed it only in the final chunk, so the environment stayed importable across the loop. FR-001 still enforced at the end (all import greps empty).
- **Skipped no code (Phase 6)**: no high+ findings; the one Medium (exporter int-key test) recorded as a follow-up rather than forcing a low-value/brittle test.
- **Verified "pre-existing" failures rigorously**: the chunk subagents' `git stash` comparisons were unreliable (stash doesn't revert prior *committed* chunks). I re-verified by running base-commit code in a bracketed-path worktree, confirming all 8 unit failures are the worktree-path artifact, not regressions.
- **Integration tests deferred — local E2E not supported**: `tests/integration/` requires a live Infrahub server (testcontainers); it timed out at container startup (240s), collecting 131 items with fixture-setup errors (not assertion failures). `tests/integration/test_export_import.py` (a ujson→orjson swap) will be exercised by CI. **This does not block** (it is a `deferred — local E2E not supported` case, not a `MISSING` row).
- **Perf captured** (T034, ad-hoc, N=1000, list of 1000 mixed dicts): dumps **11.8×** faster, loads 1.3×, round-trip **2.1×** faster than stdlib json. Evidence for the motivating speedup; no committed benchmark (parity was the bar).
- **CLAUDE.md not edited** despite a speckit agent-context step — project rule forbids it.

## 7. Suggested next steps

1. Open a PR (`3830042..ebd1e0d`, 8 commits) — include the perf numbers above in the description (T034).
2. Confirm CI green across the Python 3.10–3.14 matrix (validates orjson wheel coverage — the one assumption not verifiable locally).
3. Optional follow-up: add the exporter int-key unit test (Medium finding, §5) if the defensive `OPT_NON_STR_KEYS` guard is considered worth pinning.
4. Optional: apply the advisory simplify refactors (§5) in a separate cleanup if desired.
