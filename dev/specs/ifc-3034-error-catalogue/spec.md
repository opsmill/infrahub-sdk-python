# Feature Specification: Error Catalogue in the Python SDK

**Feature Branch**: `pog-error-catalogue-IFC-3034`

**Created**: 2026-08-21

**Status**: Draft

**Input**: IFC-3034 — Implement the error catalogue in the Python SDK. Related: IFC-2279 (spike), INFP-468 (backend catalogue), GitHub #7498.

## Context

Infrahub's GraphQL error catalogue gives every GraphQL error a stable string `extensions.code`, an
integer `extensions.http_status`, and a typed `extensions.data` payload, published as a
machine-readable schema at `schema/error-catalogue.json` in the Infrahub repository. The frontend
already consumes it through generated TypeScript bindings.

The SDK consumes none of it. `execute_graphql` raises a generic `GraphQLError` whose message embeds
the entire query text, and consumers that need to branch on a failure still match on message
strings. This feature makes ordinary SDK operations raise the specific error for the failure.

Two wire shapes matter, and they are not the same:

- **`/graphql`** carries the catalogue envelope: string `code`, integer `http_status`, typed `data`.
- **`/api/...` (REST)** carries the legacy envelope, where `extensions.code` is an *integer*
  mirroring the HTTP status. There is no catalogue code and no `data`.

The catalogue is therefore GraphQL-only, and a REST `extensions.code` is a different thing with a
different type that must never be mistaken for a catalogue code.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Branch on a specific server failure (Priority: P1)

A developer writing automation against Infrahub needs to react differently to different failures. A
`.save()` that collides on a uniqueness constraint should be distinguishable from a validation
failure, and the collision detail should be available as attributes rather than parsed out of prose.

**Why this priority**: This is the feature. Everything else either protects it or maintains it.

**Independent Test**: Drive each catalogued failure against a server (or a fixture of its response
envelope) and assert the raised type and the typed attributes carrying its detail, without reading any
message.

**Acceptance Scenarios**:

1. **Given** a node whose unique attribute already exists, **When** the developer calls `.save()`,
   **Then** `UniquenessViolationError` is raised carrying the node kind and the colliding field names
   as typed attributes.
2. **Given** a node that no longer exists, **When** the developer calls `.delete()`, **Then**
   `NodeNotFoundError` is raised carrying the node kind and identifier.
3. **Given** any catalogued failure, **When** it is raised, **Then** `exc.code` equals the catalogue
   code string and `exc.http_status` equals the catalogue status.
4. **Given** a developer who catches `GraphQLError` today, **When** a catalogued GraphQL failure
   occurs, **Then** the specific subclass is caught by that existing clause.

---

### User Story 2 - Keep working against any server version (Priority: P1)

The SDK and the server are versioned and released independently, so any SDK version may talk to any
server version. Neither direction may break.

**Why this priority**: The ticket states this is a hard requirement, not a nice-to-have. User Story 1
is not shippable without it — typed errors that raise on an unrecognised payload would be a
regression, not a feature.

**Independent Test**: Replay response fixtures representing a newer server, an older server, and a
pre-catalogue server against the parsing layer, asserting no parse failure and correct fallback in
each case.

**Acceptance Scenarios**:

1. **Given** a code the SDK has never heard of, emitted by a newer server, **When** the SDK raises,
   **Then** it raises the generic fallback for that transport branch with `exc.code` readable as a
   plain string, and does not raise on parse.
2. **Given** an existing code whose payload has gained a new attribute in a newer server, **When**
   an older SDK parses it, **Then** the unknown attribute is ignored and behaviour is unchanged.
3. **Given** a server that predates the catalogue, or an error carrying no `extensions`, **When** the
   SDK raises, **Then** behaviour matches today's and `exc.code` is `None`.
4. **Given** a pre-catalogue server emitting an *integer* `extensions.code` on `/graphql`, **When**
   the SDK parses it, **Then** it is not surfaced as a catalogue code and `exc.code` is `None`.
5. **Given** any of the above, **When** the developer regenerates nothing, **Then** correctness is
   unaffected — regeneration buys typed handling of newly catalogued errors, never correctness.

---

### User Story 3 - Catch server-reported errors uniformly across transports (Priority: P2)

