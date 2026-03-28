# Implementation Plan: End-User CLI (`infrahub` command)

**Branch**: `001-end-user-cli` | **Date**: 2026-03-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-end-user-cli/spec.md`

## Summary

Create a new `infrahub` CLI entry point for end users to perform CRUD operations
on Infrahub data and discover schema. The CLI reuses the existing SDK client,
configuration, and AsyncTyper framework from `infrahubctl`, adding commands for
`get`, `create`, `update`, `delete`, and `schema` operations with multiple output
formats including round-trippable Infrahub Object YAML.

## Technical Context

**Language/Version**: Python 3.10-3.13
**Primary Dependencies**: typer (via AsyncTyper), rich, pyyaml, httpx (via SDK client)
**Storage**: N/A (all data in Infrahub server via SDK)
**Testing**: pytest (unit + integration)
**Target Platform**: Linux, macOS, Windows (CLI)
**Project Type**: Single project (extension of existing SDK package)
**Performance Goals**: Query results < 5s for < 1000 objects
**Constraints**: Must coexist with `infrahubctl`; shared config
**Scale/Scope**: ~10 new modules, ~1500-2000 lines of production code

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async/Sync Dual Pattern | PASS | CLI commands are async (via AsyncTyper). No new public SDK API surface requiring dual pattern — CLI is async-only consumer. |
| II. Type Safety | PASS | All new functions will have type hints. mypy/ty must pass. |
| III. Test Discipline | PASS | FR-015 requires unit + integration tests. 70% coverage target. |
| IV. API Stability | PASS | New entry point, no changes to existing public API. No new dependencies needed. |
| V. Documentation Completeness | PASS | Google-style docstrings required. `docs-generate` after CLI changes. |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-end-user-cli/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research findings
├── data-model.md        # Data model (transient structures)
├── quickstart.md        # Usage quickstart guide
├── contracts/
│   └── cli-commands.md  # CLI command contracts
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
infrahub_sdk/ctl/
├── enduser_cli.py           # New: main app + entry point for `infrahub`
├── enduser_commands.py      # New: top-level command registration
├── commands/
│   ├── __init__.py          # New: commands package
│   ├── get.py               # New: `infrahub get` command
│   ├── create.py            # New: `infrahub create` command
│   ├── update.py            # New: `infrahub update` command
│   ├── delete.py            # New: `infrahub delete` command
│   └── schema.py            # New: `infrahub schema` command group
├── formatters/
│   ├── __init__.py          # New: formatters package
│   ├── base.py              # New: base formatter protocol/ABC
│   ├── table.py             # New: Rich table formatter
│   ├── json.py              # New: JSON formatter
│   ├── csv.py               # New: CSV formatter
│   └── yaml.py              # New: Infrahub Object YAML formatter
└── parsers.py               # New: --set and --filter argument parsers

tests/unit/ctl/
├── commands/
│   ├── __init__.py
│   ├── test_get.py          # New: unit tests for get command
│   ├── test_create.py       # New: unit tests for create command
│   ├── test_update.py       # New: unit tests for update command
│   ├── test_delete.py       # New: unit tests for delete command
│   └── test_schema.py       # New: unit tests for schema commands
├── formatters/
│   ├── __init__.py
│   ├── test_table.py        # New: table formatter tests
│   ├── test_json.py         # New: JSON formatter tests
│   ├── test_csv.py          # New: CSV formatter tests
│   └── test_yaml.py         # New: YAML formatter tests
└── test_parsers.py          # New: parser tests

tests/integration/
└── test_enduser_cli.py      # New: integration tests against Infrahub
```

**Structure Decision**: Extend `infrahub_sdk/ctl/` with a parallel entry point.
New commands go in a `commands/` subdirectory to separate end-user commands from
existing `infrahubctl` modules. Formatters are isolated in `formatters/` for
testability and reuse across commands.

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async/Sync Dual Pattern | PASS | No new public SDK API. CLI is async consumer only. |
| II. Type Safety | PASS | All modules typed. No generated code modified. |
| III. Test Discipline | PASS | Test structure mirrors source structure. Unit tests mock SDK client. Integration tests hit Infrahub. |
| IV. API Stability | PASS | New `infrahub` entry point in pyproject.toml. No existing API changes. pyyaml, rich, typer already in `[ctl]` deps. |
| V. Documentation Completeness | PASS | Each new module gets docstrings. `docs-generate` run after completion. |

All gates pass. Ready for `/speckit.tasks`.
