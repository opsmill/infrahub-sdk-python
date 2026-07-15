# Tasks: Standardize SDK JSON serialization on orjson

**Feature**: `specs/002-orjson-json-migration` · **Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

**Input**: plan.md, spec.md, data-model.md (call-site migration map), research.md, contracts/serialization-contract.md

This feature is a single, atomic P1 user story. Most migration tasks touch distinct files and are parallelizable `[P]`; they must all land in one change set (never commit the two-library intermediate state). The transform for each site is fixed by the plan's mapping table and the data-model call-site map — consult those, not intuition.

---

## Phase 1: Setup (dependency swap)

- [X] T001 Swap the JSON dependency in `pyproject.toml`: remove `"ujson>=5"` from `dependencies` and `"types-ujson"` from the dev group; add `"orjson>=3.10"` to `dependencies`. (ujson/types-ujson removal deferred to the final polish chunk, T033-area, so unmigrated modules keep importing during the atomic migration.)
- [X] T002 Refresh the lockfile and environment: run `uv lock` then `uv sync --all-groups --all-extras`; confirm orjson resolves and ujson is gone. (orjson resolves alongside ujson; ujson removal deferred to T033-area polish chunk.)

**Checkpoint**: orjson installed, ujson removed. Code still imports ujson/json and will not import-check until Phase 2 completes — expected during the atomic migration.

---

## Phase 2: User Story 1 — Transparent JSON library migration (Priority: P1) 🎯 MVP

**Goal**: orjson is the sole JSON library across `infrahub_sdk/`; all observable behaviour preserved except the documented non-ASCII query-group-name shift.

**Independent test**: `grep -rn "import ujson\|^import json" infrahub_sdk/` returns nothing; full test suite green; CLI/formatter output and ASCII/int/float `dict_hash` values byte-identical to baseline.

### Core / shared

- [X] T003 [US1] In `infrahub_sdk/utils.py`: migrate `dict_hash` (`orjson.dumps(dictionary, option=orjson.OPT_SORT_KEYS)`, drop the now-redundant `.encode()`) and `decode_json` (decode via `orjson.loads(response.content)`, change `except` to `orjson.JSONDecodeError`); remove both `import json` and `import ujson`, add `import orjson`.

### Encode sites (each a distinct file → parallelizable)

- [X] T004 [P] [US1] `infrahub_sdk/client.py:218` debug print: `orjson.dumps(variables, option=orjson.OPT_INDENT_2).decode()`; swap import.
- [X] T005 [P] [US1] `infrahub_sdk/checks.py:112` print: `orjson.dumps(log_message).decode()`; swap import.
- [X] T006 [P] [US1] `infrahub_sdk/graphql/multipart.py:46,60`: `orjson.dumps(..., option=orjson.OPT_NON_STR_KEYS).decode()` (str for httpx); swap import.
- [X] T007 [P] [US1] `infrahub_sdk/graphql/renderers.py:54` string-escaping: `orjson.dumps(value).decode()`; swap import (keep the escaping comment accurate).
- [X] T008 [P] [US1] `infrahub_sdk/ctl/validate.py:107`: `orjson.dumps(response, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode()`; swap import.
- [X] T009 [P] [US1] `infrahub_sdk/ctl/cli_commands.py:355`: same option combo + `.decode()`; swap import.
- [X] T010 [P] [US1] `infrahub_sdk/ctl/telemetry.py:127`: `output_path.write_text(orjson.dumps(snapshots, option=orjson.OPT_INDENT_2).decode(), encoding="utf-8")`; swap import.
- [X] T011 [P] [US1] `infrahub_sdk/ctl/formatters/json.py:42,59`: `orjson.dumps(x, option=orjson.OPT_INDENT_2 | orjson.OPT_PASSTHROUGH_DATETIME, default=str).decode()`; swap import; update the "Uses stdlib json" docstring.

### Decode sites

- [ ] T012 [P] [US1] `infrahub_sdk/ctl/parsers.py:27,28`: `orjson.loads(stripped)` + `except orjson.JSONDecodeError`; swap import.
- [ ] T013 [P] [US1] `infrahub_sdk/template/infrahub_filters.py:167,168`: `orjson.loads(value)` + `except (orjson.JSONDecodeError, TypeError)`; swap import.
- [ ] T014 [P] [US1] `infrahub_sdk/schema/__init__.py:277`: apply the decode-error strategy (decode explicitly via orjson where the value comes from `response.json()`; `except orjson.JSONDecodeError`); swap import.
- [ ] T015 [P] [US1] `infrahub_sdk/transfer/importer/json.py:67,150`: `orjson.loads(...)`; swap import.
- [ ] T016 [P] [US1] `infrahub_sdk/pytest_plugin/models.py:57`: `orjson.loads(text)`; swap import.

### File-object I/O (no `load`/`dump` in orjson)

