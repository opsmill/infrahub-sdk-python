# Implementation Plan: Error Catalogue in the Python SDK

**Branch**: `pog-error-catalogue-IFC-3034` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `dev/specs/ifc-3034-error-catalogue/spec.md`

## Summary

Make ordinary SDK operations raise the specific exception for the failure the server reported, on
both the async and sync clients, without ever raising on a payload the SDK does not recognise.

The approach has four parts:

1. **A parsed envelope on the base classes.** A new `ApiError` base carries `code`, `http_status`, the
   raw `extensions`, and the server error list; `GraphQLError` and `AuthenticationError` both descend
   from it. The envelope is read by one raise-time factory shared by every existing raise site, so the
   code is readable against any server version even with no generated bindings at all. Because the
   catalogue is GraphQL-only, every generated class descends from `GraphQLError`, and the 401/403 codes
   descend from `AuthenticationError` as well.

   The payload is **not** an attribute. Each catalogued class promotes its payload's fields to directly
   typed attributes — `exc.node_kind`, `exc.fields` — typed exactly as the catalogue declares them.
   That is what US1 asks for, it matches how the three adopted classes already work, and it means no
   class needs a loosely typed payload attribute for subclasses to narrow. Nothing in this design is
   typed `Any` beyond the raw decoded JSON in `extensions` and `errors`.
2. **Generated per-code bindings.** Infrahub renders one exception class and one pydantic payload
   model per catalogue code into a single module in the SDK submodule, next to the schema models and
   protocols it already generates there, and its existing generated-artefact validation gains a check
   for it. The module is generated in full and imports only the hand-written base, which is what keeps
   the package's import graph one-way.
3. **Reconciling the three names that already exist.** `NodeNotFoundError`,
   `BranchNotFoundError`, and `SchemaNotFoundError` are adopted by the generator rather than
   duplicated: the hand-written classes declare the code they represent, the generator sees that
   and imports them instead of defining them.
4. **Removing the string matching.** The silent-refresh decision reads the code, falling back to
   the legacy message check only for servers that predate the catalogue.

The catalogue holds 15 codes today (12 on the GraphQL branch, 3 on the authentication branch).

## Technical Context

**Language/Version**: Python 3.10-3.13 (SDK); the generator runs under the Infrahub repository's
Python environment

**Primary Dependencies**: pydantic >= 2.0 (payload models), httpx (transport), typer + rich (CLI);
Jinja2 and invoke on the Infrahub side for generation. No new runtime dependency.

**Storage**: N/A

**Testing**: pytest with `asyncio_mode = "auto"`, `pytest-httpx` for transport-level mocking;
response-envelope fixtures under `tests/fixtures/`; both client variants exercised through the
`BothClients` fixture in `tests/unit/sdk/conftest.py`

**Target Platform**: Library consumed by `infrahubctl`, the Infrahub Ansible collection, and
external Python applications

**Project Type**: Library plus its CLI, spanning two repositories (bindings are generated in
Infrahub, consumed here)

**Performance Goals**: None. The factory runs once per failed request; parsing is a dict lookup plus
one pydantic validation.

**Constraints**:

- Parsing MUST NOT raise for any envelope shape, including an unknown code, an unknown payload
  field, an absent `extensions`, or a pre-catalogue integer `code`.
- Every existing exception name, constructor signature, and `except` clause keeps working.
- The SDK holds no copy of the catalogue schema; the generated bindings are the only artefact that
  crosses the repository boundary.
- No circular imports. The exceptions package is strictly layered, and generated files are generated
  in full — never a hand-edited region inside a generated file, and never a generated region inside a
  hand-written one.
- `infrahub_sdk.exceptions` is the one supported import path for every exception, and no name
  importable from it today may stop being importable from it. The restructuring must be invisible from
  outside the package.
- The raised class is a function of the response's first error code alone — never of payload validity,
  binding freshness, or which transport observed it.