Authentication failures reach the developer from both the REST and GraphQL paths. Today they collapse
into a single `AuthenticationError` that cannot distinguish "no credentials" from "token expired"
from "not permitted". The catalogue splits these into three codes, and the SDK needs a hierarchy
where that split is expressible without stranding the REST path.

**Why this priority**: It restructures the hierarchy every other story hangs off, but User Story 1
delivers value with the existing flat `AuthenticationError` still in place.

**Independent Test**: Assert the class hierarchy directly, and assert that each existing `except`
clause in the SDK and CLI still catches what it caught before.

**Acceptance Scenarios**:

1. **Given** a GraphQL request with an expired token, **When** it fails, **Then** `TokenExpiredError`
   is raised and is caught by an existing `except AuthenticationError` clause.
2. **Given** a GraphQL request the user is not permitted to make, **When** it fails, **Then**
   `PermissionDeniedError` is raised, distinguishable from a missing-credentials failure.
3. **Given** a REST request that fails authentication, **When** it fails, **Then**
   `AuthenticationError` is raised as it is today, with `exc.code` as `None`.
4. **Given** a developer who wants to catch anything the server rejected regardless of transport,
   **When** they catch `ApiError`, **Then** both GraphQL and auth failures are caught.

---

### User Story 4 - Stop the SDK string-matching its own server (Priority: P2)

The SDK's silent token-refresh path decides whether to re-login by matching the literal string
`"Expired Signature"` in the response body. The catalogue makes that a typed decision.

**Why this priority**: A correctness improvement to existing behaviour, valuable independently, but
it depends on the envelope parsing from User Story 1.

**Independent Test**: Drive the relogin path with a catalogue `TOKEN_EXPIRED` envelope, with the
legacy string on a pre-catalogue server, and with an unrelated 401, asserting a refresh is attempted
in the first two cases and not the third.

**Acceptance Scenarios**:

1. **Given** a 401 carrying `TOKEN_EXPIRED`, **When** the SDK receives it, **Then** it refreshes the
   token and retries, without inspecting any message text.
2. **Given** a 401 from a pre-catalogue server carrying the legacy `"Expired Signature"` message,
   **When** the SDK receives it, **Then** it still refreshes and retries.
3. **Given** a 401 that is neither, **When** the SDK receives it, **Then** no refresh is attempted.

---

### User Story 5 - Bindings that cannot silently drift (Priority: P2)

A catalogue change that is not reflected in the SDK's bindings must surface as a failure, in the
change that caused it, rather than as silence that is noticed months later when a code falls back.

**Why this priority**: Without it the typed errors decay. It is P2 rather than P1 only because the
first generation can be landed and verified by hand once.

**Independent Test**: Modify the catalogue without regenerating, and confirm the validation step
fails; regenerate, and confirm it passes.

**Acceptance Scenarios**:

1. **Given** a change to the catalogue in the Infrahub repository, **When** the bindings in the SDK
   submodule are not regenerated, **Then** Infrahub's generated-artefact validation fails the pull
   request that changed the catalogue.
2. **Given** a regenerated set of bindings, **When** validation runs, **Then** it passes and the
   generated file is byte-identical to a fresh generation.
3. **Given** the generated bindings file, **When** a developer opens it, **Then** it is marked as
   generated and not to be edited, consistent with the repository's other generated artefacts.

---

### User Story 6 - Messages that are about the failure (Priority: P3)

`GraphQLError`'s message embeds the whole query text, so a one-line failure produces a wall of
output in logs and CLI sessions.

**Why this priority**: Observable quality-of-life improvement, no functional dependency either way.

**Independent Test**: Trigger a catalogued failure and an uncatalogued one, and compare their
messages.

**Acceptance Scenarios**:

1. **Given** a catalogued failure, **When** its message is rendered, **Then** it names the code and
   the server's message and does not contain the query text.
2. **Given** an uncatalogued failure, **When** its message is rendered, **Then** it is unchanged from
   today's, query text included.
3. **Given** any GraphQL failure, **When** a developer needs the query, **Then** it is still
   available on the exception.

### Edge Cases

These are specific hazards found while surveying the current code, not hypotheticals.

