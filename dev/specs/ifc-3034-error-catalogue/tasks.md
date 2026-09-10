# Tasks: Error Catalogue in the Python SDK

**Input**: Design documents from `dev/specs/ifc-3034-error-catalogue/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Included. Constitution Principle V requires tests to ship in the same change, and
[research.md](./research.md) R12 fixes the layer split they follow.

**Organization**: Tasks are grouped by user story. Phase numbering is a nominal sequence, not a strict
dependency order - see the note below for the two adjacencies that are actually forced.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US6)
- Every task names the exact file it touches

## Path conventions

Two checkouts are involved:

- **SDK** (this repository): paths are relative to the repository root, e.g. `infrahub_sdk/exceptions/base.py`.
- **Infrahub** (`opsmill/infrahub`, phase 7 only): paths are prefixed `[infrahub]`, e.g.
  `[infrahub] tasks/backend.py`.

## Phase order is a nominal sequence, not a strict dependency order

Phases are numbered so there is one obvious path through the work. Only two adjacencies are actually
forced, and both cut against the priority labels ([research.md](./research.md) R16 and R4):

1. **US3 must precede US5.** The three `CODE` declarations (T034) are a prerequisite for generation
   succeeding at all, not merely for its output: the generator aborts on an undeclared name collision.
2. **US5 must precede US1.** The generator produces the per-code classes US1 delivers, so the P1 MVP
   story lands last among the behaviour phases. Priority labels describe value, not order.

Everything else is free. **US2, US3, US4, and US6 depend only on Foundational and are mutually
independent**, so do not serialize them just because they are numbered in sequence. The envelope parses
onto the base classes with **no generated bindings at all**, which is what makes US2 and US4 landable
before anything has been generated. See Parallel opportunities below for the file overlaps to watch if
they are worked concurrently.

Nominal sequence: Setup → Foundational → US2 → US3 → US4 → US6 → US5 → US1 → Polish.
US1 remains the feature's reason for existing; it is simply the last brick, not the first.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Restructure `exceptions.py` into a package without changing a single observable behaviour,
and pin that invisibility before touching anything.

- [X] T001 Capture the current public surface as a committed snapshot: write every name importable from
      `infrahub_sdk.exceptions` today into `tests/fixtures/error_catalogue/public_names.json`, and add
      `tests/unit/sdk/test_exceptions_public_names.py` asserting every snapshot name is still importable.
      Author this **before** the restructure so the snapshot records the pre-change surface.
      **The committed snapshot is post-change: it includes `ApiError`.** It still pins that every name
      importable before the split is importable now, which is the property that matters, but it is not
      the untouched pre-change baseline this task asked for.
- [X] T002 [P] Create the response-envelope fixture directory `tests/fixtures/error_catalogue/` with a
      `README.md` stating that each file is a verbatim server response envelope, not a hand-shaped dict.
      **The README distinguishes two kinds instead.** The claim cannot hold for the `malformed_*`
      fixtures, since a correct server does not produce them; they are constructed and the README says
      so. The captured/not-parser-shaped rule stands for every fixture representing a real response.
- [X] T003 Convert `infrahub_sdk/exceptions.py` into `infrahub_sdk/exceptions/base.py` by verbatim move
      (no behaviour edits in this task), and add `__all__` to it listing every class it defines.
- [X] T004 Create the façade `infrahub_sdk/exceptions/__init__.py` re-exporting with `from .base import *`
      and nothing else yet.
- [X] T005 [P] Add `"exceptions"` to `packages_to_ignore` in `tasks.py::get_modules_to_document`, so
      `docs-generate` does not fail with `Uncategorized packages under infrahub_sdk/` and `sdk_ref`
      output stays byte-identical.
- [X] T006 [P] Add the `per-file-ignores` entry for `infrahub_sdk/exceptions/__init__.py` in
      `pyproject.toml` silencing `F403`/`F405`, with a comment giving the reason, mirroring the existing
      `infrahub_sdk/schema/generated/*.py` entry.
- [X] T007 Run `uv run pytest tests/unit/ -q` and `uv run invoke format lint-code docs-generate docs-validate`
      to confirm the restructure is invisible from outside the package.

**Checkpoint**: `infrahub_sdk.exceptions` is a package; nothing else has changed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The parsed envelope on the base classes, and the two raise-time factories every existing
raise site funnels through. Every user story below depends on this phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T008 Add `ApiError(Error)` to `infrahub_sdk/exceptions/base.py` with class-level defaults for
      `code` (`str | None`), `http_status` (`int | None`), `extensions` (`dict[str, Any] | None`),
      `errors` (immutable empty tuple), `query`, and `variables`, adding no required constructor
      arguments. The defaults are a can't-crash floor, not a substitute for constructor state.
      **Landed without `query` and `variables` on the base.** Only `GraphQLError` ever sets them, so on
      `ApiError` they would be permanently `None` on every `AuthenticationError`, telling a caller that a
      REST failure had no query rather than that it can never have one. They live on `GraphQLError`.
- [X] T009 Re-root `GraphQLError` under `ApiError` in `infrahub_sdk/exceptions/base.py` and give its
      constructor an optional `message` parameter. When `message` is omitted the string it builds MUST be
      byte-identical to today's. **Re-rooting landed; the `message` parameter is deferred to its first
      caller.** Nothing in this issue passes it, and an unused public parameter is surface the SDK would
      have to keep. T035 adds it as part of the same edit that first calls it. The byte-identical default
      message is unaffected and is pinned by `test_malformed_envelope_keeps_the_payload_in_the_message`.
- [X] T010 Re-root `AuthenticationError` under `ApiError` in `infrahub_sdk/exceptions/base.py`, leaving
      its name, constructor signature, and default message untouched.
- [X] T011 Create `infrahub_sdk/exceptions/factory.py` with `graphql_error_from_response(errors, query,
      variables)`: read `extensions.code` from the **first** error only when it is a `str`, read
      `extensions.http_status`, retain the complete unreordered error list, and construct with keyword
      arguments only.
- [X] T012 Add `authentication_error_from_response(response)` to `infrahub_sdk/exceptions/factory.py`,
      subsuming the eleven-site "decode, collect messages, join with ` | `" shape and preserving that
      message byte-for-byte. It MUST use `decode_json` and fall back to the plain status when the body is
      not JSON, since two of the sites it replaces call `response.json()` directly.
- [X] T013 Make both factories total in `infrahub_sdk/exceptions/factory.py`: wrap resolution so any
      unexpected error degrades to constructing today's generic exception rather than replacing the
      server's failure with an SDK `TypeError`, and log every fallback at debug level with the code
      involved.
- [X] T014 Extend the façade `infrahub_sdk/exceptions/__init__.py` to import the factory module, keeping
      imports pointing strictly downward.
- [X] T015 Add `tests/unit/sdk/test_exceptions_layering.py`, parsing every module in
      `infrahub_sdk/exceptions/` with `ast` and failing on any intra-package import that points at its own
      layer or higher. It MUST walk imports inside function bodies and `TYPE_CHECKING` blocks, not only
      module-level ones.
- [X] T016 Replace the four `GraphQLError` raise sites in `infrahub_sdk/client.py` (`_execute_graphql`
      and the file-upload variants, async and sync) with `graphql_error_from_response`.
- [X] T017 Replace the four `AuthenticationError` raise sites in `infrahub_sdk/client.py` with
      `authentication_error_from_response`.
- [X] T018 [P] Replace the six `AuthenticationError` raise sites in `infrahub_sdk/object_store.py` with
      `authentication_error_from_response`.
- [X] T019 [P] Replace the `AuthenticationError` raise site at `infrahub_sdk/file_handler.py:164` with
      `authentication_error_from_response`.
- [X] T020 [P] Correct the pre-existing constructor misuse at `infrahub_sdk/analyzer.py:42`, which passes
      the bare string `"Schema is not provided"` where a list of error dicts is expected.
      **No change needed - the premise does not hold.** `analyzer.py` imports `GraphQLError` from
      `graphql` (graphql-core), whose constructor takes a message string, so the call is correct.
- [X] T021 [P] Correct the pre-existing constructor misuse at
      `infrahub_sdk/testing/schemas/animal.py:154`, which passes a list whose single element is not a dict.
      **No change needed - the premise does not hold.** `SchemaLoadResponse.errors` is annotated
      `dict` and pydantic rejects a list, so `[resp.errors]` is already a `list[dict]`.
- [X] T022 Add `tests/unit/sdk/test_error_catalogue.py` covering the generic factory path with no bindings
      present: `code` and `http_status` readable off a `GraphQLError` and an `AuthenticationError`, the
      complete error list retained unreordered, and `exc.errors` asserted to be a sequence of dicts on
      both paths.

**Checkpoint**: The envelope is readable against any server version with no generated bindings at all.

---

## Phase 3: User Story 2 - Keep working against any server version (Priority: P1)

**Goal**: Parsing never raises, on any server version, for any envelope shape.

**Independent Test**: Replay fixtures representing a newer server, an older server, and a pre-catalogue
server through the factory and assert no parse failure and the correct fallback in each case
(quickstart scenario 2).

### Tests for User Story 2

- [X] T023 [P] [US2] Add cross-version envelope fixtures under `tests/fixtures/error_catalogue/`: an
      unknown string code, a known code carrying an extra payload field, an error with no `extensions`, a
      pre-catalogue integer `extensions.code` on `/graphql`, and a payload that violates its own declared
      schema.
- [X] T024 [P] [US2] Add malformed-envelope fixtures under `tests/fixtures/error_catalogue/`: `errors` as
      a bare string, `extensions` as a list, and `code` as a nested object.
- [X] T025 [US2] Add the `crossversion`-marked cases to `tests/unit/sdk/test_error_catalogue.py`: each
      fixture from T023 raises the generic class for its transport, none raises during parsing, and
      `exc.code` reads the wire string for the unknown code and `None` for the absent-envelope and
      integer-code cases.
- [X] T026 [US2] Add the `malformed`-marked totality cases to `tests/unit/sdk/test_error_catalogue.py`,
      asserting each fixture from T024 degrades to today's generic exception rather than an SDK `TypeError`.

### Implementation for User Story 2

- [X] T027 [US2] Confirm in `infrahub_sdk/exceptions/factory.py` that an integer `extensions.code` never
      reaches `exc.code`, and that `exc.code` is set from the wire whenever a string code was present,
      including when no class matched it. Which class is raised and what `code` reports are separate
      questions.
- [X] T028 [US2] Add the debug-level fallback log assertions to `tests/unit/sdk/test_error_catalogue.py`,
      using `caplog`, so a cross-version fallback is diagnosable in the field rather than only in tests.

**Checkpoint**: Every cross-version case is covered and none of them raises during parsing.

---

## Phase 4: User Story 3 - Catch server-reported errors uniformly across transports (Priority: P2)

**Goal**: The hierarchy is a tree under `ApiError`, the three unified classes are re-rooted with their
envelope state actually set, and no `except` clause or `isinstance` ladder loses coverage.

**Prerequisite for phase 7**: the `CODE` declarations added here are what stop the generator aborting.

**Independent Test**: Assert the class hierarchy directly and assert each existing `except` clause in
the SDK and CLI still catches what it caught before (quickstart scenario 3).

### Tests for User Story 3

- [ ] T029 [P] [US3] Add hierarchy tests to `tests/unit/sdk/test_exceptions.py`: no class in
      `infrahub_sdk.exceptions` has more than one parent; `GraphQLError` and `AuthenticationError` are
      siblings under `ApiError`; `NodeInvalidError` is an instance of `GraphQLError`.
- [ ] T030 [P] [US3] Add transport tests to `tests/unit/sdk/test_exceptions.py`: a real 401 carrying
      `TOKEN_EXPIRED` is caught by `except AuthenticationError` with `exc.code == "TOKEN_EXPIRED"`, and a
      `PERMISSION_DENIED` inside an HTTP 200 body is caught by `except GraphQLError` with
      `exc.code == "PERMISSION_DENIED"`. Add the matching envelope fixtures under
      `tests/fixtures/error_catalogue/`.
- [ ] T031 [P] [US3] Add the attribute-access test to `tests/unit/sdk/test_exceptions.py`: reading
      `exc.errors`, `exc.query`, and `exc.variables` off a purely client-side `NodeNotFoundError` returns
      empty/`None` rather than raising `AttributeError`, and `exc.errors` is a `list`, not the base's tuple.
- [ ] T032 [P] [US3] Add the broadening test to `tests/unit/sdk/test_exceptions.py`: `except GraphQLError`
      catches a client-side `NodeNotFoundError`, asserting the accepted behaviour change rather than
      working around it.
- [ ] T033 [P] [US3] Add ladder tests to `tests/unit/ctl/test_utils.py` driving `handle_exception` with
      `NodeNotFoundError`, `SchemaNotFoundError`, a catalogued `GraphQLError`, and a catalogued
      `AuthenticationError`, asserting rendered output rather than reading the source.

### Implementation for User Story 3

- [ ] T034 [US3] Declare `CODE = "NODE_NOT_FOUND"` on `NodeNotFoundError`, `CODE = "BRANCH_NOT_FOUND"` on
      `BranchNotFoundError`, and `CODE = "SCHEMA_NOT_FOUND"` on `SchemaNotFoundError` in
      `infrahub_sdk/exceptions/base.py`.
- [ ] T035 [US3] Re-root the three classes under `GraphQLError` in `infrahub_sdk/exceptions/base.py`, each
      calling `super().__init__(errors=[], query=None, variables=None, message=...)` explicitly so their
      envelope attributes are set by the constructor that owns them. This is the first caller of
      `GraphQLError`'s optional `message` parameter, which T009 deferred, so add the parameter here.
- [ ] T036 [US3] Widen `NodeNotFoundError.identifier` to `Mapping[str, list[str]] | str` in
      `infrahub_sdk/exceptions/base.py`, admitting the plain string `infrahub_sdk/file_handler.py:168`
      already passes.
- [ ] T037 [US3] Add a hand-written `from_payload` classmethod to each of the three classes in
      `infrahub_sdk/exceptions/base.py`, mapping `node_kind`→`node_type` and `identifier`→`identifier`,
      `branch_name`→`identifier`, and `kind`→`identifier`. Every promoted attribute on these three stays
      **optional**, since neither provenance can populate the full set.
- [ ] T038 [US3] Add the catalogued branch to `handle_exception` in `infrahub_sdk/ctl/utils.py`, placed
      **above** the class ladder and keyed on `exc.code is not None`, rendering the code and the server's
      message. An error with no code falls through to today's ladder unchanged.
- [ ] T039 [US3] Move the `(SchemaNotFoundError, NodeNotFoundError, ResourceNotDefinedError,
      GraphQLQueryError)` branch **above** the `GraphQLError` branch in
      `infrahub_sdk/ctl/utils.py::handle_exception`, which re-rooting would otherwise make unreachable.
- [ ] T040 [US3] Fix `print_graphql_errors` in `infrahub_sdk/ctl/utils.py`: degrade to the exception's
      message when there are no server errors to render. The `isinstance(errors, list)` guard this task
      also meant to fix is already gone: issue 1 made `exc.errors` a list of dicts by construction, so the
      guard became unreachable and was removed with the annotation widened to `Sequence[dict[str, Any]]`.
      The remaining gap is the empty-list case, where the renderer currently prints nothing at all.
- [ ] T041 [US3] Verify no other ordered `isinstance` ladder is shadowed by the re-rooting: check
      `infrahub_sdk/ctl/cli_commands.py:237` and `infrahub_sdk/ctl/validate.py:88`, and grep the SDK and
      CLI for further sequential tests of these classes.
- [ ] T042 [US3] Update `tests/unit/sdk/test_exceptions_public_names.py` so the snapshot check runs against
      the re-rooted hierarchy, confirming the restructure is still invisible from outside the package.

**Checkpoint**: The hierarchy is a tree, every existing clause still catches what it caught, and the
generator's adoption prerequisite is satisfied.

---

## Phase 5: User Story 4 - Stop the SDK string-matching its own server (Priority: P2)

**Goal**: The silent token-refresh decision is typed, with the legacy string check surviving only as the
pre-catalogue fallback and appearing exactly once in the SDK.

**Independent Test**: Drive the relogin path with a `TOKEN_EXPIRED` envelope, with the legacy
`"Expired Signature"` message, and with an unrelated 401 (quickstart scenario 5).

### Tests for User Story 4

- [X] T043 [P] [US4] Extend `tests/unit/sdk/test_relogin_headers.py` with three cases: a 401 carrying
      `TOKEN_EXPIRED` refreshes and retries, a 401 carrying the legacy `"Expired Signature"` message
      refreshes and retries, and an unrelated 401 does not.
- [X] T044 [P] [US4] Add a case to `tests/unit/sdk/test_relogin_headers.py` driving a 401 with a non-JSON
      body (an HTML proxy error page) and an empty body, asserting neither raises a decode error.

### Implementation for User Story 4

- [X] T045 [US4] Add the shared refresh-decision helper to `infrahub_sdk/client.py`, reading
      `errors[0].extensions.code == "TOKEN_EXPIRED"` and falling back to the existing
      `"Expired Signature" in messages` check when no code is present. It MUST tolerate a non-JSON or empty
      body rather than letting `response.json()` raise, since the wrapper sees REST responses too.
      **Landed scanning every error, not `errors[0]`.** A stale token is a fact about the request, not
      about which error happens to lead; reading only the first would refuse to refresh when the server
      orders the codes differently. Tolerance also covers a body that decodes to valid JSON that is not an
      object, which `response.json().get(...)` raised an `AttributeError` on.
- [X] T046 [US4] Route both `handle_relogin` and `handle_relogin_sync` in `infrahub_sdk/client.py` through
      that helper, so the literal `"Expired Signature"` appears exactly once in the SDK, down from twice.
- [X] T047 [US4] Confirm `grep -rn "Expired Signature" infrahub_sdk/` returns exactly one site, and that
      the GraphQL schema-validation probing used for server feature detection is untouched - it detects an
      uncatalogued condition and is deliberately out of scope.

**Checkpoint**: The refresh decision is typed and a pre-catalogue server still refreshes.

---

## Phase 6: User Story 6 - Messages that are about the failure (Priority: P3)

**Goal**: A server-reported catalogued failure's message names the code and the server's message and
carries no query text; an uncatalogued failure's message is byte-identical to today's.

**Independent Test**: Trigger a catalogued failure and an uncatalogued one and compare their messages
(quickstart scenario 6).

### Tests for User Story 6

- [ ] T048 [P] [US6] Add `message`-marked cases to `tests/unit/sdk/test_exceptions.py`: a server-reported
      catalogued failure's message names the code and the server's message and contains no query text; an
      uncatalogued failure's message is byte-identical to today's string; and a unified class raised with
      no catalogue code behind it keeps today's message exactly.
- [ ] T049 [P] [US6] Add a case to `tests/unit/sdk/test_exceptions.py` asserting `exc.query` and
      `exc.variables` remain populated on a catalogued failure.

### Implementation for User Story 6

- [ ] T050 [US6] Have the factories in `infrahub_sdk/exceptions/factory.py` pass a message naming the code
      and the server's message for a catalogued failure, and pass nothing for an uncatalogued one so
      `GraphQLError` reproduces today's string.
- [ ] T051 [US6] Re-check the message assertion at `tests/unit/sdk/test_graph_traversal.py:383`
      (`match="Source node not found"`) deliberately: that path stays uncatalogued, so confirm the
      assertion still holds rather than assuming it.

**Checkpoint**: Message behaviour is pinned in both directions.

---

## Phase 7: User Story 5 - Bindings that cannot silently drift (Priority: P2)

**Goal**: Infrahub generates `infrahub_sdk/exceptions/catalogue.py` into the SDK submodule as part of its
existing generation task, and its existing validation fails when the committed artefact is stale.

**Runs from the Infrahub checkout.** Depends on phase 4 (T034): the generator aborts on an undeclared name
collision, so the three `CODE` declarations must already be in the SDK.

**Independent Test**: Change the catalogue without regenerating and confirm validation fails; regenerate
and confirm it passes (quickstart scenario 7).

### Implementation for User Story 5

- [ ] T052 [US5] Create `[infrahub] backend/templates/generate_sdk_errors.j2` emitting, in sorted code
      order: a header marking the file generated and not to be edited, naming
      `schema/error-catalogue.json`, recording `infrahub_catalogue_version`, and giving the regeneration
      command; one pydantic payload model per code; one exception class per non-adopted, non-401/403 code;
      `CODE_TO_EXCEPTION`; and `__all__`.
- [ ] T053 [US5] Implement name derivation in the template's helper in `[infrahub] tasks/backend.py`: the
      code's parts capitalised and joined with `Error` appended only when the result does not already end
      in `Error`, and the payload model name taken from `data_schema.title` verbatim.
- [ ] T054 [US5] Implement the JSON-Schema-to-Python type mapping in `[infrahub] tasks/backend.py` covering
      `string`, `integer`, `number`, `boolean`, `string`+`format: date-time`, `array`, and
      `anyOf: [T, null]`. Anything outside that vocabulary MUST abort with the offending fragment in the
      message.
- [ ] T055 [US5] Implement the adoption walk in `[infrahub] tasks/backend.py`: parse
      `python_sdk/infrahub_sdk/exceptions/base.py` with `ast`, collect every class whose **own body**
      assigns a `CODE` string, and emit an import plus a `CODE_TO_EXCEPTION` entry for those codes instead
      of a class definition. The payload model is still emitted. Parsing rather than importing is what
      keeps `NodeInvalidError`'s inherited `CODE` invisible.
- [ ] T056 [US5] Implement the collision check in `[infrahub] tasks/backend.py` from the same walk: abort
      when a derived name matches a class defined in `base.py` that has not declared that code. Exercise it
      against `ValidationError`, `RateLimitError`, `InvalidResponseError`, `FileNotValidError`,
      `ResourceNotDefinedError`, and `TimestampFormatError`, every one of which a plausible future code
      would derive.
- [ ] T057 [US5] Add the remaining abort conditions to `[infrahub] tasks/backend.py`: no integer
      `http_status`, no non-empty `data_schema.title`, empty `codes`, or a non-object root.
- [ ] T058 [US5] Emit no class for a code declaring 401 or 403, and root every other class at
      `GraphQLError` with exactly one parent, in `[infrahub] backend/templates/generate_sdk_errors.j2`.
- [ ] T059 [US5] Emit each generated class's promoted attributes typed exactly as the catalogue declares
      them (required fields non-optional, nullable fields carrying their declared default), assigned in
      `__init__`, plus a `from_payload` classmethod and a docstring carrying the catalogue's `description`
      and `stability`, in `[infrahub] backend/templates/generate_sdk_errors.j2`.
- [ ] T060 [US5] Add `_generate_sdk_error_bindings` to `[infrahub] tasks/backend.py` (render, then
      `ruff format`, as the sibling generators do) and call it from the existing `generate` task. Correct
      `generate`'s docstring, which has said "internal backend models" since it started generating SDK
      protocols.
- [ ] T061 [US5] Extend `validate_generated` in `[infrahub] tasks/backend.py` with
      `git -C python_sdk diff --exit-code infrahub_sdk/exceptions/catalogue.py`, with a failure hint naming
      `uv run invoke backend.generate`. The diff MUST run inside the submodule; from the superproject
      `git diff` sees only the gitlink.
- [ ] T062 [US5] Add `error_catalogue == 'true'` to the `backend-validate-generated` job trigger in
      `[infrahub] .github/workflows/ci.yml`, so a hand-edit of the catalogue JSON alone cannot slip past.
      This is the only CI edit; no new path filter can match a file inside a submodule.
- [ ] T063 [US5] Run `uv run invoke backend.generate` from the Infrahub checkout and hand-verify the
      resulting `infrahub_sdk/exceptions/catalogue.py` in the SDK: nine generated classes, three adopted
      imports, fifteen payload models, and no class for the three 401/403 codes.
- [ ] T064 [US5] Commit the generated `infrahub_sdk/exceptions/catalogue.py` in the SDK repository and
      extend the façade `infrahub_sdk/exceptions/__init__.py` with `from .catalogue import *`.
- [ ] T065 [US5] Prove the negative from the Infrahub checkout: add a code to the backend catalogue, run
      `uv run invoke backend.export-error-catalogue` alone, confirm `backend.validate-generated` exits
      non-zero naming the stale artefact, then revert.

**Checkpoint**: A catalogue change that skips regeneration fails the pull request that made it.

---

## Phase 8: User Story 1 - Branch on a specific server failure (Priority: P1) 🎯 MVP

**Goal**: Every catalogued failure raises its own class carrying the payload's fields as directly typed
attributes.

**Independent Test**: Drive each catalogued failure through a fixture of its response envelope and assert
the raised type and the typed attributes, reading no message (quickstart scenarios 1, 4, 6b).

### Tests for User Story 1

- [ ] T066 [P] [US1] Add one response-envelope fixture per catalogue code under
      `tests/fixtures/error_catalogue/`, each a verbatim server response rather than a hand-shaped dict.
- [ ] T067 [US1] Add the exhaustive factory cases to `tests/unit/sdk/test_error_catalogue.py`: one per
      code, asserting the raised class, every promoted attribute's concrete value, and that `exc.code` and
      `exc.http_status` match the catalogue entry. No case reads a payload object, because there is none.
- [ ] T068 [P] [US1] Add the adopted-class cases to `tests/unit/sdk/test_error_catalogue.py`: a
      server-reported `NODE_NOT_FOUND` populates `node_type` and `identifier`, `BRANCH_NOT_FOUND` and
      `SCHEMA_NOT_FOUND` populate `identifier`, and `exc.code is not None` distinguishes a server-reported
      raise from a client-side one.
- [ ] T069 [P] [US1] Add the representative parity set to `tests/unit/sdk/test_client.py`, parametrized
      over `["standard", "sync"]` via the `BothClients` fixture, covering both branches, both transports,
      and the file-upload variant, asserting the same class and the same attributes on each.
- [ ] T070 [P] [US1] Add a `catalogue`-marked case to `tests/integration/test_infrahub_client.py`: saving a
      node that collides on a unique attribute raises `UniquenessViolationError` with the node kind and
      colliding fields from the real payload, and deleting a missing node raises `NodeNotFoundError` with
      its kind and identifier.
- [ ] T071 [P] [US1] Add the same two `catalogue`-marked cases to
      `tests/integration/test_infrahub_client_sync.py`.

### Implementation for User Story 1

- [ ] T072 [US1] Extend `graphql_error_from_response` in `infrahub_sdk/exceptions/factory.py` to look the
      first error's code up in `CODE_TO_EXCEPTION`, validate `extensions.data` with the class's
      `DATA_MODEL`, and raise via `cls.from_payload(...)`. The factory never assembles attributes itself.
- [ ] T073 [US1] Implement the validation-failure fallback in `infrahub_sdk/exceptions/factory.py`: an
      invalid payload falls back to the generic class for the observed transport with `exc.code` still
      readable, the raw `extensions` retained, and a debug log. A pydantic `ValidationError` never escapes
      a raise path.
- [ ] T074 [US1] Confirm in `infrahub_sdk/exceptions/factory.py` that the fallback follows **the transport
      the SDK observed** and never the code's declared status: the GraphQL branch for anything read from
      an `errors` array, the authentication branch only for a response the SDK saw as HTTP 401 or 403.
      This is the only rule under which the three authentication codes reach the right class at all.
- [ ] T075 [US1] Add a test to `tests/unit/sdk/test_error_catalogue.py` asserting the first error governs
      even when it carries no code and a later one does, and that the complete list is retained unreordered.

**Checkpoint**: Every catalogue code is identifiable without reading a message, on both clients.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T076 [P] Write `docs/docs/python-sdk/topics/error_handling.mdx` covering the hierarchy, catching by
      branch versus by code, the cross-version guarantees, the two accepted broadenings, and the note that
      `infrahub_sdk.exceptions` is the supported import path. Link to Infrahub's published catalogue for
      the code list rather than restating it, and note that a catalogued message now names the failing
      action and resource kind where the catalogue provides them.
- [ ] T077 [P] Add a towncrier fragment for the typed errors in `changelog/`.
- [ ] T078 [P] Add a towncrier fragment for the `NodeNotFoundError.identifier` widening in `changelog/`.
- [ ] T079 [P] Add a towncrier fragment for the `except GraphQLError` broadening in `changelog/`.
- [ ] T080 Run `uv run invoke format lint-code` and confirm both `mypy` and `ty` pass with **zero**
      suppressions. A needed `# type: ignore` is a signal the shape is wrong, not a licence to add one.
- [ ] T081 Run `uv run invoke docs-generate && uv run invoke docs-validate` and confirm `sdk_ref` output is
      unchanged, then `uv run invoke lint-docs`.
- [ ] T082 Run the full quickstart: every scenario in [quickstart.md](./quickstart.md), including the
      testcontainers scenario 6b and the Infrahub-side scenario 7.
- [ ] T083 Confirm the landing order with whoever owns the release flow before the paired pull requests go
      up: the SDK change merges first, then Infrahub bumps its submodule pointer to it. This is inferred
      from the repositories' history rather than from a written practice.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup. **Blocks every user story.**
- **US2 (Phase 3)**: depends on Foundational only. Needs no generated bindings.
- **US3 (Phase 4)**: depends on Foundational. **Blocks US5** - T034's `CODE` declarations are what stop
  the generator aborting.
- **US4 (Phase 5)**: depends on Foundational only. Independent of US3 and US5.
- **US6 (Phase 6)**: depends on `GraphQLError`'s optional `message` parameter, which T009 deferred to its
  first caller. Whichever of T035 and US6 lands first adds it. Independent of US5.
- **US5 (Phase 7)**: depends on US3 (T034). Runs from the Infrahub checkout.
- **US1 (Phase 8)**: depends on US5 (T064 lands `catalogue.py`) and on US3 (T037's adopted `from_payload`).
- **Polish (Phase 9)**: depends on all of the above.

### Parallel opportunities

- **Phase 1**: T002, T005, T006 are independent files.
- **Phase 2**: T018, T019, T020, T021 touch four different modules and can run together once T011-T013 exist.
- **Phases 3, 4, 5, and 6 are mutually independent** once Foundational is done: US2, US3, US4, and US6
  each depend on Phase 2 alone. Two file overlaps to coordinate if they are genuinely worked in
  parallel: US2 and US6 both edit `infrahub_sdk/exceptions/factory.py`, and US3 and US6 both add cases
  to `tests/unit/sdk/test_exceptions.py`. US4 touches neither.
- **Phase 4**: T029-T033 are five independent test additions.
- **Phase 8**: T066, T068, T069, T070, T071 are independent; T070 and T071 are the two integration files.
- **Phase 9**: T076-T079 are four independent files.

### Within each story

- Fixtures before the tests that load them.
- Tests before the implementation that satisfies them.
- Base classes before the factory; the factory before the raise sites.
- Deliberate behaviour changes are pinned by a test asserting the **new** behaviour, never worked around.

---

## Parallel Example: User Story 3

```bash
# Five independent test additions, one file each:
Task: "Hierarchy tests in tests/unit/sdk/test_exceptions.py"
Task: "Transport tests in tests/unit/sdk/test_exceptions.py"
Task: "Attribute-access test in tests/unit/sdk/test_exceptions.py"
Task: "Broadening test in tests/unit/sdk/test_exceptions.py"
Task: "Ladder tests in tests/unit/ctl/test_utils.py"
```

## Parallel Example: Phase 2 raise-site wiring

```bash
Task: "Replace the six AuthenticationError raise sites in infrahub_sdk/object_store.py"
Task: "Replace the AuthenticationError raise site in infrahub_sdk/file_handler.py"
Task: "Correct the constructor misuse in infrahub_sdk/analyzer.py"
Task: "Correct the constructor misuse in infrahub_sdk/testing/schemas/animal.py"
```

---

## Pull requests and issues

Task count is not pull-request count. The 83 tasks above are implementation granularity; the boundaries
below are set by three things, none of which is task count:

1. **The repository split.** The generator lives in `opsmill/infrahub`, so it is a separate pull request
   whatever else happens.
2. **The landing order** ([research.md](./research.md) R17): the SDK merges first, then Infrahub bumps its
   submodule pointer. Infrahub's `validate_generated` diffs submodule *content*, so `catalogue.py` must
   already exist at the pointer Infrahub carries.
3. **Where the review risk actually is.** The compatibility-sensitive work (re-rooting three classes,
   reordering the CLI ladder, two deliberate broadenings) is the only place FR-018 can be violated. It
   gets its own pull request so a reviewer reads it on its own.

### Four issues, four pull requests

| # | Issue | Repo | Tasks | Scope |
|---|-------|------|-------|-------|
| 1 | Parse the catalogue envelope onto the base classes | SDK | T001-T028, T043-T047 | The exceptions package, `ApiError`, the two factories, every raise site rewired, cross-version tolerance, and the typed refresh decision. No generated bindings, no re-rooting, no class anyone catches changes shape. |
| 2 | Unify and re-root the not-found classes | SDK | T029-T042, T048-T051, T078-T079 | The `CODE` declarations, the re-rooting, the CLI ladder and renderer, the message change, and the two changelog fragments documenting the `identifier` widening and the `except GraphQLError` broadening. |
| 3 | Typed per-code exceptions | SDK | T063-T064, T066-T077 | The generated `catalogue.py`, per-code resolution and its validation-failure fallback, both-client parity, the integration tests, the topic page, and the typed-errors changelog fragment. |
| 4 | Generate the SDK's error bindings | **Infrahub** | T052-T062, T065 | The template, the renderer, the adoption walk and collision check, `validate_generated`, the CI trigger, and the submodule pointer bump. |

T080-T082 (format, lint, type-check, docs-validate, quickstart) run on **every** pull request for the
scenarios that request covers; quickstart scenario 7 runs only on issue 4. T083 (confirm the landing order
with whoever owns the release flow) belongs to issue 1's timeframe, before issues 3 and 4 go up.

Two pull requests would also work (one SDK, one Infrahub), since the tasks are ordered so a single branch
carries them. It is not recommended: issue 2 is where "every existing `except` clause still catches what it
caught" has to be verified, and it is only fourteen tasks across three files.

### Issue dependencies to record

- **Issue 2 blocks issue 4.** The three `CODE` declarations (T034) are what stop the generator aborting on
  an undeclared name collision. Generation fails outright without them; this is not a preference about
  ordering.
- **Issue 3 depends on issues 2 and 4.**
- Not a dependency, but worth scheduling around: issues 1 and 2 both touch
  `infrahub_sdk/exceptions/base.py`, so running them in sequence avoids a conflict rather than
  satisfying a constraint.

### Issue 4 is developed before issue 3 but merges after it

`catalogue.py` in issue 3 is produced by running the generator from issue 4's unmerged branch (T063). So
issue 4 sits in progress while issue 3, which consumes its output, merges. That is the correct order, not
a mistake to be tidied up: the SDK pull request must carry the generated artefact before Infrahub's
content-level validation can pass against the pointer it bumps to.

## Implementation Strategy

### MVP scope

The feature's value is US1, and US1 cannot ship without US2 (typed errors that raise on an unrecognised
payload would be a regression, not a feature) or without the generator that produces its classes. So the
MVP is **Phases 1-4 plus 7-8**: US2, US3, US5, US1. US4 and US6 are genuinely optional to the MVP and can
follow.

---

## Notes

- [P] tasks touch different files and have no dependency on an incomplete task.
- Commit after each task or logical group; run `uv run invoke format lint-code` before each commit.
- Do not reference this document, its task IDs, or the ticket in any file that ships: code, comments,
  docstrings, changelog fragments, or documentation. Every shipped file must stand on its own.
- Stop at any checkpoint to validate the increment independently.
