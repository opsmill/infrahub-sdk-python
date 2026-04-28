# Feature Specification: Marketplace Download Command Update

**Feature Branch**: `knotty-dibble`
**Created**: 2026-04-21
**Status**: Draft
**Input**: User description: "marketplace.infrahub.app is now live and has a new api no longer using graphql. Lets update that I also want the ability to autometically determine if the namespace is a collection or a schema. The ability to specify a version like so --version and also a custom destination path for the schema with the default being the schemas directory"

## Overview

The public Infrahub Marketplace at `marketplace.infrahub.app` is now live and exposes a REST API for distributing schemas and schema collections. The existing `infrahubctl marketplace get` command was designed against an earlier GraphQL-based interface and must be realigned with the new REST contract. Alongside that migration, users need a simpler, less error-prone download experience: one identifier argument that Works For Schemas And Collections alike, an optional pinned version, and predictable default output placement.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Download any published item by identifier (Priority: P1)

As a platform engineer bootstrapping a new Infrahub environment, I want to run a single `infrahubctl marketplace get <namespace>/<name>` command and have the tool figure out whether I'm asking for a single schema or a full collection so that I don't need to inspect the marketplace UI or remember which flag to pass.

**Why this priority**: This is the primary workflow for every marketplace user. Without automatic detection, every first-time user who types the command will either guess wrong or abandon the command line and revisit the web UI, undermining the value of the CLI.

**Independent Test**: Publish one schema and one collection to the marketplace (or mock the API), then run the download command twice — once against each identifier — without passing any type-hint flag. Both invocations succeed, write the correct files, and print the correct item type.

**Acceptance Scenarios**:

1. **Given** the identifier `acme/network-base` refers to a single schema on the marketplace, **When** the user runs `infrahubctl marketplace get acme/network-base`, **Then** the CLI downloads the schema file to the default destination and reports it was downloaded as a schema.
2. **Given** the identifier `acme/starter-pack` refers to a collection on the marketplace, **When** the user runs `infrahubctl marketplace get acme/starter-pack`, **Then** the CLI downloads every schema in the collection to the default destination and reports the collection totals.
3. **Given** the identifier does not match any published schema or collection, **When** the user runs the download command, **Then** the CLI fails with a clear message naming the identifier and the marketplace that was queried, and exits non-zero.

---

### User Story 2 - Pin a specific schema version (Priority: P2)

As a configuration author integrating a schema into a production pipeline, I want to pin to a specific published semver of a schema so that upstream updates do not silently change the shape of my data.

**Why this priority**: Reproducible builds are a must-have for any downstream automation that consumes marketplace content. Without a version pin, environments drift.

**Independent Test**: Publish at least two versions of the same schema, then run the download command with `--version <older>` and verify the older file contents are written rather than the latest.

**Acceptance Scenarios**:

1. **Given** schema `acme/network-base` has published versions `0.9.0` and `1.2.0`, **When** the user runs `infrahubctl marketplace get acme/network-base --version 0.9.0`, **Then** the CLI writes the `0.9.0` payload to disk and reports that version in its success output.
2. **Given** the user passes `--version` with a value that has not been published for the schema, **When** the command runs, **Then** the CLI fails with a message that distinguishes "version not found" from "schema not found" and exits non-zero.
3. **Given** the target identifier resolves to a collection, **When** the user also passes `--version`, **Then** the CLI warns that `--version` has no effect for collections and proceeds with the collection download.

---

### User Story 3 - Choose where files land (Priority: P2)

As a repository owner whose project uses a non-standard layout, I want to direct downloaded schemas into a specific folder so that the files match my repository conventions without a post-download move.

**Why this priority**: Users who store schemas outside the default `schemas/` directory currently have to run an extra move step, which is easy to forget and breaks automation.

**Independent Test**: Run the download against any identifier with `--output-dir ./custom/path` and confirm the files appear only in `./custom/path`, not in the default `schemas/` directory.

**Acceptance Scenarios**:

1. **Given** no `--output-dir` is provided, **When** the user downloads a schema, **Then** the file is written under `./schemas/` relative to the current working directory.
2. **Given** `--output-dir ./infra/schemas/marketplace` is provided and the directory does not yet exist, **When** the user downloads a schema or collection, **Then** the CLI creates the directory (including parents) and writes the payload there.
3. **Given** `--output-dir` points to a path the user does not have permission to write to, **When** the user runs the download, **Then** the CLI surfaces the filesystem error with the target path and exits non-zero without partial writes left in unrelated locations.

---

### Edge Cases