- **Ordered `isinstance` ladder is shadowed.** The CLI's error handler tests
  `isinstance(exc, GraphQLError)` *before* it tests
  `isinstance(exc, (SchemaNotFoundError, NodeNotFoundError, ...))`. Re-rooting those classes under
  `GraphQLError` makes the later branch unreachable, silently changing CLI output for exactly the
  errors this feature makes specific. The ladder must be reordered, and the same shadowing hazard
  checked wherever else the SDK or CLI tests these classes in sequence.
- **A GraphQL error renderer with no server errors to render.** The CLI's `GraphQLError` branch
  renders `exc.errors`, which is a list of server error dicts. A unified `NodeNotFoundError` raised
  purely client-side has no server response behind it, so that list is empty. Rendering must degrade
  to the message rather than printing nothing.
- **`identifier` already means two different things.** The client-side `NodeNotFoundError` declares
  `identifier` as a mapping of filters, and the store and client lookup paths pass one. The file
  handler, however, already passes a plain string, which the declared type does not admit — so the
  attribute is heterogeneous today, before any unification. The catalogue payload adds a third
  reading: a single server-side identifier string. Unification does not create this problem, it
  forces a decision on it. FR-016 pins the resulting contract; the mechanism is left to the plan.
  Nothing in this repository reads the attribute except the exception's own string rendering, so the
  compatibility risk is entirely external.
- **A subclass inherits the re-rooting.** `NodeInvalidError` subclasses `NodeNotFoundError`, so it
  silently becomes a `GraphQLError` too. Intended, but it must be asserted rather than assumed.
- **Pre-existing constructor misuse, in two places.** One call site constructs `GraphQLError` with a
  plain string where the constructor expects a list of error dicts, so `errors` holds a string; another
  passes a list whose single element is not a dict. Any code that now iterates `errors` to resolve a
  code will meet both. Re-rooting makes this worse before it makes it better: once a class inherits a
  constructor whose *first positional parameter* is `errors`, passing a message positionally silently
  produces the same corruption.
- **A message-matching test inside our own suite.** At least one existing test asserts on
  `GraphQLError`'s message text. Message changes must be reflected in the suite deliberately, not
  worked around.
- **More than one error in one response.** A GraphQL response may carry several errors with different
  codes. The rule for which code determines the raised class must be explicit, and no error may be
  discarded from the exception.
- **`UNDEFINED_ERROR` is a code, not the absence of one.** A server that explicitly says
  `UNDEFINED_ERROR` is reporting a catalogue gap on its side. That is distinct from an error carrying
  no `extensions` at all, and the two must not collapse.
- **Codes with no payload.** Several codes declare an empty payload object. These must still produce
  a usable class rather than a special case.
- **Silent-refresh runs on both transports.** The relogin wrapper inspects raw responses from REST
  *and* GraphQL calls, but only GraphQL carries the catalogue envelope. It must read the code where
  one exists and fall back to the legacy check where one does not.
- **GraphQL data errors arrive as HTTP 200, and so do some auth failures.** Catalogued data errors
  come back with status 200 and an `errors` array. Only auth failures that escape *before* query
  execution come back as real 401/403 responses on a separate code path; a permission or
  authentication failure raised inside a resolver is formatted at the GraphQL layer and returned in
  the 200 response's `errors` array like any other error. So the transport a code arrives on cannot be
  inferred from the code, and a code's declared `http_status` is metadata about the failure rather than
  the status the SDK saw. The declared status can also differ from the status on the wire: the server
  replaces a declared 500 with the real HTTP status when it has a more accurate one.

## Requirements *(mandatory)*

### Functional Requirements

#### Envelope parsing

- **FR-001**: The SDK MUST expose a base class representing "the server reported an error", carrying
  the catalogue code, the HTTP status, the raw error envelope, and the server's error list, from which
  both the GraphQL and the authentication branches descend. The base MUST NOT declare an attribute for
  the typed payload: a payload's fields belong to the specific class that has a type for them, and a
  base-level payload attribute could only be typed loosely enough to be useless.
- **FR-002**: The SDK MUST parse the error envelope onto the shared base class of FR-001 — not onto the
  generated per-code classes — so the code is readable against any server version without regenerated
  bindings.
- **FR-003**: The code attribute MUST always exist, holding either a catalogue code string or `None`.
  Reading it MUST NOT raise, so a consumer can test it without first testing which class it holds. The
  REST envelope's integer `code` MUST NOT be surfaced through it; the HTTP status is already available
  separately.
