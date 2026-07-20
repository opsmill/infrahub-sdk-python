# Implementation Plan: End-User CLI (`infrahubctl` CRUD commands)

**Branch**: `001-end-user-cli` | **Date**: 2026-03-28 | **Updated**: 2026-04-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `dev/specs/001-end-user-cli/spec.md`

## Summary

Add CRUD and schema discovery commands (`get`, `create`, `update`, `delete`,
`schema list`, `schema show`) as top-level commands on the existing `infrahubctl`
CLI app. The implementation reuses the existing SDK client, configuration,
AsyncTyper framework, and `catch_exception` pattern. Relationship values are
passed through to the SDK as HFIDs — the CLI does not resolve them to UUIDs.

## Technical Context

**Language/Version**: Python 3.10-3.13
**Primary Dependencies**: typer (via AsyncTyper), rich, pyyaml, httpx (via SDK client)
**Storage**: N/A (all data in Infrahub server via SDK)
**Testing**: pytest (unit + integration)
**Target Platform**: Linux, macOS, Windows (CLI)
**Project Type**: Single project (extension of existing SDK package)
**Performance Goals**: Query results < 5s for < 1000 objects
**Constraints**: Commands live on existing `infrahubctl`; shared config via `infrahubctl.toml`
**Scale/Scope**: ~10 new modules, ~1500-2000 lines of production code

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Async/Sync Dual Pattern | PASS | CLI commands are async (via AsyncTyper). No new public SDK API surface requiring dual pattern — CLI is async-only consumer. |
| II. Type Safety | PASS | All new functions have type hints. mypy/ty must pass. |
| III. Test Discipline | PASS | FR-015 requires unit + integration tests. |
| IV. API Stability | PASS | New commands on existing entry point, no changes to existing public API. No new dependencies. |
| V. Documentation Completeness | PASS | Google-style docstrings required. `docs-generate` after CLI changes. |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
dev/specs/001-end-user-cli/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research findings
├── data-model.md        # Data model (transient structures)
├── quickstart.md        # Usage quickstart guide
├── contracts/
│   └── cli-commands.md  # CLI command contracts
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Implementation tasks
```

### Source Code (repository root)

```text
infrahub_sdk/ctl/
├── cli_commands.py          # Existing: registers CRUD commands on main app
├── schema.py                # Existing: extended with schema list/show commands
├── parsers.py               # New: --set and --filter argument parsers
├── commands/
│   ├── __init__.py          # New: commands package
│   ├── get.py               # New: infrahubctl get command
│   ├── create.py            # New: infrahubctl create command
│   ├── update.py            # New: infrahubctl update command
│   ├── delete.py            # New: infrahubctl delete command
│   └── utils.py             # New: resolve_node, prepare_relationship_data
└── formatters/
    ├── __init__.py          # New: OutputFormat enum, auto-detection
    ├── base.py              # New: base formatter protocol
    ├── table.py             # New: Rich table formatter
    ├── json.py              # New: JSON formatter
    ├── csv.py               # New: CSV formatter
    └── yaml.py              # New: Infrahub Object YAML formatter

tests/unit/ctl/
├── commands/
│   ├── __init__.py
│   ├── test_get.py          # Unit tests for get command
│   ├── test_create.py       # Unit tests for create command
│   ├── test_update.py       # Unit tests for update command
│   ├── test_delete.py       # Unit tests for delete command
│   ├── test_schema.py       # Unit tests for schema commands
│   └── test_utils.py        # Unit tests for resolve_node
├── formatters/
│   ├── __init__.py
│   ├── test_init.py         # OutputFormat auto-detection tests
│   ├── test_table.py        # Table formatter tests
│   ├── test_json.py         # JSON formatter tests
│   ├── test_csv.py          # CSV formatter tests
│   └── test_yaml.py         # YAML formatter tests
└── test_parsers.py          # Parser tests (set, filter, coercion)

tests/integration/
└── test_enduser_cli.py      # Integration tests against Infrahub
```

**Structure Decision**: Commands are registered directly on the `infrahubctl`
main app in `cli_commands.py` (lines 78-81). Schema list/show commands are
added to the existing `schema` subgroup in `schema.py`. No separate entry point
or command registration module. This was decided in R1 (research.md) to avoid
user confusion with two CLI tools.

## Key Architectural Decisions

### Relationship Handling: HFID Pass-Through

**Decision**: The CLI passes relationship values directly to the SDK as HFID
references. It does NOT resolve them to UUIDs via round-trips.

**Implementation** (`prepare_relationship_data` in `commands/utils.py`):

- UUID strings → passed through (SDK wraps as `{"id": uuid}`)
- Non-UUID strings → converted to HFID list (SDK wraps as `{"hfid": [...]}`)
- Multi-component HFIDs → split on `/` (e.g., `"Cisco/NX-OS"` → `["Cisco", "NX-OS"]`)
- Cardinality-many → JSON array syntax: `--set tags=[["blue"], ["red"]]`

**Rationale**: The SDK's `RelatedNode` natively accepts lists (auto-wrapped as
`{"hfid": list}`) and strings (auto-wrapped as `{"id": str}`). The server
resolves HFIDs, including for generic peer types. This eliminates the need for
client-side `resolve_relationship_values` and `_search_generic_peer` functions,
which required expensive round-trips and brute-force schema scanning.

**Prior art**: The `infrahub-ansible` collection uses this same HFID pass-through
pattern (`infrahub_utils.py`).

**SDK dependencies** (future improvements, not blocking):

- [#267](https://github.com/opsmill/infrahub-sdk-python/issues/267) — `rebuild_hfid_from_data()` in SDK
- [#272](https://github.com/opsmill/infrahub-sdk-python/issues/272) — `node.update(data)` from dict

### Command Registration

**Decision**: Register `get`, `create`, `update`, `delete` as top-level commands
on the existing `infrahubctl` app. Add `schema list` and `schema show` to the
existing `infrahubctl schema` subgroup.

**Implementation**: Commands are imported in `cli_commands.py` and registered via
`app.command(name="...")`. Schema commands are added to the existing `schema_app`
in `schema.py`.

### Output Formats

**Decision**: Four formatters (table, JSON, CSV, YAML) with auto-detection
(table for TTY, JSON for piped). YAML format uses `apiVersion: infrahub.app/v1`
envelope, round-trippable with `ObjectFile`.

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Async/Sync Dual Pattern | PASS | No new public SDK API. CLI is async consumer only. |
| II. Type Safety | PASS | All modules typed. No generated code modified. |
| III. Test Discipline | PASS | Test structure mirrors source structure. Unit tests mock SDK client. Integration tests hit Infrahub. |
| IV. API Stability | PASS | Commands on existing `infrahubctl` entry point. No existing API changes. pyyaml, rich, typer already in `[ctl]` deps. |
| V. Documentation Completeness | PASS | Each new module has docstrings. `docs-generate` run after completion. |

All gates pass.
