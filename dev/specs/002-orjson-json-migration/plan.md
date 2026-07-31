# Implementation Plan: Standardize SDK JSON serialization on orjson

**Branch**: `dga/feat-orjson-pd5o6` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-orjson-json-migration/spec.md`

## Summary

Replace all JSON serialization in `infrahub_sdk/` — currently split across `ujson` (16 modules) and stdlib `json` (8 modules, 2 of which also use `ujson`) — with `orjson` as the sole JSON library. The migration is behaviour-preserving: byte-identical output at every consumed/compared site, unchanged parameter-hash values for ASCII/int/float inputs, and no gaps in decode-error handling. The single externally observable change is a one-time query-group-name shift for non-ASCII parameter values, which is accepted, documented, and pinned by a test.

## Technical Context

**Language/Version**: Python 3.10–3.14 (`requires-python = ">=3.10,<3.15"`)

**Primary Dependencies**: orjson (new, `>=3.10`); removes ujson + types-ujson. Existing: pydantic, httpx, graphql-core.

**Storage**: N/A (library). Touches on-disk recorded fixtures (recorder/playback) and telemetry/export files only as JSON text.

**Testing**: pytest (`tests/unit`, `tests/integration`).

**Target Platform**: Cross-platform library; orjson ships prebuilt wheels for CPython 3.10–3.14 on Linux/macOS/Windows.

**Project Type**: Single Python library + CLI (`infrahubctl`) + pytest plugin.

**Performance Goals**: Parity bar only — trust orjson's documented speedup; no benchmark harness or perf gate in scope.

**Constraints**: No behaviour change to serialized output, parameter hashing (ASCII/int/float), or decode-error handling. No public API signature changes.

**Scale/Scope**: ~35 call sites across 21 modules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is an unpopulated template stub — it defines no ratified principles. There are therefore no constitution gates to evaluate. Project working agreements from `AGENTS.md` that do apply:

- **New dependency (ask-first gate)**: adding `orjson` — CONFIRMED by maintainer. ✅
- **Async/sync dual pattern**: not affected (serialization is synchronous at all sites). ✅
- **Generated code (`protocols.py`)**: not touched. ✅
- **Type hints on all signatures**: preserved; orjson ships its own stubs. ✅

No violations. Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/002-orjson-json-migration/
├── plan.md              # This file
├── research.md          # Phase 0 output — library-behavior decisions
├── data-model.md        # Phase 1 output — call-site migration map
├── quickstart.md        # Phase 1 output — validation guide
├── contracts/
│   └── serialization-contract.md   # Behavioral contract this migration must preserve
└── checklists/
    └── requirements.md  # Spec quality checklist (specify phase)
```

### Source Code (repository root)

Files touched, grouped by concern (all under `infrahub_sdk/`):

```text
infrahub_sdk/
├── utils.py                       # dict_hash (encode), decode_json (decode-error)
├── client.py                      # debug-print dumps
├── checks.py                      # print dumps
├── playback.py                    # dump + file-object load  (removes dual import)
├── recorder.py                    # file-object dump (indent+sort_keys)
├── query_groups.py                # consumer of dict_hash (no edit; behavior noted)
├── graphql/
│   ├── multipart.py               # dumps -> str for httpx
│   └── renderers.py               # dumps for string escaping
├── ctl/
│   ├── validate.py                # dumps indent=2 sort_keys
│   ├── cli_commands.py            # dumps indent=2 sort_keys
│   ├── parsers.py                 # loads + decode-error
│   ├── telemetry.py               # dumps indent=2 -> file
│   └── formatters/json.py         # dumps indent=2 default=str (+datetime passthrough)
├── template/infrahub_filters.py   # loads + decode-error
├── schema/__init__.py             # decode-error
├── transfer/exporter/json.py      # dumps -> file (arbitrary data: non-str keys)
├── transfer/importer/json.py      # loads
└── pytest_plugin/
    ├── models.py                  # loads
    └── items/{base,check,graphql_query,python_transform,jinja2_transform}.py
                                    # dumps indent=4 + decode-error
```