- **FR-004**: Payload parsing MUST tolerate unknown fields, which is the inverse of the server's
  strict emission contract. Where a payload does not validate at all, the operation MUST fall back to
  the generic class for the branch, with the code still readable, and MUST NOT raise from parsing.
  This case is reachable rather than defensive — the server has a fallback path that emits an empty
  payload under a code whose schema declares required fields.

  Rationale: the specific class exposes the payload's fields as attributes typed exactly as the
  catalogue declares them, so a required field is not optional. There is nothing to populate those
  attributes with when validation fails, and the alternative — making every payload attribute
  optional on every class — would tax every consumer of the feature's central use for a narrow
  server-side glitch. Note that this does not weaken FR-013: payload validity is a property of the
  response, so the raised class remains a function of the response alone and never of which
  generated bindings the SDK holds.

#### Generated bindings

- **FR-005**: Every catalogue code MUST have one exception class, rooted at the SDK's base `Error`
  class, and one typed payload model. Both MUST be importable from `infrahub_sdk.exceptions`, but the
  payload model is the parsing mechanism rather than the access path: each of its fields MUST be
  reachable as a directly typed attribute on the exception itself, typed as the catalogue declares it.
  Every name importable from `infrahub_sdk.exceptions` before this change MUST remain importable from
  it afterwards, and that MUST be pinned by a test rather than asserted, since the module is being
  restructured.
- **FR-006**: Exception class names MUST derive from the code deterministically, without producing a
  doubled `Error` suffix for codes that already end in `_ERROR`. A derived name that collides with an
  exception the SDK already defines MUST either be an intentional adoption, declared by the SDK, or
  fail generation. It MUST NOT silently produce two classes with one name.

  Rationale: the SDK already defines `ValidationError`, `RateLimitError`, `InvalidResponseError`,
  `FileNotValidError`, and `ResourceNotDefinedError`, every one of which is the name a plausible future
  code would derive. A collision that is not caught would shadow the hand-written class of that name,
  changing what an existing `except` clause catches — in this repository, from a change made in
  another one.
- **FR-007**: Payload model names MUST come from the catalogue's declared payload title, so SDK and
  frontend bindings agree on naming.
- **FR-008**: Parent classes MUST be derived from the code's declared HTTP status, with no
  hand-maintained per-code mapping. Every catalogued code descends from the GraphQL branch, because
  the catalogue is GraphQL-only and any code can reach the SDK inside a GraphQL response. Codes
  declaring 401 or 403 MUST *additionally* descend from the authentication branch.

  Rationale: the two are not alternatives. A permission failure raised inside a resolver comes back
  as an HTTP 200 GraphQL response carrying `PERMISSION_DENIED` in its `errors` array, which is a
  response `except GraphQLError` catches today. Making the authentication branch the sole parent
  would silently remove that coverage, violating FR-018.
- **FR-009**: The generated artefact MUST carry the same "generated, do not edit" marking as the
  repository's other generated files, and MUST record the catalogue version it was generated from.
- **FR-010**: The SDK MUST NOT contain a copy of the catalogue schema. The generated bindings are the
  only artefact that crosses the repository boundary.

#### Raising the specific error

- **FR-011**: Every operation that today raises the generic GraphQL error MUST raise the specific
  class when the response carries a recognised code.
- **FR-012**: Where no class matches the code — unrecognised, absent, or an integer from a
  pre-catalogue server — or where the matched class's payload does not validate, the operation MUST
  raise the generic class for **the transport it observed**: the GraphQL error for anything read from an
  `errors` array, and the authentication error only for a response the SDK saw as HTTP 401 or 403. The
  fallback MUST NOT be selected from the code's declared HTTP status.

  Rationale: for an unrecognised code the SDK holds no binding and so cannot know the declared status
  at all, and for a recognised one the declared status describes the failure rather than the transport.
  Routing by declared status would therefore send a recognised 401/403 code whose payload fails to
  validate, arriving inside an HTTP 200 body, to the authentication branch — where an existing
  `except GraphQLError` would stop catching it, the coverage loss FR-018 forbids. Note that the dual
  inheritance in FR-008 does not help here: it shapes the per-code classes, and the class the fallback
  raises is the generic one, which has a single parent. Only the transport rule preserves the coverage.

  Where a string code was on the wire it MUST remain readable as `exc.code` even though the generic
  class was raised; `exc.code` is `None` only when no string code was present.