- A name collision exists between a schema and a collection under the same namespace (e.g. `acme/network` is both a single schema and a collection). The CLI must apply a deterministic, documented resolution order and make the choice visible to the user.
- The marketplace is unreachable, returns a 5xx, or the response is malformed. The CLI must fail with a network-oriented error message that names the host, not a Python traceback.
- The user overrides the marketplace base URL (e.g. for staging or an air-gapped mirror). Auto-detection and version resolution must honour the override.
- The same identifier has been published with only a pre-release version (no stable release yet). Default (no `--version`) behaviour must be defined: either download the latest pre-release with a warning, or fail with guidance to pass `--version`.
- A collection lists schemas that individually have no published version. The CLI must surface these as skipped entries alongside the successful downloads so the user sees a complete picture.
- The user passes an identifier missing the `/` separator, or with extra path segments. The CLI must reject the input with a usage message before any network call.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `infrahubctl marketplace get` command MUST communicate with the marketplace exclusively over its public REST API; no GraphQL usage for marketplace operations is permitted.
- **FR-002**: The command MUST accept a single positional identifier in `namespace/name` form and reject any other shape with a usage error before making network calls.
- **FR-003**: When no type-hint flag is passed, the command MUST automatically determine whether the identifier refers to a schema or a collection and download accordingly, reporting the resolved type in its output.
- **FR-004**: The command MUST expose a `--version` option that, when provided, pins the download to that specific published semver for a schema.
- **FR-005**: If `--version` is provided alongside an identifier that resolves to a collection, the command MUST warn that the flag is ignored and continue with the collection download rather than failing.
- **FR-006**: The command MUST expose an `--output-dir` option that defaults to `./schemas` and, when provided, redirects all downloaded files (schemas or collection members) beneath the supplied path.
- **FR-007**: The command MUST create any missing intermediate directories under the chosen output path before writing files.
- **FR-008**: The command MUST distinguish, in its user-facing error output, between "identifier not found", "version not found for identifier", "marketplace unreachable", and "user input invalid", and MUST exit with a non-zero status on any of these.
- **FR-009**: The command MUST honour a user-supplied marketplace base URL (via flag or configuration) for every network call it makes, including any calls used for auto-detection.
- **FR-010**: On success, the command MUST print, per downloaded file, the namespace, name, resolved version, and absolute or workspace-relative path on disk, and MUST print an aggregate summary for collection downloads (e.g. "N of M schemas downloaded, K skipped").
- **FR-011**: The `--collection` flag MUST remain available as an explicit override so users in automation contexts can force the collection code path and bypass auto-detection.
- **FR-012**: Name collisions between a schema and a collection sharing the same `namespace/name` MUST be resolved by a single documented precedence rule, and the CLI MUST print which type it resolved to so the user can detect an unintended match.

### Key Entities *(include if feature involves data)*

- **Schema**: A single published unit of Infrahub data model content, addressed by `namespace/name` and versioned by semver. Has a payload (YAML content) and metadata including the resolved version.
- **Collection**: A named, curated bundle of schemas under a single `namespace/name`. Enumerates its member schemas and, for each, either a successful entry (with content and version) or a skip reason.
- **Marketplace**: The remote catalogue service hosting schemas and collections. Addressed by a base URL that defaults to `https://marketplace.infrahub.app` but is overridable per-invocation or via configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time user can download any published schema or collection in a single command without reading the help text or toggling flags, in 100% of valid-identifier cases.
- **SC-002**: When a user supplies `--version`, the file written to disk is byte-identical to the payload stored for that version on the marketplace in 100% of cases.
- **SC-003**: When `--output-dir` is omitted, all downloaded content lands under `./schemas/` in 100% of runs; when it is supplied, zero files land outside the supplied path.
- **SC-004**: Error messages for the four distinct failure classes (not-found, version-not-found, network, invalid-input) are distinguishable by a human reader on first glance — validated by having a new user correctly classify each error in at least 90% of sampled cases.
- **SC-005**: Migrating existing scripts from the previous GraphQL-based command to the new one requires no change to their positional identifier or `--output-dir` arguments; only the removal of the explicit `--collection` flag is optional.

## Assumptions

- The marketplace REST API exposes separate endpoints (or response fields) that allow the CLI to distinguish schemas from collections without requiring the user to specify the type up-front. If the only way to distinguish is trial-and-error (probe schemas, then collections on 404), that trial is acceptable as long as it is transparent and bounded to one extra request.
- The default marketplace base URL is `https://marketplace.infrahub.app`, overridable via configuration or a flag.
- Schemas are versioned with semver and the marketplace returns the resolved version in a response header or body field so the CLI can echo it back to the user.
- The precedence rule for name collisions between a schema and a collection sharing the same `namespace/name` is **schema wins**, mirroring the previous default behaviour (download treated an identifier as a schema unless `--collection` was passed). Users relying on a collision must use `--collection` to disambiguate.
- The command downloads files only; it does not load schemas into a running Infrahub instance. Users who want to push downloaded content should chain with `infrahubctl schema load` (the earlier `--load` convenience was removed for simplicity and single-responsibility).
- Retention, telemetry, and auth on the marketplace side are out of scope for this client-side specification.

## Implementation Status *(informational, not part of acceptance)*

At time of writing (commit `Marketplace` on branch `knotty-dibble`) the following are **already implemented** in `infrahub_sdk/ctl/marketplace.py`:

- REST API calls against `/api/v1/schemas/...` and `/api/v1/collections/...` (FR-001).
- `--version` option for schemas (FR-004).
- `--output-dir` option defaulting to `schemas/` (FR-006, FR-007).
- Explicit `--collection` flag (FR-011).
- Distinct error paths for 404 vs. other HTTP errors (partial FR-008).

The following are **not yet implemented** and are the primary delta introduced by this spec:

- Auto-detection of schema vs. collection when `--collection` is not passed (FR-003).
- Warning behaviour when `--version` is combined with a collection identifier (FR-005, partial).
- Full four-way classification of error output (FR-008).
- Documented precedence rule for namespace/name collisions (FR-012).