**Scale/Scope**: 15 catalogue codes; 11 `AuthenticationError` raise sites and 4 `GraphQLError`
raise sites collapse onto two factories; one generated module; one CLI ladder reordering; one new
documentation topic page.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Async/Sync Dual API Parity | **Pass.** No new public client method, so `test_method_count` and `test_validate_method_signature` are untouched. The behaviour change lands on the async and sync paths of `_execute_graphql`, `_execute_graphql_with_file`, and the relogin wrappers, which are separate implementations; both are covered by parametrized tests over `["standard", "sync"]`. |
| II. Backward Compatibility & Public API Stability | **Pass, with two documented broadenings.** Nothing is removed or renamed, so no deprecation path is required. `except GraphQLError` additionally catches client-side node/branch/schema lookup misses, and `NodeNotFoundError.identifier` widens to admit the plain string the file handler already passes. Both get towncrier fragments per FR-016. `infrahub_sdk.exceptions` is treated as public and is the one supported import path; a snapshot test pins that no name importable from it disappears, so restructuring it into a package is invisible from outside. |
| III. Layered Architecture | **Pass.** All envelope parsing, resolution, and message construction lives in `infrahub_sdk/`. The CLI change is confined to presentation: reordering its `isinstance` ladder and degrading the GraphQL renderer when there are no server errors to render. |
| IV. Type Safety & Typed Errors | **Pass, with no suppressions.** This principle is the feature. Generated payload models are pydantic v2; every failure mode gets a specific subclass under `Error`; each catalogued class carries its payload's fields as attributes typed exactly as the catalogue declares them. `Any` appears only where the value genuinely is unknown at the type level — the raw decoded JSON in `extensions` and `errors`, the latter already annotated that way today. No `# type: ignore` is anticipated anywhere; if the R15 spike shows one is needed, that is a signal the shape is wrong rather than a licence to add it. |
| V. Test-First Development | **Pass.** Tests ship in the same change: envelope fixtures per code, cross-version fallback cases, ladder assertions, relogin cases, and both-client parity. Deliberate behaviour changes (the message change, the re-rooting) are pinned by tests that assert the new behaviour rather than being worked around. Because every fixture is authored alongside the parser that reads it, the mocked suite alone could pass against an envelope shape the server never sends — so two real catalogued failures are also driven through testcontainers, which is where the constitution puts behaviour that depends on real server responses. |
| VI. Format & Lint Before Commit | **Pass, with one justified silencing.** `uv run invoke format lint-code` and `lint-docs`; the generated modules are `ruff format`ed by the generator, as the other generated artefacts are. The façade re-exports the generated classes with `from .catalogue import *`, which trips `F403` under `select = ["ALL"]`. A wildcard is the only re-export form that keeps the export surface automatic as codes are added *and* stays visible to mypy and `ty`; the alternative is a hand-maintained list edited every time the catalogue grows. Recorded as a commented `per-file-ignores` entry, mirroring the existing entry for `infrahub_sdk/schema/generated/*.py`. |
| VII. Documentation Accuracy | **Pass.** A new hand-written topic page describes the hierarchy and the cross-version guarantees, linking to Infrahub's published catalogue for the code list rather than restating it. Converting `exceptions.py` into a package requires categorising it in `tasks.py::get_modules_to_document`; it goes in `packages_to_ignore`, which preserves today's `sdk_ref` output exactly and avoids coupling the SDK's `docs-validate` to an Infrahub-side regeneration. |

**Result**: no violations. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
dev/specs/ifc-3034-error-catalogue/
├── plan.md                         # This file
├── spec.md                         # Feature specification
├── research.md                     # Phase 0 output
├── data-model.md                   # Phase 1 output
├── quickstart.md                   # Phase 1 output
├── contracts/
│   ├── exception-hierarchy.md      # The consumer-facing contract
│   └── generator-contract.md       # The Infrahub-to-SDK generation contract
├── checklists/
│   └── requirements.md
└── tasks.md                        # Phase 2 output (/speckit-tasks, not created here)
```

### Source Code

This repository (`infrahub-sdk-python`):

```text
infrahub_sdk/
├── exceptions/                     # exceptions.py becomes a package, layered strictly one-way
│   ├── base.py                     # layer 0: today's exceptions.py + ApiError + adopted-code markers
│   ├── catalogue.py                # GENERATED in full — layer 1: payload models, per-code classes, map
│   ├── factory.py                  # layer 2: raise-time resolution from a response envelope
│   └── __init__.py                 # layer 3: façade, re-exports base + catalogue, defines __all__
├── client.py                       # Raise sites and the relogin wrappers call the factories
├── object_store.py                 # REST auth raise sites call the auth factory
├── file_handler.py                 # REST auth raise site calls the auth factory
├── analyzer.py                     # Pre-existing GraphQLError(str) misuse, corrected
└── ctl/
    └── utils.py                    # Ladder reordering and renderer degradation

