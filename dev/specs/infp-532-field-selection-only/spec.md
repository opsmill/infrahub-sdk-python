# Feature Specification: Field Selection with `only` and Known-State Field Access

**Feature Branch**: `field-selection-only-infp-532`

**Jira**: INFP-532

**Created**: 2026-10-02

**Status**: Draft

**Input**: Idea brief grilled with the maintainer on 2026-10-02 from the Notion PRD "Field Selection with only and Strict Field Access (INFP-532)" (<https://app.notion.com/p/opsmill/PRD-Field-Selection-with-only-and-Strict-Field-Access-INFP-532-8fd228b83025824d9f20810f1b502f3d>). The brief supersedes the PRD where they differ, and both supersede the exclusive-`include` approach on the INFP-532 card.

**Release shape**: the next 1.x minor release ships `only`, known-state tracking and warnings. The 2.0 release turns every warning into an error. This specification covers the 1.x deliverable in full and the 2.0 change as a single switch from warning to raising.

## Background

The node query methods (`get`, `all`, `filters` on both clients) fetch a **default set** of fields: every attribute, plus every cardinality-one relationship and every cardinality-many relationship of kind attribute or parent. Two parameters adjust it:

- `include` adds fields to the default set. It is the only way to add a cardinality-many relationship or a hierarchical field.
- `exclude` removes fields from the default set.

There is no way to ask for *less* than the default set without enumerating every other field in `exclude`, and that list goes stale whenever the schema grows. Queries therefore overfetch, and they get larger every time someone adds an attribute.

Separately, a field the SDK did not fetch reads as `None` (attributes, cardinality-one relationships) or `[]` (cardinality-many relationships). That is indistinguishable from a value that is genuinely empty. Nodes narrowed with `exclude`, nodes built from a custom GraphQL query, and nodes read after a save all report values the SDK never saw, and nothing fails.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Unknown fields announce themselves (Priority: P1)

A developer reads a field that the SDK was never told the value of. Instead of a silent `None` or `[]`, they get a visible warning that names the field and, where known, the selection the node was fetched with. The value returned is unchanged, so no existing code breaks in 1.x. A developer can also ask any attribute or relationship whether its value is known before reading it.

**Why this priority**: It fixes a data-correctness problem that exists today, independently of any new parameter, and it is the prerequisite that makes narrow selection safe. It ships on its own as the deprecation step for 2.0.

**Independent Test**: Build nodes from payloads that omit fields, from client-side data with and without an `id`, and after a save. Read each field and assert on the returned value, the presence and text of the warning, and the result of the known-state check.

**Acceptance Scenarios**:

1. **Given** a node fetched with `exclude=["description"]`, **When** the developer reads `description`, **Then** a `FutureWarning` names the field and the selection `exclude=['description']`, and the value is `None` as before.
2. **Given** a node fetched with the default selection, **When** the developer reads `node.tags.peers`, **Then** a `FutureWarning` names the `tags` relationship, and `[]` is returned as before.
3. **Given** a new node that has not been saved, **When** the developer reads an attribute or relationship they have not set, **Then** its empty value is returned with no warning.
4. **Given** a new node, **When** the developer assigns a value to any field, **Then** the assignment succeeds and the field reads back without a warning.
5. **Given** a node that was created and then saved, **When** the developer reads a field they never set, **Then** a warning is emitted, because the server may have applied a default the SDK did not read back.
6. **Given** a node built from client-side data that includes an `id` and `name` only, **When** the developer reads `description`, **Then** a warning says the field's origin is unknown.
7. **Given** a partially fetched node, **When** the developer modifies one field and saves it, **Then** the save succeeds, only the modified field is sent, and no warning is emitted by the save itself.
8. **Given** any fetched node, **When** the developer checks whether an attribute, a cardinality-one relationship or a cardinality-many relationship is known, **Then** the check returns `True` exactly when reading that field would not warn.

---

### User Story 2 - Exclusive selection with `only` (Priority: P2)

A developer passes `only` to a node query and gets exactly the named fields plus a fixed identity floor. Relationships named in `only` come back as references to their peers, not copies. Reading anything outside the selection raises immediately, from the first release, because `only` is a new contract with no existing callers.

**Why this priority**: It is the feature developers asked for: queries whose cost is predictable and does not grow with the schema. It depends on User Story 1's known-state tracking to be safe.

**Independent Test**: Generate queries with `only` present, absent and empty, compare them to expected query documents, and run reads against the resulting nodes on both clients.

**Acceptance Scenarios**:

1. **Given** `client.all(kind="BuiltinTag", only=["name"])`, **When** the query is generated, **Then** it requests `id`, `display_label`, `__typename` and `name` and nothing else, and reading `description` on a returned node raises the unknown-field error.
2. **Given** `only` naming a relationship, **When** the query is generated, **Then** the peer carries only `id`, `hfid`, `display_label` and `__typename`.
3. **Given** `only=[]`, **When** the query is generated, **Then** it requests the identity floor only, which differs from omitting `only`.
4. **Given** `only` combined with `include` or with `exclude`, **When** the call is made, **Then** a typed error is raised before any request is sent.
5. **Given** `only` containing a name that exists on no attribute or relationship of the kind, **When** the call is made, **Then** a typed error naming that field is raised before any request is sent.
6. **Given** no `only`, **When** any existing query runs, **Then** the generated query is unchanged.
7. **Given** `only=["name", "hfid"]`, **When** the query is generated, **Then** the queried node also requests its `hfid`.

---

### User Story 3 - Controlled peer hydration (Priority: P3)

Having fetched references to peers, a developer hydrates a relationship with a chosen set of peer fields in one call, including for relationships whose peers are of several kinds.

**Why this priority**: It completes `only` for relationship-heavy workloads, but references plus default hydration already deliver most of the value.

**Independent Test**: Hydrate cardinality-one and cardinality-many relationships with `only` and `exclude`, including a relationship to a generic, and assert on the requests sent and on which peer fields are readable.

**Acceptance Scenarios**:

1. **Given** a relationship whose peers carry only the identity floor, **When** the developer calls `fetch(only=["name"])`, **Then** the peers carry `name` plus the floor, and reading any other peer field raises.
2. **Given** a relationship whose peers are of several kinds (for example group members), **When** the developer calls `fetch(only=["name"])`, **Then** the names are validated once against the relationship's declared peer kind before any request, each concrete kind is asked only for the named fields it defines, and kinds without `name` receive the identity floor.
3. **Given** `fetch(only=[...], exclude=[...])`, **When** the call is made, **Then** the mutual-exclusion error is raised before any request.

---

### User Story 4 - Strict access switch for 2.0 (Priority: P4)

The SDK maintainers turn every User Story 1 warning into the typed error by changing one switch point, with no other code change, when cutting 2.0.

**Why this priority**: The 2.0 release itself is out of scope, but the switch must exist and be tested now so the flip is mechanical.

**Independent Test**: Run the User Story 1 scenarios with the switch set to strict and assert that each warning becomes the typed error with the same message, while scenarios 3, 4 and 7 still emit nothing.

**Acceptance Scenarios**:

1. **Given** the switch set to strict, **When** any User Story 1 read that warns in 1.x is repeated, **Then** the unknown-field error is raised with the same message as the warning.
2. **Given** the switch set to strict, **When** a new unsaved node's unset field is read, or a partially fetched node is modified and saved, **Then** no error is raised.

---

### Edge Cases

- `only=[]` versus `only` absent: an empty list means the identity floor, absent means the default set. A list computed down to empty must never silently mean "everything".
- A name in `only` that exists on the kind only as an inherited field while inherited fields are excluded from the query.
- A generic kind where a named field exists on some implementing kinds and not others, with fragments enabled and disabled.
- A node fetched broadly and then re-fetched narrowly with store population enabled: the store holds the narrower node. Unrelated code reading it then raises if `only` produced it, and warns otherwise.
- A relationship fetched as a reference (named in `only`, no hydration), when the caller resolves its peer: the not-found error points at hydration. A node fetched with `only=[]`, when the caller reads an attribute: the unknown-field message points at hydration.
- A node whose HFID depends on fields that were not fetched: it has no HFID and is stored by `id` only.
- A partially fetched node that is modified and saved: only modified fields are sent, and unfetched fields are neither read nor cleared.
- A node created or upserted without setting an optional field, then read: the field is unknown afterwards.
- A node built client-side with an `id`: only the fields it was given are known.
- Nodes built from GraphQL the SDK did not generate (`convert_query_response` in generators and transforms, the JSON importer, direct construction from a response): only the fields that GraphQL selected are known, and messages report an unknown origin.
- Hydrating peers of several kinds with `only`.
- Rendering a partially fetched node in the CLI.
- An identity floor name given in `only`: `id` and `display_label` are no-ops; `hfid` adds the queried node's HFID to the request.

## Requirements *(mandatory)*

### Functional Requirements

#### Selection

- **FR-001**: When `only` is provided to `get`, `all` or `filters` on either client, the generated query MUST contain only the named attributes and relationships plus the identity floor.
- **FR-002**: When `only` is not provided, selection behaviour MUST be unchanged.
- **FR-003**: `include` MUST keep its additive meaning and MUST NOT be deprecated.
- **FR-004**: `exclude` MUST keep its subtractive meaning and MUST continue to combine with `include` as it does today.
- **FR-005**: `only` combined with `include`, or with `exclude`, MUST raise the mutually-exclusive-selection error before any request is sent.
- **FR-006**: `only` MUST accept attribute and relationship names in one flat list.
- **FR-007**: `only=[]` MUST be valid and MUST produce a query for the identity floor only. It MUST be distinguishable from `only` being absent.
- **FR-008**: The names `id`, `hfid` and `display_label` MUST be accepted in `only` without error. `id` and `display_label` are always in the floor, so naming them is a no-op. Naming `hfid` requests the queried node's server-computed HFID, which the `only` floor otherwise leaves out.
- **FR-009**: A name in `only` that resolves to no attribute or relationship MUST raise the unknown-field-name error naming the offending field, before any request is sent.
- **FR-010**: For a generic kind, a name in `only` MUST be valid if it resolves on the generic or on any implementing kind.
- **FR-011**: For a generic kind, a name that resolves only on implementing kinds while fragments are disabled MUST raise an error that names fragments as the resolution.

#### Relationships and peers

- **FR-012**: A relationship named in `only` MUST fetch the peer identity floor (`id`, `hfid`, `display_label`, `__typename`) and nothing further.
- **FR-013**: `prefetch_relationships` MUST govern how much peer data is returned and MUST NOT affect which fields are members of the selection.
- **FR-014**: Hierarchical fields (`parent`, `children`, `ancestors`, `descendants`) MUST be fetched under `only` solely when named, and MUST then carry the same peer identity floor as other relationships.
- **FR-015**: The peer-hydration methods on cardinality-one and cardinality-many relationships, on both clients, MUST accept `only` and `exclude` under the same mutual-exclusion rule. They accept flat names only.
- **FR-016**: Hydration with `only` MUST validate names once, before any request, against the relationship's declared peer kind under the FR-010 rule, and MUST request from each concrete peer kind only the named fields that kind defines.
- **FR-017**: Under `only`, the queried node's envelope MUST request `id`, `display_label` and `__typename`, plus `hfid` only when named (FR-008). Without `only`, the envelope MUST stay as it is today (`id`, `hfid`, `display_label`, `__typename`), because the raw payload is observable through `get_raw_graphql_data()`, export files and the Ansible collection's module output. Peers MUST always request `hfid`.

#### Known state

- **FR-018**: The SDK MUST know a field if and only if (1) the field was present in the data the node was built from, (2) the caller has assigned it since, or (3) the node has no `id`. A field known only through rule 3 MUST read as its empty value: `None` for attributes and cardinality-one relationships, `[]` for cardinality-many relationships. This rule replaces the PRD's separate "unsaved" (FR-020) and "after save" (FR-021) rules.
- **FR-019**: Attributes, cardinality-one relationships and cardinality-many relationships MUST each expose the same known-state check, with one meaning: the SDK knows this field's value. Reading MUST warn or raise if and only if the check is false. The existing `initialized` flags on relationships MUST keep their current meaning.
- **FR-020**: Assigning a value to an attribute or a cardinality-one relationship the SDK does not know MUST always succeed and make the field known. Cardinality-many relationships keep their existing write contract: `add`, `extend` and `remove` raise `UninitializedError` until the relationship has been fetched or given data, because the SDK can't merge into a peer list it has never seen.

#### Unknown-field reads

- **FR-021**: Reading a field the SDK does not know MUST be detected for attribute values, cardinality-one relationships, and cardinality-many relationships (their peer list, peer ids, peer HFIDs, iteration and indexing), whatever produced the node.
- **FR-022**: In 1.x, a detected read MUST emit a warning and return the value the SDK returns today.
- **FR-023**: In 1.x, a detected read on a node produced by a query with `only`, on a peer of such a node, or on a peer hydrated with `only`, MUST raise the unknown-field error instead of warning.
- **FR-024**: A single switch point MUST turn every FR-022 warning into the unknown-field error with the same message. The switch stays on "warn" in 1.x.
- **FR-025**: The warning MUST use a category Python shows by default (`FutureWarning`), so that it reaches developers running generators inside the Infrahub pipeline.
- **FR-026**: The message MUST name the node's kind, the field and, when an SDK-generated query produced the node, the selection used. When no SDK-generated selection produced the node, the message MUST say the origin is unknown. When the node carries only the identity floor, the message MUST point at peer hydration. Separately, when resolving a relationship's peer fails because the peer was never fetched (the reference exists but no peer node is held), the existing not-found error MUST keep its type and its message MUST point at hydrating the relationship or using `prefetch_relationships`.
- **FR-027**: The SDK's own reads MUST NOT trigger the warning or the error. This covers HFID computation, mutation payload generation, store indexing, path-value resolution, CLI rendering, the CLI object update command, and the JSON importer.

#### Errors

- **FR-028**: The SDK MUST provide three new error types: unknown-field access, unknown name in `only`, and mutually exclusive selection parameters. Each MUST be a specific direct subclass of the SDK's base `Error`, and none MUST derive from `AttributeError`, `UninitializedError` or `ValueError`, so that no existing handler can absorb them. The existing `ValueError` raised when a name appears in both `include` and `exclude` MUST stay as it is.

#### HFID, store and CLI

- **FR-029**: When an HFID component is not known, HFID computation MUST return no value rather than warn or raise. Such a node MUST remain storable and retrievable by `id`.
- **FR-030**: CLI output MUST skip fields that are not known when rendering a node.

#### General

- **FR-031**: The async and sync clients MUST produce identical queries for identical arguments, and MUST warn and raise identically.
- **FR-032**: Every first-party call site that narrows a query MUST use `only`: relationship peer hydration (two sites, which today pass `include=[name]` plus an exhaustive `exclude`), the CLI generator group lookup, the CLI check group lookup, query groups (two sites), and the client repository lookup (an explicit six-field `include`).
- **FR-033**: The documentation MUST describe all three selection modes, the identity floor, known-state access and the 1.x/2.0 timeline. It MUST correct the description of `include`'s peer behaviour and the unfetched-relationship example in the query guide, which currently shows `[]` as the expected result.

### Key Entities

- **Selection** *(new)*: the resolved set of attributes, relationships and hierarchical fields for an SDK-generated query, derived from the caller's arguments and the node schema. It is recorded on the resulting node and its peers only when an SDK-generated query produced them, so that messages can report it. It also records whether `only` produced it.
- **Identity floor** *(new)*: the fields always present regardless of selection. For the queried node under `only`: `id`, `display_label`, `__typename`, plus `hfid` when named. For the queried node without `only`: today's envelope, `hfid` included. For peers: `id`, `hfid`, `display_label`, `__typename`.
- **Known state** *(new)*: a per-field fact on every attribute and relationship, governed by the FR-018 rule and exposed by the FR-019 check. It sits alongside the existing `initialized` flags and does not replace them.
- **Read policy** *(new)*: the single switch point (FR-024) that decides whether an unknown-field read warns or raises outside `only`.
- **Exception hierarchy**: gains the three error types in FR-028.
- **Client store**: unchanged. It already holds whatever was last fetched. This feature makes the consequences of a narrow node replacing a broad one visible, not silent.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every selection test case, a query restricted with `only` requests exactly the named fields plus the identity floor, verified by comparing the generated query with the expected one.
- **SC-002** *(post-release outcome measure, owned by `infrahub-sync`; not a release gate)*: On the measured `infrahub-sync` workload, a main load migrated to `only` transfers at least 45% fewer bytes, and a migrated deletion sweep at least 75% fewer, against the pre-change baseline.
- **SC-003** *(post-release outcome measure, owned by `infrahub-sync`; not a release gate)*: The measured interface sweep completes in under half its baseline wall-clock time after migration.
- **SC-004**: Upgrading without changing any application code requests exactly the same fields as the previous release, for 100% of existing selection test cases.
- **SC-005**: Every read that previously returned `None` or an empty list for a field that was not fetched now warns in 1.x and raises with the strict switch set, identifying the field, in 100% of the access-matrix cases.
- **SC-006**: A misspelt name in `only` is reported before any request is sent, in 100% of cases.
- **SC-007**: Building, saving and updating nodes needs no changes to existing application code, except code that reads, after a save, a field it neither set nor fetched. Verified by the existing test suite: tests change only where they read a field they never fetched or set, and each such change either asserts the new warning or widens the fixture.
- **SC-008** *(release gate)*: Adding attributes or relationships to a kind's schema leaves both the generated query and the response for an existing `only` call unchanged.

## Assumptions

- Code that reads cardinality-many relationships after a default `get`, without `include` or hydration, will warn in 1.x and raise in 2.0. Such code already receives `[]` whatever the server holds.
- Leaving a field out of a selection changes only what the server returns, not what it resolves or stores, including values that come from profiles. Fields that were not fetched are never sent on save.
- A read of an unknown field is a programming error. The fix is to widen the query or hydrate, not to catch the exception. Defensive checks are expected only where a node's provenance is genuinely unknown, such as reads from the client store.
- The savings baseline for SC-002 and SC-003 is the `infrahub-sync` validation recorded in `opsmill/infrahub-sync-lab` under `.planning/evidence/validation/val-29-results.md`. It was simulated with `exclude` while `hfid` was still requested, so the measured savings come from narrowing alone.
- `__typename` is resolved from the GraphQL schema and carries no database cost.

## Out of Scope

- Deprecating or removing `include` or `exclude`. All three modes are permanent.
- Any configuration setting that governs selection or access behaviour.
- Separate `attributes` / `relationships` parameters.
- Path syntax in `only` (for example `site__name`), deferred to a follow-up.
- Known-state access for attribute properties (`source`, `owner`, `is_protected`, …).
- Correcting `include`'s full peer expansion. Its owner and impact assessment across Infrahub are still to be decided.
- Reading never-set fields back in the mutation response after a save. This is a non-breaking follow-up that needs its own cost measurement.
- Removing `hfid` from peers.
- Removing `hfid` from the default (no `only`) query envelope. It is observable through raw GraphQL data, export files and the Ansible collection's module output, so it needs its own change with consumer notice.
- Allowing `add()` on a new node's cardinality-many relationship without a prior `fetch()`. Unchanged existing behaviour.
- Reworking the client store into an identity map, a static-analysis migration tool, and non-Python SDKs.
- The 2.0 release itself, beyond providing and testing the switch point.

## Known Divergences

- `include` expands peers in full, so `include=["tags"]` and `only=["tags"]` return different peer payloads in the same release. The documentation describes current behaviour.
- Attribute properties still read as `None` when they were not fetched.
- Peers still request `hfid`, because peer HFIDs, HFID-based peer removal and HFID de-duplication depend on it.
- Default queries still request `hfid` for the queried node. The brief proposed dropping it, but the critique found it's exposed through raw GraphQL data (see the critique report), so only `only` queries leave it out.
- In 1.x, nodes produced by `only` raise on unknown reads while every other node warns. This ends at 2.0.

## Dependencies and Governance

- **Changing public API signatures** (AGENTS.md "ask first"): a new `only` parameter on the query and hydration methods, a new known-state check, and changed read behaviour. Approved by the maintainer during the 2026-10-02 grilling.
- **New dependencies**: none.
- **Constitution II (backward compatibility)**: follows the standard path. Existing behaviour warns in a 1.x minor release and raises only in 2.0. `only` raises from its first release as part of a new contract.
- **Related work**: the GraphQL fragment inlining spec (`infp-496-graphql-fragment-inlining`) touches the same query-generation surface; no conflict.