- [ ] T017 [P] [US1] `infrahub_sdk/recorder.py:59`: `fobj.write(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode())`; swap import.
- [ ] T018 [P] [US1] `infrahub_sdk/playback.py:52,57`: encode `orjson.dumps(payload)` (drop `str(...).encode()` wrappers — already bytes), read `orjson.loads(fobj.read())`; remove both `import json` and `import ujson`, add `import orjson`.

### Export (arbitrary data → preserve non-str-key coercion)

- [ ] T019 [P] [US1] `infrahub_sdk/transfer/exporter/json.py:151,155,166`: `orjson.dumps(..., option=orjson.OPT_NON_STR_KEYS).decode()` for the `write_text` sites; swap import.

### pytest-plugin items (dumps indent + paired except)

- [ ] T020 [P] [US1] `infrahub_sdk/pytest_plugin/items/base.py:62,63`: `orjson.dumps(x, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode().splitlines()`; swap import.
- [ ] T021 [P] [US1] `infrahub_sdk/pytest_plugin/items/check.py:52,53`: `OPT_INDENT_2` + `.decode()`, and set the paired `except` to match the orjson decode of `response.json()`; swap import.
- [ ] T022 [P] [US1] `infrahub_sdk/pytest_plugin/items/graphql_query.py:31,32`: same pattern as T021.
- [ ] T023 [P] [US1] `infrahub_sdk/pytest_plugin/items/python_transform.py:54,55`: same pattern as T021.
- [ ] T024 [P] [US1] `infrahub_sdk/pytest_plugin/items/jinja2_transform.py:63,64`: `OPT_INDENT_2 | OPT_SORT_KEYS` + `.decode()` + paired except; swap import.

**Checkpoint**: no `ujson`/stdlib-`json` imports remain; package imports cleanly.

---

## Phase 3: Tests & verification (part of US1 acceptance)

- [ ] T025 [US1] Extend `tests/unit/sdk/test_utils.py::test_dict_hash`: keep the three committed vectors (`608de4…`, `4d8f1a…`, `99914b…`) and add a non-ASCII vector (e.g. `{"x": "café"}`) asserting the new pinned orjson value (`dict_hash` of `b'{"x":"caf\xc3\xa9"}'`).
- [ ] T026 [US1] Add a characterization test for `ctl/formatters/json.py` asserting a record with a date/time value renders identically to the pre-migration `str()` form (guards the `OPT_PASSTHROUGH_DATETIME` decision).
- [ ] T027 [US1] Confirm `tests/unit/sdk/test_file_object.py` (or add a targeted test) covers a recorder→playback round-trip yielding the original object after the file-object rewrite.
- [ ] T028 [US1] Add/confirm a decode-of-invalid-input test proving malformed JSON still raises and is caught at a representative decode site (`decode_json`).
- [ ] T029 [P] [US1] Check whether any pytest-plugin test asserts exact failure/diff message text; update expected strings for the cosmetic 4→2 indent shift.

---

## Phase 4: Polish & cross-cutting

- [ ] T030 Verify zero legacy imports: `grep -rn "import ujson" infrahub_sdk/` and `grep -rn "^import json\|^\s*import json$" infrahub_sdk/` both return nothing (SC-001).
- [ ] T031 Run `uv run invoke format lint-code` — ty/mypy must be green (catches any `bytes`-where-`str`-expected leak, FR-004).
- [ ] T032 Run `uv run pytest tests/unit/` then `uv run pytest tests/integration/` — all green (SC-002).
- [ ] T033 Add a release-note entry documenting the one-time non-ASCII `dict_hash`/query-group-name change (SC-004); grep docs for any `ujson` references and update.
- [ ] T034 Capture one ad-hoc before/after encode+decode timing on a representative payload in the PR description (evidence for the motivating speedup; not a committed benchmark).

---

## Dependencies & execution order

- **T001 → T002** (Setup) must complete first; orjson must be importable.
- **T003–T024** (migration) all depend on T002 and are mutually independent `[P]` (distinct files); they form the atomic change set.
- **T025–T029** (tests) depend on the corresponding migration tasks landing.
- **T030–T034** (polish) run last, after the full change set is in place.

## Parallel execution example

After T002, launch the migration in parallel — e.g. one agent per file cluster:

```text
T004 client.py │ T005 checks.py │ T006 multipart.py │ T008 validate.py │
T011 formatters/json.py │ T017 recorder.py │ T018 playback.py │ T020–T024 pytest_plugin/*
```

T003 (utils.py) is the one shared-concern file; do it first or in isolation to avoid churn.

## MVP scope

The entire feature is the MVP: a single atomic P1 story. There is no smaller shippable slice — a partial migration would leave two JSON libraries coexisting, which is the exact state this work removes.

## Format validation

All tasks use `- [ ] Txxx [P?] [US1?] description + file path`. Setup/Polish tasks carry no story label; migration/test tasks carry `[US1]`; parallelizable distinct-file tasks carry `[P]`.
