# Feature Specification: Fetch Only the Named Fields with `only`

**Feature Branch**: `ds/infp-532-only-field-selection`

**Created**: 2026-10-14

**Status**: Draft

**Input**: Idea brief for [INFP-532](https://opsmill.atlassian.net/browse/INFP-532), written after an internal product review (2026-08-28 to 2026-09-04). The brief is the reference for this feature. The INFP-532 card still describes an earlier proposal (making `include` exclusive) and was not updated. The branch `field-selection-only-infp-532` holds an earlier prototype, used for reference only.

## Background

When a developer queries nodes with `get()`, `all()` or `filters()`, the SDK requests a default set of fields: every attribute and most relationships of the kind. Two parameters change that set:

- `include` adds fields to the default set.
- `exclude` removes fields from the default set.

A developer cannot ask for only some fields. To fetch less, they list every unwanted field in `exclude`, and that list goes out of date each time someone adds a field to the schema. Queries therefore fetch more than the code reads, and they grow whenever the schema grows. Developers who write integrations, scripts and generators asked for a way to fetch only what they need ([INFP-532](https://opsmill.atlassian.net/browse/INFP-532)).

The INFP-532 card proposed making `include` exclusive. The product review chose a new parameter, `only`, so that no existing query changes. The same review asked that reading a field that was not fetched raise an error, instead of returning `None` as it does today after `exclude`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fetch only the named fields (Priority: P1)

A developer calls `client.all("InfraDevice", only=["name", "site"])` and gets devices that carry `name` and a reference to their site. The query requests those fields plus the fields the SDK needs to build a node, and it stays the same when the schema grows. When the code reads a field it did not name, the SDK raises an error that says which field was not fetched. The developer can check beforehand whether a field was fetched.

**Why this priority**: This is the request on INFP-532: queries whose size the developer controls and that do not grow with the schema.

**Independent Test**: Generate queries with `only` absent, empty and set to several lists against the test schemas, compare each query with the expected one, and read fields on the returned nodes, on both the async and the sync client.

**Acceptance Scenarios**:

1. **Given** the kind `InfraDevice`, **When** the developer calls `all(kind="InfraDevice", only=["name"])`, **Then** the query requests `id`, `display_label`, `__typename` and `name` for each device, and no other field.
2. **Given** the same call, **When** an attribute is added to `InfraDevice`, **Then** the generated query is unchanged.
3. **Given** a device returned by that call, **When** the developer reads `device.description.value`, **Then** `FieldNotLoadedError` is raised, naming `InfraDevice.description` and `only=['name']`.
4. **Given** the same device, **When** the developer checks `device.description.is_loaded`, **Then** it is `False` and nothing is raised.
5. **Given** `all(kind="InfraDevice", only=["name", "site"])`, **When** the query is generated, **Then** `site` is requested as a reference to the peer: `id`, `hfid`, `display_label` and `__typename`.
6. **Given** the same call with `prefetch_relationships=True`, **When** the query is generated, **Then** the site is requested with its default fields, and no relationship other than `site` is requested.
7. **Given** a call that does not pass `only`, **When** the query is generated, **Then** it is the same as before this feature.

---

### User Story 2 - Fetch chosen fields of a peer (Priority: P2)

A developer who fetched a device with `only=["site"]` holds a reference to the site. They call `device.site.fetch(only=["name"])` and read the site's name, without fetching every default field of the site and without writing a second query by hand.

**Why this priority**: It completes User Story 1 for relationships. Without it, reading one field of a peer needs `prefetch_relationships=True`, which fetches every default field of the peer and grows with the peer's schema. It depends on User Story 1 and is tested on its own.

**Independent Test**: Call `fetch(only=[...])` on cardinality-one and cardinality-many relationships, including a relationship whose peers are of several kinds, and check the queries sent and which peer fields can be read, on both clients.

**Acceptance Scenarios**:

1. **Given** a device fetched with `only=["site"]`, **When** the developer calls `device.site.fetch(only=["name"])`, **Then** one query for the site requests `id`, `display_label`, `__typename` and `name`, and `device.site.peer.name.value` returns the site's name.
2. **Given** the same site, **When** the developer reads `device.site.peer.description.value`, **Then** `FieldNotLoadedError` is raised.
3. **Given** a cardinality-many relationship whose peers are of several kinds, **When** the developer calls `fetch(only=[...])` with a name that one of those kinds does not have, **Then** the unknown-field error is raised before the peer queries are sent.

---

### Edge Cases

- **Empty list**: `only=[]` fetches `id`, `display_label` and `__typename` only. Not passing `only`, or passing `None`, keeps the default set.
- **Misspelt name**: `only=["nmae"]` raises the unknown-field error before the data query is sent, naming `nmae` and the kind.
- **Fields that are always fetched**: `id` and `display_label` in `only` are accepted and change nothing.
- **`hfid` in `only`**: requests the HFID that the server stores for each node, and none of the fields it is made of. `node.hfid` returns that value until a field the HFID is built from is changed on the node; from then on it is calculated from the fetched fields. For a kind without an HFID, naming `hfid` changes nothing.
- **Client store**: a node from `only` goes into the store and can replace a fuller copy of the same node. Code that later reads it from the store gets `FieldNotLoadedError` for the fields it lacks, and can check `is_loaded` first. The SDK's own HFID calculation does not raise when it reads such a node from the store: for any node, a field that the stored node lacks counts as missing.
- **Saving**: saving a node from `only` sends `id` and the changed fields only. Fields that were not fetched are neither sent nor cleared on the server.
- **HFID that cannot be calculated**: `node.hfid` on a node from `only` is `None` when `hfid` was not named and its HFID fields were not fetched, and when `hfid` was named and the server returned an empty value.
- **Reference without a stored peer**: `device.site.peer` on a reference raises the existing `NodeNotFoundError` when the site is not in the store, as after a default query today.
- **New node after saving**: after a node the developer created is saved, the fields it never set have `is_loaded` `False`. Reading them raises only on nodes from `only`; on other nodes they behave as today.
- **Generic kinds**: when only some kinds that implement a generic have a named field, the field is fetched for the nodes of those kinds.

## Requirements *(mandatory)*

### Functional Requirements

#### Choosing fields on the query methods

- **FR-001**: Users MUST be able to pass `only=[...]` to `get()`, `all()` and `filters()` on `InfrahubClient` and `InfrahubClientSync`. For the queried nodes and their peers, the query MUST request the fields FR-002 to FR-007 define, and no other field. The query's filters, ordering, pagination and `count` stay as they are today, and so does the data that `property=True` and `include_metadata=True` add for the requested fields.
- **FR-002**: For the queried node, a query with `only` MUST fetch `id`, `display_label` and `__typename`, plus the named attributes and relationships. The server's `hfid` field MUST be fetched for the queried node only when `only` names `hfid` (FR-005).
- **FR-003**: A relationship named in `only` MUST return its peers as references (`id`, `hfid`, `display_label`, `__typename`), as a relationship in the default set does today.
- **FR-004**: With `prefetch_relationships=True`, the peers of the relationships named in `only` MUST come back with their default fields. Relationships not named in `only` MUST NOT be queried.
- **FR-005**: In `only`, `id` and `display_label` MUST be accepted and change nothing. `hfid` MUST request the server's stored `hfid` field on the queried node, and no field, relationship or peer that the HFID is made of. On a node from that query, `hfid`, `hfid_str`, `get_human_friendly_id()` and `get_human_friendly_id_as_string()` MUST return the server's value, or `None` when that value is empty or null, and the client store MUST index the node by it. Once a field the HFID is built from is changed on the node, they MUST be calculated from the fetched fields instead, so they never return a value that no longer matches the node. When `hfid` is not named, they MUST be calculated from the fields the node fetched, and be `None` when a part was not fetched. For a generic kind, `hfid` MUST be requested when the generic or any kind implementing it has an HFID. For a kind without an HFID, naming `hfid` MUST change nothing.
- **FR-006**: `parent`, `children`, `ancestors` and `descendants` MUST be fetched only when named in `only`. When named, they follow FR-003 and FR-004 like any other named relationship: references, or their peers' default fields when `prefetch_relationships=True`.
- **FR-007**: `only=[]` MUST fetch `id`, `display_label` and `__typename` only. Not passing `only`, or passing `None`, MUST keep the default set.

#### Checking the names

- **FR-008**: A name in `only` that is not a field of the kind MUST raise a new typed error before the data query is sent, naming the field and the kind. For a generic kind, a name is known if the generic or any kind implementing it has the field.
- **FR-009**: Combining `only` with `include` or with `exclude` MUST raise a new typed error before any request is sent.

#### Reading fields on nodes from `only`

- **FR-010**: Reading a field that a node from `only`, or a peer returned with it, does not carry MUST raise `FieldNotLoadedError`, naming the kind, the field and the `only` list. Saving, upserting, calculating the HFID and storing such a node MUST NOT raise.
- **FR-011**: Users MUST be able to check `is_loaded` on any attribute, cardinality-one relationship and cardinality-many relationship. It MUST be `True` when the response contained the field, when the user assigned the field since, or when the node has no `id` yet, and `False` otherwise. Reading `is_loaded` MUST never raise.

#### Choosing fields when fetching peers

- **FR-012**: Users MUST be able to pass `only=[...]` to `fetch()` on `RelatedNode`, `RelatedNodeSync`, `RelationshipManager` and `RelationshipManagerSync`. Peers MUST come back with only the named fields plus `id`, `display_label` and `__typename`, and reading a field they do not carry MUST raise as FR-010 defines. Every name MUST exist on every peer kind being fetched; otherwise the FR-008 error MUST be raised before the peer queries are sent.

#### Keeping existing behaviour

- **FR-013**: `include` and `exclude` MUST keep their current behaviour and MUST NOT be deprecated. Unknown names in `include` and `exclude` MUST stay ignored, as today.

### Key Entities

- **Node, attribute, relationship, peer, client store**: existing; unchanged for nodes not fetched with `only`.
- **`only` parameter** *(new)*: the list of field names the developer wants, on the query methods and on `fetch()`. Not passed or `None` means the default set; an empty list means `id`, `display_label` and `__typename` only.
- **Reading a field**: for an attribute, reading its value; for a cardinality-one relationship, reading its peer or the peer's identifiers; for a cardinality-many relationship, reading its list of peers. Accessing the attribute or relationship itself, for example to check `is_loaded`, is not reading it.
- **`is_loaded`** *(new)*: a property on attributes and on both kinds of relationship that says whether the SDK holds the field's value.
- **"The response contained this field" record** *(new, internal)*: kept for each field when a node is built from a server response, and used by `is_loaded`. Not public.
- **Errors** *(new)*: `FieldNotLoadedError`, one error for an unknown name in `only`, and one error for combining `only` with `include` or `exclude`. All three are subclasses of the SDK's base `Error`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every case in the test schemas, a query with `only` requests exactly the fields FR-002 to FR-007 define, on both clients.
- **SC-002**: Adding attributes or relationships to a kind, or to a kind that implements it, leaves the query for an existing `only` call unchanged, unless the added field is one of the names in `only`.
- **SC-003**: Upgrading without changing code leaves every default, `include` and `exclude` query exactly as before.
- **SC-004**: A misspelt name in `only` is reported before the data query is sent, in every case.
- **SC-005**: On nodes from `only`, reading a field they do not carry raises `FieldNotLoadedError` in every case, and `is_loaded` is `False` exactly in those cases.
- **SC-006** *(measured after release, not a release gate)*: on the `infrahub-sync` workload measured for the PRD, a load migrated to `only` transfers fewer bytes than the baseline. No target number is set.

## Constitution Alignment

- **I. Async/sync parity**: every new parameter, property and error is available on both clients and tested on both.
- **II. Backward compatibility**: an additive feature. `only` is placed after the existing parameters; SC-003 checks that existing queries do not change.
- **III. Layered architecture**: all logic lives in the SDK; the CLI does not change.
- **IV. Typed errors**: three new subclasses of `Error`.
- **V. Test-first**: tests ship in the same pull request, on both clients.
- **VII. Documentation accuracy**: the query guide documents `only`, `is_loaded` and `fetch(only=...)` in the same pull request. The `only` section describes `only` only and makes no claims about the peers that `include` returns.

## Governance Gates Crossed

- **Changing public API signatures**: additive. Validated in the product review; no separate approval is needed (owner).
- **Adding new dependencies**: none.

## Assumptions

- Leaving a field out of `only` changes only what the server returns, not what it resolves. Values that come from profiles are unaffected.
- The client store keeps the most recent copy of each node ([opsmill/infrahub-sdk-python#413](https://github.com/opsmill/infrahub-sdk-python/issues/413) is unresolved). This feature does not wait for [opsmill/infrahub-sdk-python#1120](https://github.com/opsmill/infrahub-sdk-python/pull/1120).
- The INFP-532 card is not updated. The idea brief and the product review are the reference for the parameter.

## Out of Scope

- Changing or deprecating `include` or `exclude`, and correcting the `include` section of the query guide.
- From the prototype branch: the warning on reads of unfetched fields for all other nodes, and the switch that turns those reads into errors in 2.0.
- From the prototype branch: moving the SDK's own queries to `only` (query groups, `infrahubctl generator`, `infrahubctl check`) and changes to CLI output.
- `fetch(exclude=...)`.
- Path syntax in `only`, such as `site__name`.
- Removing `hfid` and `display_label` from peer references.
- Using the server's `hfid` for `node.hfid` on nodes not from `only`, or on nodes from `only` whose query did not name `hfid`.

## Follow-ups (outside this feature)

- Comment on [opsmill/infrahub-sdk-python#1120](https://github.com/opsmill/infrahub-sdk-python/pull/1120) that it can reuse the internal "the response contained this field" record instead of adding a public `is_fetched`.
- `infrahubctl object update --set` on a cardinality-many relationship: the prototype's implementation report says it reports success but sends no peers. Reproduce it and fix it in its own pull request.
- Agree with the prototype's author on closing the branch `field-selection-only-infp-532`.