tests/
├── fixtures/
│   └── error_catalogue/            # Response-envelope fixtures per code and per cross-version case
└── unit/
    ├── sdk/
    │   ├── test_exceptions.py               # Hierarchy, dual base, naming, adoption, messages
    │   ├── test_exceptions_layering.py      # Asserts the import graph stays one-way
    │   ├── test_exceptions_public_names.py  # No name importable from the package may disappear
    │   ├── test_error_catalogue.py          # Factory: resolution, precedence, fallbacks, totality
    │   ├── test_relogin_headers.py          # Extended with the typed refresh decision
    │   └── test_client.py                   # Both-client raise-path assertions
    └── ctl/
        └── test_utils.py                    # Ladder behaviour and no-server-errors rendering

tests/integration/
├── test_infrahub_client.py          # Real catalogued failures, async
└── test_infrahub_client_sync.py     # The same two failures, sync

docs/docs/python-sdk/topics/
└── error_handling.mdx              # New topic page (sidebar globs this directory)

changelog/                          # towncrier fragments: typed errors, identifier widening, broadening
pyproject.toml                      # per-file-ignore for the façade's re-export star imports
tasks.py                            # Add `exceptions` to packages_to_ignore for API-doc generation
```

Infrahub repository (`/Users/patrick/Code/opsmill/infrahub`, requirements FR-025 to FR-027):

```text
backend/templates/
└── generate_sdk_errors.j2          # New template: payload models, exception classes, resolution map
tasks/
└── backend.py                      # Renderer called from `generate`; diff added to validate_generated
.github/
└── workflows/ci.yml                # backend-validate-generated gains the catalogue trigger
```

The existing path filters need no change: a submodule artefact cannot be filtered on from the
superproject, and `sdk_files`, `backend_files`, and `error_catalogue_files` already cover the three
things that can change. See [research.md](./research.md) R2.

**Structure Decision**: `infrahub_sdk/exceptions.py` becomes the `infrahub_sdk/exceptions/` package,
with a strictly one-way import graph and no cycle anywhere in it:

```text
base.py      (written)    →  imports nothing from inside the package
catalogue.py (generated)  →  imports base
factory.py   (written)    →  imports base and catalogue
__init__.py  (written)    →  imports all of the above
```

Each module may import only from a strictly lower layer, and no module ever imports the package
façade — internal code always names the concrete submodule. `base.py` sitting at the bottom with no
intra-package imports at all is what the payload decision buys: because a payload's fields are promoted
to attributes rather than exposed as an object, no hand-written class needs to name a generated model
type, so the generated module needs no separate models module below `base.py` and no type-only import
to keep the hand-written hierarchy independent of generated code.

The rule is enforced by `tests/unit/sdk/test_exceptions_layering.py`, which parses each module and
fails on any upward import, so the property cannot decay silently. Every `from .exceptions import X`
in the codebase keeps working unchanged. See [research.md](./research.md) R1 and R6.

## Sequencing

Priority labels in the specification describe value, not order. The generator is US5 (P2) but produces
the per-code classes US1 (P1) delivers, so task ordering must follow the dependency: the Infrahub-side
generator and its first hand-verified run come first. FR-002 softens this — the envelope parses onto the
base classes with no bindings at all, so `code`, `http_status`, and the typed relogin decision (US4) are
independently landable — but the typed per-code classes are not. See [research.md](./research.md) R16.

## Cross-repository landing order

The SDK change lands first and Infrahub then bumps its submodule pointer to it — the pattern both
repositories already follow, and the only order under which Infrahub's content-level validation can
pass. See [research.md](./research.md) R17, which notes the one confirmation still worth getting.

## Complexity Tracking

No Constitution Check violations, so nothing to justify here.