- **FR-013**: Where a response carries several errors, the **first** error in the response determines
  the class raised. The exception MUST retain the complete list, and MUST NOT discard or reorder it.
  The first error governs even when it carries no code and a later one does, in which case the generic
  class for the branch is raised.

  Rationale: this makes the raised type a pure function of the response, independent of which version
  of the generated bindings the SDK holds. Selecting the first *recognised* code instead would make
  the type depend on binding freshness, so regenerating bindings could change which exception a
  consumer receives for a byte-identical response — the opposite of the guarantee in FR-010 and User
  Story 2.
- **FR-014**: Async and sync clients MUST behave identically, per the constitution's parity
  principle, and both paths MUST be tested.

#### Reconciling names that already exist

- **FR-015**: `AuthenticationError` MUST keep its name and constructor and MUST remain the class
  raised for REST authentication failures, while gaining the three catalogue subclasses beneath it.
- **FR-016**: `NodeNotFoundError` MUST be unified into a single class covering both the client-side
  and the server-reported cases, re-rooted so that an existing `except GraphQLError` clause catches
  it. The consequent broadening — that clause now also catches purely client-side lookup misses — is
  accepted.

  The unified class MUST satisfy all of the following observable contract. The mechanism that achieves
  it is left to the plan; the contract is not.

  - Every construction shape in use today MUST keep working unchanged. That includes the mapping of
    filters passed on the store and client lookup paths **and** the plain string the file handler
    already passes, which the current type annotation does not actually admit.
  - The server-reported node kind and identifier MUST be reachable as typed attributes when the error
    came from the server.
  - There MUST be one documented way to obtain the identifying detail that works regardless of which
    path raised the error, so a consumer never has to test which case it is holding.
  - Any attribute whose type widens as a result MUST be documented as such, and the widening MUST be
    called out in the change's release notes, since external consumers read these attributes even
    though nothing in this repository does.
- **FR-017**: `BranchNotFoundError` and `SchemaNotFoundError` MUST be reconciled the same way as
  `NodeNotFoundError`.
- **FR-018**: Every existing `except` clause and `isinstance` check in the SDK and CLI MUST still
  catch what it caught before the change, with ordered ladders corrected where re-rooting shadows a
  later branch.

#### Removing string matching

- **FR-019**: The silent token-refresh decision MUST be made from the catalogue code where one is
  present, retaining the existing message check only as the fallback for servers that predate the
  catalogue.
- **FR-020**: The SDK's remaining message-string checks for catalogued failures MUST be replaced with
  typed handling.
- **FR-021**: Checks that detect *uncatalogued* conditions — notably GraphQL schema-validation probing
  used for server feature detection — are explicitly out of scope and MUST be left in place.

#### Messages

- **FR-022**: A server-reported catalogued error's message MUST name the code and the server's message,
  and MUST NOT embed the query text. Where one of the unified classes is raised client-side, with no
  code and no server message to name, its message MUST remain exactly as it is today.
- **FR-023**: An uncatalogued error's message MUST remain exactly as it is today, query text included.
- **FR-024**: The query and variables MUST remain available as attributes on the exception in both
  cases.

#### Generation and validation (Infrahub repository)

- **FR-025**: Infrahub MUST generate the SDK's error bindings into the SDK submodule as part of its
  existing generation task, alongside the schema models and protocols it already generates there.
- **FR-026**: Infrahub's existing generated-artefact validation MUST be extended to fail when the
  submodule's bindings do not match a fresh generation, so a catalogue change that skips regeneration
  fails the pull request that made it.
- **FR-027**: No release-time gate is added on either side. Pull-request-time validation is the
  mechanism, matching the treatment the existing generated artefacts receive.

#### Documentation

- **FR-028**: SDK documentation MUST describe the exception hierarchy, how to catch by branch and by
  code, and the cross-version behaviour a consumer can rely on, updated in the same change as the
  behaviour. It MUST reference the server's published catalogue for the code list rather than
  restating it, so a code added upstream cannot leave the SDK's documentation quietly wrong. It MUST
  also note that a catalogued message now names the failing action and resource kind where the
  catalogue provides them, since that text reaches logs and CLI output.