**Structure Decision**: Existing single-package layout; no new modules or restructuring. The change is a mechanical, site-by-site substitution plus targeted adaptations for the four orjson API differences (bytes return, no file-object I/O, no `sort_keys`/`indent` kwargs → options, strict non-str keys).

## Design approach

Four orjson API differences drive every adaptation. The mapping is fixed and applied uniformly:

| ujson / stdlib call | orjson replacement |
|---|---|
| `dumps(x)` (str consumed) | `orjson.dumps(x).decode()` |
| `dumps(x, sort_keys=True)` | `orjson.dumps(x, option=orjson.OPT_SORT_KEYS)` |
| `dumps(x, indent=2 [,sort_keys])` | `orjson.dumps(x, option=orjson.OPT_INDENT_2 [\| orjson.OPT_SORT_KEYS])` (byte-identical to stdlib indent=2) |
| `dumps(x, indent=4)` | `orjson.dumps(x, option=orjson.OPT_INDENT_2)` (**4→2 width, cosmetic; human-facing only**) |
| `dumps(x, default=str)` (CLI formatter) | `orjson.dumps(x, option=orjson.OPT_INDENT_2 \| orjson.OPT_PASSTHROUGH_DATETIME, default=str)` |
| `dumps(arbitrary_data)` (export) | add `option=orjson.OPT_NON_STR_KEYS` to preserve silent int-key coercion |
| `loads(s)` | `orjson.loads(s)` (accepts str or bytes) |
| `load(fobj)` | `orjson.loads(fobj.read())` |
| `dump(x, fobj, ...)` | `fobj.write(orjson.dumps(x, option=...).decode())` |

**Decode-error strategy (resolves the #1165 hazard).** `orjson.JSONDecodeError` subclasses both `json.JSONDecodeError` and `ValueError` (verified). To remove stdlib `json` entirely *and* keep every `except` correct, decode sites that currently rely on httpx's stdlib-backed `response.json()` are switched to decode explicitly via `orjson.loads(response.content)`, so the raised error is `orjson.JSONDecodeError` and the paired `except orjson.JSONDecodeError` is exact. Pure `loads` sites (`parsers.py`, `infrahub_filters.py`, `pytest_plugin`) swap library and matching `except` together. This makes decode + except internally consistent everywhere — the exact ambiguity #1165 flagged.

**dict_hash.** `ujson.dumps(d, sort_keys=True).encode()` → `orjson.dumps(d, option=orjson.OPT_SORT_KEYS)` (already bytes). Byte-identical for ASCII/int/float/nested (verified against the three committed MD5 vectors); diverges only for non-ASCII (orjson emits raw UTF-8 vs ujson `\uXXXX`). Accepted + pinned by a new test vector.

**Atomicity.** All sites migrate in one change set; the intermediate two-library state is never committed to `main`.

## Notes from critique (applied)

- **Special-type parity**: `extract_node_data`/`extract_node_detail` yield primitives + `datetime` (passthrough) + string-rendered addresses/ids — no enum/dataclass objects — so orjson's native type handling does not break byte-parity. Add a characterization test on a date/time-bearing record to guard it (FR-002 acceptance).
- **pytest-plugin diff width**: the 4→2 indent shift changes failure/diff message text; check whether any test asserts that exact text and update it as a characterization change, not a contract break.
- **NaN/Infinity**: decoding now rejects them and `nan` encodes to `null` — documented as a spec edge case; no special handling planned.
- **Performance**: parity is the bar (no benchmark harness). Capture one ad-hoc before/after encode+decode number in the PR description to evidence the motivating speedup.
- **Interpreter coverage**: rely on the CI matrix (3.10–3.14) to confirm orjson wheel availability rather than a local check.

## Complexity Tracking

No constitution violations; section not required.
