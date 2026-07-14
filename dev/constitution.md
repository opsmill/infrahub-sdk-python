<!--
Sync Impact Report
==================
Version change: (template placeholder) → 1.0.0
Rationale: Initial ratification. The file previously contained only unfilled
template tokens ([PRINCIPLE_1_NAME], [GOVERNANCE_RULES], ...); this is the first
concrete constitution, so it starts at 1.0.0 (MINOR/PATCH bumps do not apply to a
first ratification).

Principles defined (all new):
  - I.   Async/Sync Dual API Parity
  - II.  Backward Compatibility & Public API Stability
  - III. Layered Architecture
  - IV.  Type Safety & Typed Errors
  - V.   Test-First Development
  - VI.  Format & Lint Before Commit
  - VII. Documentation Accuracy (NON-NEGOTIABLE)

Sections added:
  - Core Principles (7 articles)
  - Additional Constraints (tech stack + boundaries)
  - Development Workflow & Quality Gates
  - Governance

Templates / artifacts reviewed for consistency:
  - .specify/templates/plan-template.md ...... ✅ no change needed
      (Constitution Check gate uses generic "[Gates determined based on
       constitution file]"; it reads this file at plan time, no hardcoded
       principle list to update)
  - .specify/templates/spec-template.md ...... ✅ no change needed (no constitution refs)
  - .specify/templates/tasks-template.md ..... ✅ no change needed (no constitution refs)
  - AGENTS.md / dev/knowledge/* .............. ✅ referenced as operational how-to; not duplicated

Deferred TODOs: none.
-->

# Infrahub Python SDK Constitution

The Infrahub Python SDK is a foundational library that abstracts the Infrahub API so
developers work with infrastructure data as native Python objects. It is consumed by
`infrahubctl`, the Infrahub Ansible collection, and external Python applications. Because
so much depends on it, the principles below are non-negotiable defaults, not aspirations.

## Core Principles

### I. Async/Sync Dual API Parity

Every public feature MUST ship on both `InfrahubClient` (async) and `InfrahubClientSync`
(sync) with matching method names, signatures, and behavior. The only sanctioned
asymmetry is functionality that is physically meaningless in one mode (e.g. a
concurrency/streaming helper with no coherent sync analog); such an exception MUST be
justified in the pull request and documented in the method's docstring. Internal helpers
(leading-underscore, not exported) are exempt.

Enforcement: surface parity is asserted by `tests/unit/sdk/test_client.py`
(`test_validate_method_signature`, `test_method_count`). New behavior MUST be exercised
by tests on **both** the async and sync path.

Rationale: the dual client is the SDK's signature contract. Divergence silently breaks
sync consumers and is the single most likely regression when new surface is added.

### II. Backward Compatibility & Public API Stability

The SDK makes a tiered stability promise:

- **Guaranteed**: names exported from `infrahub_sdk/__init__.py` (`__all__`), the public
  (non-underscore) methods of those classes, and documented `Config` fields.
- **Not guaranteed**: underscore-prefixed names and modules reached by deep imports that
  are not re-exported at top level. These may change in a MINOR release.

Breaking or removing a *guaranteed* surface MUST follow a deprecation path: first ship a
release that emits `DeprecationWarning` naming the replacement, keep the deprecated path
working for **at least one MINOR release**, and remove it only in a **MAJOR** release.
Breaking changes without this path require explicit maintainer approval (see the
`AGENTS.md` "ask first" gate on changing public API signatures).

Rationale: `infrahubctl`, the Ansible collection, and external applications pin and import
this library; an unannounced break is a break for all of them at once.

### III. Layered Architecture

Reusable logic — API interaction, data transformation, and domain rules — MUST live in
the SDK (`infrahub_sdk/`). Every first-party consumer (the CLI, the Ansible collection,
external apps) is a thin layer over it. Concretely, the CLI (`infrahub_sdk/ctl/`) is
limited to: argument parsing and local-only input validation, calls into SDK methods,
presentation via Rich, and error-to-exit-code handling via `@catch_exception`. It MUST NOT
use plain `print()` or instantiate `InfrahubClient` directly (use `initialize_client()`).

Test for a violation: *"Would a non-CLI consumer have to duplicate this logic to get the
same behavior?"* If yes, it belongs in the SDK, not the CLI. Detailed CLI rules — including
"don't pre-validate what the server validates" — live in
`dev/knowledge/cli-design-principles.md` and `dev/knowledge/cli-architecture.md`.

Rationale: logic stranded in the CLI is invisible to every other consumer and drifts from
the server it duplicates.

### IV. Type Safety & Typed Errors

All function signatures MUST carry type hints; both `ty` and `mypy` MUST pass clean.
Pydantic v2 models are used at configuration, API, and data boundaries. A type-check
suppression (`# type: ignore`, override) requires an inline justification.

Errors that a consumer could reasonably catch MUST be raised from the
`infrahub_sdk.exceptions` hierarchy (rooted at `Error`), using a **specific** subclass; a
new failure mode gets a new subclass rather than a bare `Exception`, `RuntimeError`, or a
generic reuse. Standard-library exceptions (`ValueError`, `TypeError`) are acceptable only
for local/programming errors a consumer would never be expected to catch.

Rationale: precise types and a typed exception hierarchy are the contract that lets
consumers handle failures deterministically instead of string-matching messages.

### V. Test-First Development

Every feature and bug fix MUST ship with tests in the same change; tests are never
deferred to a follow-up. A bug fix MUST include a test that reproduces the bug (fails
before the fix, passes after). New public surface MUST test both the async and sync paths
(see Principle I). Unit tests MUST be fast, mocked, and free of external dependencies;
behavior that needs a real server belongs in integration tests (testcontainers). Tests
MUST assert concrete expected values, not mere truthiness or non-null — an assertion that
cannot fail for the right reason is not evidence.

Rationale: tests written with the change, and reproduction tests for bugs, are the only
evidence a reviewer or agent can check that behavior is actually pinned.

### VI. Format & Lint Before Commit

Python code and documentation MUST pass the project's format and lint pipeline before
being committed — `uv run invoke format lint-code` for code and `uv run invoke lint-docs`
for documentation — and CI enforces the same pipeline. Nothing merges while these checks
are red, and linters or type-checkers MUST NOT be silenced without an inline
justification (see Principle IV).

The concrete tool list is intentionally kept out of this document (it changes over time);
it is defined by the invoke tasks and `AGENTS.md`.

Rationale: a green, uniformly formatted baseline keeps diffs about behavior, not style,
and keeps the review signal trustworthy.

### VII. Documentation Accuracy (NON-NEGOTIABLE)

Documentation MUST describe behavior that actually exists.

- **Generated docs**: whenever CLI commands, SDK configuration, or Python docstrings
  change, `uv run invoke docs-generate` MUST be run and the result committed;
  `docs-validate` MUST pass in CI. Generated artifacts — `protocols.py` and generated
  docs — are NEVER hand-edited.
- **Hand-written docs & examples**: MUST describe only behavior that exists (no
  aspirational or planned behavior presented as working), and MUST be updated in the
  **same pull request** as the behavior change they document.

Rationale: this is a public SDK for network automation engineers; an inaccurate example
does not merely confuse — it ships broken automation downstream. This principle is
non-negotiable and is not waived for schedule pressure.

## Additional Constraints

- **Tech stack**: Python 3.10–3.13, UV for dependency management, pydantic >= 2.0, httpx,
  graphql-core. Adding a new runtime dependency is an "ask first" decision (`AGENTS.md`).
- **Generated code**: `protocols.py` and generated documentation are produced by tooling
  and MUST NOT be edited by hand (reinforces Principles III and VII).
- **Boundaries of record**: `AGENTS.md` and the subdirectory guides
  (`infrahub_sdk/ctl/AGENTS.md`, `infrahub_sdk/pytest_plugin/AGENTS.md`,
  `tests/AGENTS.md`) hold the operational Always/Ask-first/Never lists that implement
  these principles.

## Development Workflow & Quality Gates

- Run `uv run invoke format lint-code` before committing Python code (Principle VI).
- Run `uv run invoke docs-generate` after creating, modifying, or deleting CLI commands,
  SDK config, or Python docstrings; run `uv run invoke lint-docs` before committing
  markdown (Principle VII).
- New features follow the async/sync dual pattern and ship with both-path tests
  (Principles I, V).
- Pull requests — whether authored by a human or a Spec Kit agent — MUST be reviewable
  against each principle above. A deviation MUST be called out and justified in the PR
  description (and, for complexity, in the plan's Complexity Tracking table).

## Governance

This constitution supersedes conflicting practices. Where it and `AGENTS.md` /
`dev/knowledge/*` disagree, this constitution wins; otherwise the constitution holds the
non-negotiable principles and those documents hold the operational how-to — they
cross-reference rather than duplicate.

**Compliance**: every pull request and review (including automated Spec Kit reviews of
specs, plans, and implementations) verifies compliance with these principles. Unjustified
deviations block merge.

**Amendments**: changes require a written proposal, maintainer approval, and an adoption
note describing any migration impact. The constitution is versioned with semantic
versioning:

- **MAJOR**: a principle is removed or redefined in a backward-incompatible way.
- **MINOR**: a new principle or section is added, or guidance is materially expanded.
- **PATCH**: clarifications, wording, and non-semantic refinements.

**Version**: 1.0.0 | **Ratified**: 2026-07-10 | **Last Amended**: 2026-07-10