### Key Entities

- **Catalogue code**: A stable string naming one failure mode, with a declared description, stability
  level, HTTP status, and payload schema. Owned by Infrahub; the SDK is a consumer.
- **Error envelope**: What the server puts on the wire for one error. Two shapes exist — the catalogue
  envelope on GraphQL, and the legacy integer-code envelope on REST.
- **Payload model**: The typed `data` for one code, tolerant of fields it does not recognise. Used to
  validate the envelope and populate the exception's attributes; not the way a consumer reads them.
- **Exception hierarchy**: Rooted at the SDK's `Error`; below it a base for server-reported errors,
  splitting into the authentication branch and the GraphQL branch, with one generated class per code.
- **Generated bindings module**: The single artefact crossing from Infrahub into the SDK, holding the
  payload models, the per-code classes with their promoted attributes, and the code-to-class
  resolution used at raise time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every code in the catalogue is reachable as its own exception type, with the catalogue's
  payload fields readable as typed attributes on it; a developer can handle any catalogued failure
  without reading a message.
- **SC-002**: No message-string matching remains in the SDK for any failure the catalogue covers.
- **SC-003**: The existing test suite passes with no `except` clause losing coverage it had before;
  every deliberate behaviour change is pinned by a test that asserts the new behaviour.
- **SC-004**: Every cross-version case — unknown code, unknown payload field, absent envelope,
  pre-catalogue integer code — is covered by a test and none of them raises during parsing.
- **SC-005**: A catalogue change that omits regeneration fails validation in the pull request that
  introduced it, and a regenerated artefact is byte-identical to a fresh generation.
- **SC-006**: Async and sync clients raise the same type with the same attributes for the same
  failure, across all catalogued codes.
- **SC-007**: A catalogued failure's message contains no query text, while an uncatalogued failure's
  message is byte-identical to today's.
- **SC-008**: A developer can catch every server-reported error, on either transport, with one
  `except` clause.

## Assumptions

- **The catalogue is GraphQL-only.** Confirmed against the server: REST responses keep the legacy
  integer-code envelope. If REST later adopts the catalogue, the base class introduced here is where
  it would attach, but no REST parsing is in scope.
- **Class and code names are the product, not implementation detail.** For an SDK the exception
  hierarchy *is* the user-facing contract, so this spec names classes and codes. It deliberately does
  not specify module layout, file names, generator implementation, or test framework mechanics.
- **Generation belongs to Infrahub.** The SDK cannot regenerate its own protocols or schema models
  today either; those come from Infrahub's generation task writing into the submodule. Error bindings
  follow that established pattern rather than introducing a second mechanism, which also removes any
  need to keep a vendored catalogue copy in sync.
- **`infrahub_sdk.exceptions` is the supported import path, and it is treated as public.** A consumer
  should never need to know which module inside it defines a given exception: every exception the SDK
  raises — hand-written or generated — is importable from `infrahub_sdk.exceptions`, and no name
  importable from it today may stop being importable from it. Modules beneath it are internal and are
  not an import path for consumers. This is a stronger promise than the constitution's tiering
  strictly requires, and it is made deliberately, because `infrahubctl`, the Ansible collection, and
  external consumers already import from it directly.
- **Three broadenings are accepted deliberately**: `except GraphQLError` will additionally catch node,
  branch, and schema lookup misses that never involved a GraphQL request at all — both the client-side
  ones and the REST 404 the file handler turns into a `NodeNotFoundError`; it will also catch a real
  401 or 403 whenever the SDK raises a per-code class for it, since only those classes carry both
  parents — that is, when the code is recognised and its payload validates, with anything else falling
  back to `AuthenticationError` exactly as today; and code that catches the generic error to inspect its
  message will now sometimes receive a subclass with a different message. All three follow from
  answered decisions rather than oversight.
- **The repository-import failure handling in the git integrator (GitHub #7498) is out of scope**, as
  is any change to what the server emits.
- **Both repositories are in scope for this document.** Requirements FR-025 to FR-027 land in the
  Infrahub repository and must be executed from that checkout; everything else lands here.
