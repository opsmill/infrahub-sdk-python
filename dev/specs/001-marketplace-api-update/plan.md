# Implementation Plan: Marketplace Download Command Update

**Branch**: `knotty-dibble` | **Date**: 2026-04-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-marketplace-api-update/spec.md`

## Summary

Migrate `infrahubctl marketplace get` to the public REST API at `marketplace.infrahub.app`, add auto-detection of schema-vs-collection identifiers, keep the `--version` pinning flag for schemas, and retain `--output-dir` (default `./schemas`). The REST migration, `--version`, and `--output-dir` pieces have already shipped in the current branch's `Marketplace` commit; the remaining deltas are auto-detection, the four-class error taxonomy, and the documented precedence rule for namespace/name collisions.

## Technical Context

**Language/Version**: Python 3.10–3.13
**Primary Dependencies**: `typer` (CLI), `httpx` (HTTP), `rich` (console output), `pydantic` 2.x (config). No new runtime dependencies are expected.
**Storage**: Files on disk under the user-chosen `--output-dir` (default `./schemas`). No database or server-side state owned by this change.
**Testing**: `pytest` with `pytest-httpx` for mocking the marketplace REST API; existing tests in `tests/unit/ctl/test_marketplace_app.py` are the template.
**Target Platform**: Cross-platform CLI (macOS/Linux/Windows), installed via `uv`/`pip` as the `infrahubctl` entry point.
**Project Type**: Single project (Python SDK + CLI) — uses the `infrahub_sdk` package layout already in place.
**Performance Goals**: Interactive CLI; target end-to-end command latency dominated by the marketplace round-trip. Auto-detection must not exceed one additional round-trip beyond the download itself in the common (cache-miss, 404-on-schema) case.
**Constraints**: Must remain backward compatible with scripts that already pass `--collection` / `--output-dir` / `--version`. Must not require any new public SDK surface outside the CLI module. Must not re-introduce GraphQL usage for marketplace calls.
**Scale/Scope**: Small surface area — a single `infrahub_sdk/ctl/marketplace.py` module (~180 LOC today) plus its test file. Expected diff is additive, likely under ~150 LOC of new code plus tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

This repository ships a template-only `.specify/memory/constitution.md` (unfilled) in sibling worktrees, and none in the current branch. In the absence of concrete articles, the following project-level gates (derived from `AGENTS.md`) are applied:

- **Async/sync dual pattern**: N/A for this change — the marketplace CLI command is already async-only (via `AsyncTyper`) and deliberately does not expose a sync twin. Adding a sync twin is out of scope.
- **Type hints on all signatures**: PASS — will be enforced on any new helpers.
- **No modifications to generated code (`protocols.py`)**: PASS — not touched.
- **No new runtime dependencies without asking first**: PASS — no new dependencies planned.
- **Lint + format gates (`uv run invoke format lint-code`)**: PASS — will be run before committing.
- **Tests-first spirit**: Will add unit tests covering each new acceptance scenario before wiring the CLI changes.

**Result**: PASS. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/001-marketplace-api-update/
├── spec.md                 # Feature specification (already written)
├── plan.md                 # This file
├── research.md             # Phase 0 output
├── contracts/
│   └── marketplace-api.md  # Reverse-documented external REST contract we consume
├── quickstart.md           # Phase 1 output
├── checklists/
│   └── requirements.md     # Spec quality validation (already written)
└── tasks.md                # (Produced later by /speckit.tasks)
```

`data-model.md` is intentionally omitted: this feature consumes an external REST API and writes YAML to disk, with no owned entity model to design. The Key Entities in `spec.md` are behavioural, not a data-store schema.

### Source Code (repository root)

```text
infrahub_sdk/
├── ctl/
│   ├── marketplace.py         # Primary code under change
│   ├── config.py              # `marketplace_url` setting (already in place)
│   └── cli_commands.py        # Registers the marketplace sub-app (no change expected)

tests/
└── unit/
    └── ctl/
        └── test_marketplace_app.py   # Primary test file to extend
```

**Structure Decision**: Single-project Python layout. All implementation lives in the existing `infrahub_sdk/ctl/marketplace.py` module; tests live alongside existing tests in `tests/unit/ctl/test_marketplace_app.py`. No new packages or modules are introduced.

## Phases

### Phase 0 — Research

See [research.md](research.md). Topics resolved:

1. Auto-detection strategy (schema-probe-first vs. parallel probe vs. metadata endpoint).
2. Name collision precedence (`schema wins` — see Assumption in spec).
3. Error taxonomy mapping (not-found vs. version-not-found vs. network vs. invalid-input) onto observable HTTP responses from the marketplace.
4. Behaviour when a schema exists only as a pre-release (no stable published semver).

### Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **External contract documentation** → [contracts/marketplace-api.md](contracts/marketplace-api.md).
   Documents the *consumed* REST endpoints (schemas, collections, version pinning), expected response shapes, and HTTP status semantics. This is not an owned contract — it reverse-describes what the CLI assumes about `marketplace.infrahub.app`, so drift can be detected.

2. **Quickstart** → [quickstart.md](quickstart.md).
   Manual and automated verification steps that exercise each acceptance scenario from the spec.

3. **Agent context update**: not applicable — no `.specify/scripts/bash/update-agent-context.sh` is installed in this branch, and the project-level agent context (`AGENTS.md`) does not require updates for this feature (no new dependencies or commands).

### Phase 2 — Tasks (deferred)

Not produced by this command. Will be generated by `/speckit.tasks` against this plan.

## Complexity Tracking

No constitution violations to justify. The feature fits inside the existing module with no new abstractions.
