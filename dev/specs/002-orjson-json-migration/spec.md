# Feature Specification: Standardize SDK JSON serialization on orjson

**Feature Branch**: `dga/feat-orjson-pd5o6`

**Created**: 2026-07-14

**Status**: Draft

**Input**: Consolidate two related tech-debt items — "standardize the JSON library used across the SDK" and "adopt orjson for performance" — into a single migration that makes orjson the sole JSON library in `infrahub_sdk/`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Transparent JSON library migration (Priority: P1)

An engineer who builds automation on the SDK (transforms, generators, checks, imports/exports, and GraphQL round-trips) upgrades to the SDK version where JSON serialization is handled by a single, faster library. Their existing code runs unchanged and produces the same observable results, while JSON encoding and decoding on the hot path is faster.

At the same time, a contributor working inside the SDK now finds exactly one JSON library and one import convention across the package, removing the ambiguity of choosing between two libraries and the latent hazard of mismatched decode-error handling.

**Why this priority**: This is the entire feature. It is deliberately a single, atomic slice — splitting it would leave the codebase in a two-library intermediate state, which is precisely the ambiguity the work exists to eliminate.

**Independent Test**: Run the full existing unit and integration suite against the migrated SDK and confirm it passes with no behavioural changes to serialized output, hashing, or error handling; confirm no code in `infrahub_sdk/` references more than one JSON library.

**Acceptance Scenarios**:

1. **Given** an engineer running any existing SDK operation (query, export, generator, check, or `infrahubctl` JSON output), **When** they run it on the migrated SDK, **Then** the observable results are identical to the pre-migration behaviour.
2. **Given** query parameters containing only ASCII / integer / float / nested-dict values, **When** the SDK derives the tracking group name for those parameters, **Then** the derived name is identical to the pre-migration name.
3. **Given** malformed JSON returned from the API, **When** the SDK decodes it, **Then** the same decode-failure error is raised and caught as before.
4. **Given** a contributor searches `infrahub_sdk/` for JSON library usage, **When** they inspect imports, **Then** exactly one JSON library is present and no legacy JSON library remains.

### Edge Cases

- **Non-ASCII parameter values in tracking-group naming**: the derived group name changes once on upgrade for parameters containing non-ASCII characters (the new library emits raw UTF-8 where the old one emitted escaped sequences). The previously-created group is orphaned and a new one is created. This is an accepted, documented, one-time change and is pinned by a test vector.
- **Serialized output type**: serialization now yields bytes at the boundary; every place that requires text must convert explicitly so no consumer receives the wrong type.
- **Non-string dictionary keys**: the old library silently coerced non-string keys to strings; the new library must be configured to preserve that behaviour at sites that serialize arbitrary data, so previously-working payloads do not begin to fail.
- **Datetime rendering in CLI JSON output**: date/time values in `infrahubctl` JSON output must render in the same textual form as before, with no change visible to anyone parsing that output.
- **File-based serialization**: sites that read or write JSON directly to file handles must be rewritten, because the new library serializes and deserializes via in-memory bytes rather than file handles.
- **Human-facing pretty-printed output** (debug prints, test-failure diffs): indentation width may change cosmetically; this output carries no contract and is not compared programmatically.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The SDK MUST use a single JSON library throughout `infrahub_sdk/`; no module may reference the previously-used JSON libraries. *Acceptance*: a search of `infrahub_sdk/` finds zero references to the legacy libraries and lint passes.
- **FR-002**: The SDK MUST preserve JSON output byte-for-byte at every site where that output is consumed, compared, or shown to users, including preserving current indentation for machine-consumed output and preserving the current textual form of date/time values in CLI output. *Acceptance*: existing CLI/formatter tests pass unchanged.
- **FR-003**: The parameter-hashing behaviour that feeds tracking-group naming MUST return identical values for ASCII, integer, float, and nested-dictionary inputs, and MUST have its non-ASCII behaviour pinned by an explicit test vector. *Acceptance*: the hashing test retains its existing vectors and adds a non-ASCII vector asserting the new value.
- **FR-004**: The SDK MUST convert serialized output to text at every call site that requires text, so no consumer receives bytes where text is expected. *Acceptance*: type checking passes and the affected call sites' tests pass.
- **FR-005**: The SDK MUST correctly read and write JSON at every site that previously serialized directly to a file handle, adapting to in-memory serialization. *Acceptance*: a record-then-replay round-trip test passes.
- **FR-006**: The SDK MUST continue to catch malformed-JSON decode failures everywhere they are currently handled, with no gaps introduced by the library change. *Acceptance*: a decode test with invalid input raises and is caught as before.
- **FR-007**: The dependency manifest MUST add the new JSON library and remove the previous runtime library and its type stubs, with the lockfile refreshed. *Acceptance*: the manifest and lockfile reflect exactly this change and the project installs cleanly.
- **FR-008**: Non-string dictionary keys that previously serialized successfully MUST continue to serialize successfully at sites that handle arbitrary data. *Acceptance*: a serialization test with integer-keyed data passes.

### Key Entities *(include if feature involves data)*

- **Tracking group name**: an existing, persisted identifier derived in part from a hash of query parameters. Not a new entity; its derivation is affected only for non-ASCII parameter values (see Edge Cases). No change to its structure or public type.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero references to the legacy JSON libraries remain anywhere in `infrahub_sdk/`.
- **SC-002**: The full unit and integration test suite passes, and CLI/formatter output plus parameter-hash values for ASCII/integer/float inputs are byte-identical to the pre-migration baseline.
- **SC-003**: The migration ships as a single change with no split intermediate state in which two JSON libraries coexist in `infrahub_sdk/`.
- **SC-004**: Exactly one behavioural change is externally observable — the one-time tracking-group-name shift for non-ASCII parameters — and it is documented in the release notes.

## Assumptions

- Prebuilt distributions of the new JSON library are available for every supported interpreter (Python 3.10–3.14) on mainstream platforms, so end users do not build it from source.
- No downstream consumer depends on the CLI JSON date/time formatting beyond the textual form this migration preserves.
- Tracking-group name stability matters only for ASCII parameter values in practice; the one-time non-ASCII shift is acceptable churn.
- The performance benefit of the new library is well established; no benchmark harness or performance gate is in scope (parity is the bar). Verifying measurable speedups is explicitly out of scope for this migration.
- Scope is limited to `infrahub_sdk/`; JSON usage in tests is touched only where a test asserts serialized output.
- The parameter-hashing function keeps its current public signature and return type (text), so this is not a public API change.
