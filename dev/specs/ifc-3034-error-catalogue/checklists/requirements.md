# Specification Quality Checklist: Error Catalogue in the Python SDK

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-21
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

Two checklist items were resolved by scoping rather than by rewriting, and the reasoning is recorded
here so the plan phase does not relitigate it:

- **"No implementation details" / "written for non-technical stakeholders"** — for a library, the
  exception hierarchy *is* the user-facing product, so class names, catalogue codes, and the
  transport split are domain vocabulary rather than implementation leakage. The spec names those and
  deliberately withholds module layout, file names, generator implementation, and test mechanics.
  Recorded as an explicit assumption in the spec rather than left implicit.
- **"Success criteria are technology-agnostic"** — SC-001 through SC-008 are stated as outcomes a
  consumer or reviewer can verify (a failure is handleable without reading a message; no string
  matching remains; a stale artefact fails validation) rather than as internal mechanics. They do
  reference exceptions and catalogue codes, which is unavoidable and correct for this feature.

Two items were originally deferred to the plan and have since been pulled back into the spec, both
prompted by automated review of the pull request:

- **The `identifier` contract on the unified `NodeNotFoundError`.** Deferring the whole question was
  wrong: *which* attributes a consumer can read is observable API surface and belongs here, even
  though the mechanism does not. FR-016 now pins the contract — every construction shape in use today
  keeps working, the server-reported kind and identifier are reachable, one documented accessor works
  for both cases, and any type widening is called out in release notes. Surveying the code for this
  also turned up that the attribute is *already* heterogeneous: the file handler passes a plain string
  where the declared type is a mapping.
- **Multi-error precedence.** FR-013 originally required only that a rule exist, which is untestable
  until the rule does. It now specifies that the first error in the response governs, with the
  complete list retained, and records why first-*recognised* was rejected: it would make the raised
  type depend on binding freshness rather than on the response.
