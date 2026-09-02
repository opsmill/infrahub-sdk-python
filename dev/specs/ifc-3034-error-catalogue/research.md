# Research: Error Catalogue in the Python SDK

Every decision below was reached against the two checkouts as they stand, not from the specification
alone. The specification carried no `NEEDS CLARIFICATION` markers; what follows resolves the
mechanism questions it deliberately left to the plan.

## Survey findings the decisions rest on

The catalogue (`schema/error-catalogue.json`, `infrahub_catalogue_version: "1"`) holds 15 codes.
Twelve declare a non-auth status (400, 404, 422, 423, 500) and three declare 401/403
(`AUTHENTICATION_REQUIRED`, `TOKEN_EXPIRED`, `PERMISSION_DENIED`). Two codes declare an empty payload
(`AUTHENTICATION_REQUIRED`, `UNDEFINED_ERROR`). One field carries `format: date-time`
(`TOKEN_EXPIRED.expired_at`); the rest are strings, nullable strings, and one string array
(`UNIQUENESS_VIOLATION.fields`).

Three derived class names collide exactly with hand-written SDK classes: `NODE_NOT_FOUND` →
`NodeNotFoundError`, `BRANCH_NOT_FOUND` → `BranchNotFoundError`, `SCHEMA_NOT_FOUND` →
`SchemaNotFoundError`.

Raise sites that need to change: `GraphQLError` is raised at `infrahub_sdk/client.py:1360` and
`:2348` (`_execute_graphql`, async and sync) and `:1429` and `:2417` (the file-upload variants).
`AuthenticationError` is raised from the same four GraphQL paths (`:1350`, `:1688`, `:2338`, `:3857`)
and from six REST paths in `infrahub_sdk/object_store.py` plus one in `infrahub_sdk/file_handler.py`,
all with the identical four-line "decode, collect messages, join with ` | `" shape.

Infrahub already owns two generation paths that write into the submodule
(`tasks/backend.py::_generate_schemas` and `::_generate_protocols`) and validates both with
`git -C python_sdk diff --exit-code` inside `validate_generated`. Separately,
`tasks/frontend.py::regenerate_error_bindings` regenerates the three catalogue-derived artefacts
(the JSON, the frontend TypeScript bindings, the docs page) and `check_error_bindings` diffs them.
The frontend's hand-rolled generator (`frontend/app/scripts/generate-error-bindings.mjs`) is the
closest precedent for what the SDK generator must do.

Infrahub declares the SDK as `infrahub-sdk = { path = "python_sdk", editable = true }`, so `uv sync`
fails outright without the submodule. Every Python job in that repository therefore already needs
`submodules: true`, and 20 of the 32 checkouts in `ci.yml` set it.

## R1 — Where the generated bindings live in the SDK, with no circular imports

**Decision**: convert `infrahub_sdk/exceptions.py` into a package of five modules in a strict,
enforced layer order. No module imports a module at its own level or above, and no module imports the
package façade.

| Layer | Module | Written or generated | May import |
|-------|--------|----------------------|------------|
| 0 | `base.py` | hand-written | nothing from inside the package |
| 1 | `catalogue.py` | generated, in full | `base` |
| 2 | `factory.py` | hand-written | `base`, `catalogue` |
| 3 | `__init__.py` | hand-written | all of the above |

**Rationale**: two constraints pull against each other. The generated classes must descend from the
base classes, and `infrahub_sdk.exceptions` must re-export the generated classes (FR-005). Keeping
both in one module makes that a cycle whose only resolution is a wildcard import at the bottom of the
file — fragile, and in exactly the module that must never fail to import. Splitting hand-written from
generated makes the dependency one-way and puts the façade above both.

Nothing in `base.py` needs anything from the generated module. That falls out of the payload decision
in R6: because a payload's fields are promoted to directly typed attributes on the exception rather
than exposed as a payload object, no hand-written class needs to name a generated model type — not even
the three adopted classes. So the hand-written hierarchy imports and behaves identically whether or not
the generated module is present, with no type-only import required to achieve it.

**Enforcement**: `tests/unit/sdk/test_exceptions_layering.py` parses each module in the package with
`ast` and asserts every intra-package import points to a strictly lower layer. It walks *every*
`Import` and `ImportFrom` node, not only module-level ones — a function-body import is the classic way
a cycle gets reintroduced once the obvious route is closed — and it counts imports inside
`TYPE_CHECKING` blocks. An upward import fails the pull request that adds it, so the property cannot
decay into the cycle it was designed out of. No new dependency.

**Consequences to handle**:

- `tasks.py::get_modules_to_document` auto-discovers packages under `infrahub_sdk/` and raises
  `ValueError` for any package that is not explicitly categorised, so `"exceptions"` must be
  categorised. It goes in `packages_to_ignore`. Documenting it would generate `sdk_ref` pages from the
  *generated* classes, which couples the SDK's own `docs-validate` to an Infrahub-side regeneration:
  Infrahub writes new bindings into the submodule, nothing re-runs the SDK's `docs-generate`, and the
  next SDK pull request fails on stale docs for a change made in another repository. `exceptions.py` is
  not documented in `sdk_ref` today, so ignoring the package preserves current behaviour exactly and
  creates no coupling. FR-028 is satisfied by the hand-written topic page, which is the better artefact
  for a hierarchy anyway.
- The façade re-exports with `from .base import *` and `from .catalogue import *`, each source module
  declaring its own `__all__` (generated for `catalogue.py`). That keeps the export
  surface automatic as codes are added and stays visible to mypy and `ty`, at the cost of an `F403`
  `per-file-ignores` entry with a comment — the same treatment
  `infrahub_sdk/schema/generated/*.py` already gets. `infrahub_sdk.exceptions` is the supported import
  path for consumers; the submodules beneath it are internal, and the façade is what makes that true
  rather than aspirational.
- First generation is a bootstrap: the SDK pull request lands `catalogue.py` produced by running the
  Infrahub generator from the paired branch, verified by hand once, which is what US5 anticipates.

**Alternatives considered**:

- *A sibling `infrahub_sdk/error_catalogue.py`.* Fails FR-005 — `infrahub_sdk.exceptions` could not
  re-export it without reintroducing the cycle.
- *Keep one `exceptions.py` and wildcard-import the generated module at the bottom of the file.*
  Works, and is precisely the fragility this decision exists to avoid.
- *Generate the whole of `exceptions.py`.* Rejected. Roughly thirty hand-written exceptions
  unrelated to the catalogue live there — rate limiting, fragment rendering, YAML validation, and the
  three unified classes with custom constructor and `__str__` logic. Generating the file would put all
  of that under a generator owned by another repository, and would require the generator to carry
  hand-written class bodies as template data. What this design does take from that idea is the part
  worth keeping: the generated file is generated *in full*, so there is never a hand-edited region
  inside a generated file or a generated region inside a hand-written one.
- *Split the generated models into their own module below `base.py`.* Necessary only if a hand-written
  class must name a generated model type, which the promotion decision in R6 removes. Without that
  need the split buys nothing and costs a module, a second artefact to validate, and an ordering
  constraint on generation.

## R2 — Where the generator lives and how validation is wired

**Decision**: one Jinja2 template `backend/templates/generate_sdk_errors.j2`, rendered by a
`_generate_sdk_error_bindings` helper in `tasks/backend.py` and called from the existing
`backend.generate` task, with `backend.validate-generated` gaining
`git -C python_sdk diff --exit-code infrahub_sdk/exceptions/catalogue.py`.

No new command, and no task outside the `backend` namespace generates the SDK's bindings.

**Rationale**: the entry point already exists and already does exactly this job.

```python
@task
def generate(context: Context) -> None:
    """Generate internal backend models."""
    _generate_schemas(context=context)      # → python_sdk/infrahub_sdk/schema/generated
    _generate_protocols(context=context)    # → python_sdk/infrahub_sdk/protocols.py
```

`backend.generate` writes into the SDK submodule today, paired with `backend.validate-generated`. The
error bindings are a third artefact of the same kind — Infrahub-generated, SDK-destined — so they
belong in the same pair rather than in a second entry point for the same category of work.

The namespace boundary that matters here is **producer, not location**. `backend` names the side that
generates; that it writes into `python_sdk/` is the point of the task, not a violation of it. The
frontend is a sibling *consumer* of the same catalogue, which is why hooking regeneration into
`frontend.regenerate-error-bindings` was wrong: a consumer generating another consumer's artefact.

Two incidental notes for the implementer. `generate`'s docstring says "internal backend models", which
has been inaccurate since it started generating SDK protocols; adding a third artefact is a good moment
to correct it. And `_generate_custom_graphql_types` is called by `validate_generated` but not by
`generate`, so `generate` is already the smaller set of the two — adding the error bindings to both
keeps them in step.

**On the CI job**: no new step and no new job. `backend-validate-generated` runs
`backend.validate-generated`, which now covers the error bindings too. Submodule availability is not a
discriminator in that placement: `infrahub-sdk = { path = "python_sdk", editable = true }` in Infrahub's
`pyproject.toml` means `uv sync` fails without the submodule, so every Python job in that repository
already requires `submodules: true` — 20 of the 32 checkouts in `ci.yml` set it today.

**Consequences**:

- That job's `if` currently fires on `backend == 'true' || documentation == 'true'`. Add
  `error_catalogue == 'true'` so a hand-edit of `schema/error-catalogue.json` alone cannot slip past.
  This is the only CI edit required.
- **No new path filter.** An entry for the submodule artefact could never match: from the superproject
  a submodule is a single gitlink, so a change inside it appears only as a change to `python_sdk` —
  the same limitation that forces the diff to run inside the submodule. The repository already handles
  this with `sdk_files: - "python_sdk"`, commented "Catch updates to the submodule commit" and included
  in `backend_all`. The generator template is likewise already covered, since `backend_files` is
  `backend/**`, and `error_catalogue_files` already lists the catalogue JSON.
- The failure hint names `uv run invoke backend.generate`.
- The SDK's bindings move with the other artefacts Infrahub generates into the SDK — the schema models
  and the protocols — which is the grouping that matters for this feature. The catalogue's *other*
  derived artefacts (the frontend bindings and the docs page) are regenerated by their own consumers,
  and CI is what keeps all of them in step: the `error_catalogue` filter gates every one of their
  checks, so a catalogue change that skips any of them fails the pull request that made it.

**Pre-existing wart, deliberately left alone**: `tasks/frontend.py::regenerate_error_bindings` already
calls `backend.export_error_catalogue` and `docs.generate_error_catalogue`, so it is a catalogue
orchestrator carrying a frontend label. Tidying that is not this feature's job — but it is why
regeneration must not be hooked there: a consumer generating another consumer's artefact.

**Alternatives considered**:

- *A pytest in `backend/tests/unit/errors/test_export.py` that renders in memory and byte-compares
  against the committed files*, mirroring `test_export_matches_committed_file` for the catalogue JSON.
  Attractive — precise failure output, no git involved — but the renderer's output only becomes
  canonical after `ruff format`, so the test would have to shell out to ruff or the template would
  have to emit already-formatted output for all 15 codes. Rejected as one mechanism too many;
  `validate_generated` already does render-then-format-then-diff for the two other submodule
  artefacts. Worth revisiting if the diff output ever proves hard to act on.
- *Adding the SDK generation to `frontend.regenerate-error-bindings` and the check to
  `frontend.check-error-bindings`.* Rejected: the frontend namespace should generate frontend artefacts
  only, and a consumer should not generate another consumer's artefact. It would also have needed a
  Python toolchain in a Node-only CI job to validate a Python artefact, making the job name lie.
- *A new `generate` / `validate` pair in `tasks/sdk.py`, matching the shape `tasks/schema.py` uses.*
  Internally consistent, and the right answer if no entry point existed — but `backend.generate` and
  `backend.validate-generated` already are that pair for everything Infrahub generates into the
  submodule. A second entry point for the same category of work costs discoverability and invites the
  two from drifting apart.
- *A standalone Python script mirroring the frontend's `.mjs` generator.* Would duplicate the
  template-render-then-ruff pipeline `tasks/backend.py` already has.
- *No generator at all — hand-write the 15 classes once.* Worth stating plainly, because 15 classes is
  not much typing. The generator's value is not saved keystrokes, it is US5: a catalogue change that
  skips the SDK fails the pull request that made it, instead of surfacing months later as a code that
  quietly falls back. Hand-written classes buy the typing and none of the drift protection.

## R3 — Name derivation

**Decision**: the exception class name is the code's underscore-separated parts capitalised and
joined, with `Error` appended only when the result does not already end in `Error`. The payload model
name is `data_schema.title` verbatim.

Worked examples: `UNIQUENESS_VIOLATION` → `UniquenessViolationError` / `UniquenessViolationData`;
`UNDEFINED_ERROR` → `UndefinedError` (not `UndefinedErrorError`) / `UndefinedErrorData`;
`MERGE_IN_PROGRESS` → `MergeInProgressError` / `MergeInProgressData`.

**Rationale**: FR-006 and FR-007. Taking the payload name from the declared title rather than
deriving it keeps SDK and frontend binding names identical, which the frontend generator already
relies on. The generator asserts a non-empty `data_schema.title`, as the frontend one does, so a
catalogue entry that omits it fails generation loudly.

**Undeclared collisions must fail generation.** Deriving a name that already exists in `base.py` is
fine when the SDK declared that adoption (R4) and a latent disaster otherwise. The façade re-exports
`base` and then `catalogue`, so a generated class would win the name and silently shadow the
hand-written one — changing what an existing `except` clause catches, from a change made in the other
repository. This is not hypothetical: the SDK already defines `ValidationError`, `RateLimitError`,
`InvalidResponseError`, `FileNotValidError`, and `ResourceNotDefinedError`, and `VALIDATION_ERROR`,
`RATE_LIMIT`, `INVALID_RESPONSE`, `FILE_NOT_VALID`, and `RESOURCE_NOT_DEFINED` all derive exactly
those names. A 429 code in the catalogue is an entirely ordinary thing to add.

The generator therefore collects every class name defined in `base.py`, not only those carrying a
`CODE`, and aborts on any derived name that matches one without a matching `CODE` declaration. The
remedy is then a deliberate SDK decision — adopt the code, or rename — taken in the pull request that
adds the code rather than discovered months later.

## R4 — Codes whose class already exists

**Decision**: adoption is discovered, not configured. The hand-written class declares the code it
represents (`CODE = "NODE_NOT_FOUND"` on `NodeNotFoundError`, and likewise for `BranchNotFoundError`
and `SchemaNotFoundError`); the generator parses `infrahub_sdk/exceptions/base.py` with `ast`,
collects every class whose body assigns a `CODE` string, and for those codes emits an import plus a
`CODE_TO_EXCEPTION` entry instead of a class definition. It still emits the payload model for an
adopted code.

**Rationale**: the alternative is a hand-maintained code-to-class table in the generator, which is
the kind of thing FR-008 exists to avoid and which would live in the wrong repository — the decision
to unify a name is an SDK decision. Discovery puts the declaration next to the class it describes, so
adopting a fourth code later is a one-line SDK change with no generator edit.

Reading the source with `ast` rather than importing the SDK keeps the generator a pure text transform,
as the frontend's generator is, and means generation never depends on the SDK checkout being in an
importable state. The same walk collects every class *name* defined in `base.py`, which is what the
collision check in R3 needs.

**Fallback**: if the `ast` walk proves awkward, import `infrahub_sdk.exceptions.base` and read `CODE`
off the classes — `base.py` imports nothing from inside the package, so it is importable on its own.
Such a walk must filter to classes whose *own* `__dict__` carries `CODE`, because `NodeInvalidError`
inherits `CODE = "NODE_NOT_FOUND"` from `NodeNotFoundError`; it would otherwise see two classes
claiming the same code and let dict ordering pick the winner. The `ast` walk is immune, since it only
sees class bodies.

**Alternative considered**: generating all 15 classes under distinct names and having the
hand-written unified classes subclass them. Rejected — the resolution map would then point at the
generated base, so the factory would raise the generated class and never the unified one that
consumers catch.

## R5 — Parent class derivation

**Decision**: every generated class descends from `GraphQLError`. Classes for codes declaring 401 or
403 *additionally* descend from `AuthenticationError`: `class PermissionDeniedError(GraphQLError,
AuthenticationError)`. Derived from the catalogue entry at generation time, with no per-code table
(FR-008).

Today that yields `AuthenticationRequiredError`, `TokenExpiredError`, and `PermissionDeniedError`
with both parents, and the remaining twelve with `GraphQLError` alone.

**Rationale**: the first design here made the two parents alternatives, which was wrong, and the
survey proves it rather than suspects it. `backend/infrahub/graphql/app.py:298-300` returns
`status_code=200` for every executed query, and `graphql/error_formatter.py` maps resolver-raised
failures onto catalogue codes inside that response's `errors` array — including `PERMISSION_DENIED`,
`AUTHENTICATION_REQUIRED`, and `TOKEN_EXPIRED`. Only failures that escape *before* execution get a
real 401/403, which `api/exception_handlers.py:52-55` states outright. So a permission failure can
arrive on the data path, in a response `except GraphQLError` catches today. A single authentication
parent would silently remove that coverage and violate FR-018.

The diamond closes on `ApiError`, so the MRO is
`PermissionDeniedError → GraphQLError → AuthenticationError → ApiError → Error`, and `__init__`
resolves to `GraphQLError`'s — correct, because these classes only ever arise on the GraphQL
transport. A REST authentication failure raises plain `AuthenticationError` and never a generated
subclass, since REST carries no catalogue codes (FR-015).

**Consequence for the CLI**: its ladder tests `AuthenticationError` before `GraphQLError`, so a
resolver-raised `PERMISSION_DENIED` will render as "Authentication failure: …" where today it renders
through `print_graphql_errors`. That is a deliberate, user-visible change; it is pinned by a test, and
flagged as an open question in the plan rather than assumed to be wanted.

**Note on `http_status`**: the class attribute is the catalogue's declared value, which is what US1
acceptance scenario 3 asserts. The wire value can differ — `api/exception_handlers.py:26-27` replaces
a declared 500 with the real HTTP status when it has a more accurate one — and stays available as
`exc.extensions["http_status"]`. Documented, so the divergence does not read as a bug.

## R6 — How a consumer reads the payload

**Decision**: the payload's fields are promoted to directly typed attributes on the exception class.
The payload model validates the envelope and populates them; it is not the access path.

```python
# generated
class UniquenessViolationError(GraphQLError):
    CODE = "UNIQUENESS_VIOLATION"
    code = "UNIQUENESS_VIOLATION"
    http_status = 422
    DATA_MODEL = UniquenessViolationData

    def __init__(self, node_kind: str, fields: list[str], **envelope: Any) -> None:
        self.node_kind = node_kind
        self.fields = fields
        super().__init__(**envelope)
```

```python
# consumer
except UniquenessViolationError as exc:
    print(exc.node_kind, exc.fields)     # str, list[str]
```

Attribute types mirror the catalogue exactly: a required field is not optional, and a nullable field
carries its declared default. There is no payload attribute on `ApiError` and none on the generated
classes either.

**Rationale**: this is what US1 actually asks for — "carrying the node kind and the colliding field
names as typed attributes". A payload *object* on the exception was never a requirement; it was a
design choice, and a costly one. Exposing `data` on the base forces the base to name a type for it,
and narrowing that type on each subclass is an unsound override of a mutable attribute, so it can only
be bought with `Any` on the base, a read-only property pair, or a generic hierarchy. Promotion makes
the whole question disappear: there is nothing on the base to narrow.

It is also the access pattern the design already used for the three adopted classes, whose payload
fields land on the existing `node_type` and `identifier` attributes (R9). Promoting everywhere removes
an inconsistency where three codes were read one way and twelve another.

Two further simplifications fall out. `base.py` no longer needs to name a generated model type, so the
package needs no separate generated models module and no type-only import to stay independent of
generated code (R1). And the `Optional` payload attribute — with its `if exc.data:` guard at every call
site — is gone.

**Construction**: the factory never assembles attributes itself. Each class exposes a
`from_payload(cls, payload, **envelope)` classmethod — generated for generated classes, hand-written
for the three adopted ones, where it maps `node_kind` onto the existing `node_type` and so on. The
factory validates with `DATA_MODEL` and calls `cls.from_payload(...)`, so promotion stays with the
class that knows its own attribute names and the factory carries no per-code branching.

**Payload model shape**: generated payload models are pydantic v2 `BaseModel`s with
`model_config = ConfigDict(extra="ignore")`, honouring the catalogue's `required` list so a required
field is a required model field. JSON Schema is mapped as: `string` → `str`, `integer` → `int`,
`number` → `float`, `boolean` → `bool`, `string` with `format: date-time` → `datetime`,
`array` → `list[T]`, `anyOf: [T, {"type": "null"}]` → `T | None` with the declared default. Any
construct outside that vocabulary fails generation with the offending fragment in the message, as the
frontend generator does. A code with an empty `properties` object still gets a real model class with
no fields, not a special case.

**Decision on validation failure**: if the payload does not validate — a server violating its own
emission contract, or a `date-time` the SDK cannot parse — the operation falls back to the generic class
for the branch, with `code` readable, the raw `extensions` retained, and a debug-level log recording the
failure. A `ValidationError` never escapes a raise path.

**Rationale**: FR-004 requires tolerating unknown *fields*, which `extra="ignore"` delivers, and User
Story 2 requires that nothing raises during parsing. Promotion then forces this: a required field is a
non-optional attribute, and there is nothing to populate it with when validation fails. The alternative
is making every promoted attribute optional on every class, which taxes every consumer of the feature's
central use for a narrow server-side glitch.

An earlier form of this decision kept the specific class and left the payload `None`, on the grounds
that FR-013 requires the raised type to be "a pure function of the response" and so it must not depend
on payload validity. That reasoning was overreaching. A malformed payload *is* part of the response;
FR-013's concern is that the type must not depend on **binding freshness** — on which SDK version the
consumer happens to hold — and falling back on an invalid payload does not touch that property.

The case is also narrower than it first appears. `graphql/error_formatter.py:59-60` initialises the
payload to `UndefinedErrorData()` and only overwrites it when an `isinstance` guard matches, so the
server can emit `data: {}` under a code whose schema declares required fields. But for the adopted
codes — the ones US1's acceptance scenarios exercise — the guard tests the very exception type the code
was resolved from, so it cannot realistically fail.

## R7 — Raise-time resolution

**Decision**: two hand-written factories in `infrahub_sdk/exceptions/factory.py`:

- `graphql_error_from_response(errors, query, variables)` for the `errors`-array path.
- `authentication_error_from_response(response)` for the 401/403 path, which subsumes the four-line
  shape repeated at eleven call sites and preserves today's ` | `-joined message.

Resolution reads `extensions.code` from the **first** error in the response and looks it up in
`CODE_TO_EXCEPTION`. A hit validates `extensions.data` with the class's `DATA_MODEL` and raises via
`cls.from_payload(...)`. A miss — unrecognised code, absent `extensions`, a non-string `code`, or a
payload that fails validation — raises the generic class for the transport the SDK observed.

**Which class is raised and what `code` reports are separate questions.** `exc.code` is set from the
wire whenever the wire carried a *string* code, whether or not a class matched it: an unrecognised code
from a newer server is readable there (US2 acceptance scenario 1), and so is a recognised code whose
payload failed to validate. `exc.code` is `None` only when there was no string code to read — an absent
`extensions`, or the REST envelope's integer `code` (FR-003). Conflating the two would break both places
that key on `exc.code is not None`: the CLI branch in R11 and the server-reported test in R9.

The complete `errors` list is retained on the exception in every case, unreordered (FR-013) — which is
why `errors` belongs on `ApiError` rather than only on `GraphQLError`, since the authentication branch
must retain it too and FR-015 freezes `AuthenticationError`'s constructor.

**The fallback follows the transport, never the code's declared status.** For an unrecognised code the
SDK has no binding and therefore cannot know the declared status at all; for a recognised one the
declared status describes the failure, not the transport. So the case that bites is a *recognised*
401/403 code whose payload fails to validate inside an HTTP 200 body: routing by declared status would
send it to the authentication branch, where an existing `except GraphQLError` would stop catching it.

R5's dual base does not rescue that case, and it is worth being precise about why: the dual base shapes
the per-code classes, and the class a fallback raises is the *generic* one, which has a single parent.
Only the transport rule preserves the coverage here.

**Construct with keyword arguments, always.** A generated class's `__init__` takes its promoted fields
first and forwards the envelope to `super().__init__`, and for the auth-branch classes the MRO resolves
that to `GraphQLError.__init__`, whose *first positional parameter* is `errors`. Anything constructing
one of these positionally — the shape the eleven existing `AuthenticationError` raise sites use today,
`TokenExpiredError(" | ".join(messages))` — assigns a message string into a field expecting a list of
error dicts, reproducing by construction the exact corruption `analyzer.py` already has. The factories
construct with keywords only, and a test asserts `exc.errors` is a sequence of dicts on the auth path.

**The auth factory must tolerate a non-JSON body.** Two of the sites it replaces call
`exc.response.json()` directly rather than `decode_json`, so a 401 carrying an HTML error page from a
proxy currently raises a JSON decode error in place of the authentication error. The factory uses
`decode_json` and falls back to the plain status when the body is not JSON, which is the same tolerance
R10 requires of the relogin helper for the same reason.

**The factory must be total.** It sits on the failure path of every client method, so an unexpected
exception inside it would replace a legitimate server error with an SDK `TypeError` and lose the
original failure entirely — the worst possible blast radius for a library. Resolution is therefore
wrapped so that *any* unexpected error degrades to constructing today's generic exception. Tested by
feeding the factory deliberately malformed envelopes: `errors` as a string (which `analyzer.py`
produces today), `extensions` as a list, `code` as a nested object.

**Fallback logging**: every fallback — unresolved code, absent envelope, invalid payload — logs at
debug with the code involved. Cross-version fallbacks are precisely the signal a maintainer wants from
the field when an SDK meets a newer server, and silence makes SC-004's guarantees observable only in
tests.

**Rationale**: the first error governs unconditionally, so the raised type is a pure function of the
response rather than of which generated bindings the SDK happens to hold — the reasoning FR-013
records. Reading `extensions.code` only when it is a `str` is what keeps the REST envelope's integer
`code` from ever being surfaced as a catalogue code (FR-003).

**Defensive detail**: two call sites already construct `GraphQLError` with something that is not a
list of dicts. `infrahub_sdk/analyzer.py:42` passes the bare string `"Schema is not provided"`, and
`infrahub_sdk/testing/schemas/animal.py:154` passes `[resp.errors]`, a list whose single element is not
a dict. The factory is on neither path, but the CLI renderer and anything iterating `errors` is.
Correct both call sites, and keep `print_graphql_errors`' non-list guard — which needs a `return` it
does not currently have, since today it prints the non-list value and then falls through and iterates
it anyway.

## R8 — Message construction

**Decision**: `GraphQLError.__init__` gains an optional `message` parameter. The factory passes a
message naming the code and the server's message for a catalogued failure and passes nothing for an
uncatalogued one, so today's `f"An error occurred while executing the GraphQL Query {query},
{errors}"` string is reproduced byte-for-byte in the uncatalogued case (FR-023, SC-007). `query` and
`variables` remain attributes in both cases (FR-024).

**Consequence**: `tests/unit/sdk/test_graph_traversal.py:383` asserts on `GraphQLError`'s message
text (`match="Source node not found"`). That path stays uncatalogued today, so the assertion holds;
the test is re-checked deliberately rather than assumed, per the specification's edge case.

## R9 — Unifying `NodeNotFoundError`, `BranchNotFoundError`, `SchemaNotFoundError`

**Decision**: these three promote their payload fields onto the attributes they already have, via a
hand-written `from_payload`, so a consumer reads the same attribute regardless of which path raised the
error:

| Class | Existing attribute | Promoted from |
|-------|--------------------|---------------|
| `NodeNotFoundError` | `node_type`, `identifier` | `node_kind`, `identifier` |
| `BranchNotFoundError` | `identifier` | `branch_name` |
| `SchemaNotFoundError` | `identifier` | `kind` |

This is the same promotion R6 applies to every other code; the only difference is that the target
attribute names already exist and are not the catalogue's, so the mapping is hand-written rather than
generated.

`identifier`'s annotation widens to `Mapping[str, list[str]] | str`, which is what FR-016 calls
"documented as such": the plain string is not new behaviour, it is what
`infrahub_sdk/file_handler.py:168` already passes and what the current annotation wrongly excludes. The
three classes are re-rooted under `GraphQLError` (via `ApiError`), and `NodeInvalidError` inherits that
re-rooting — asserted by a test, not assumed.

Because there is no payload attribute, "did this come from the server?" is answered by `exc.code is not
None`, which is true of every server-reported error rather than only of ones carrying a payload.

**Rationale**: this satisfies "one documented way to obtain the identifying detail that works
regardless of which path raised the error" without inventing a new accessor that existing consumers
do not know about. Nothing in this repository reads these attributes except the classes' own `__str__`
rendering, so the blast radius is entirely external, which is why the widening goes in the release
notes.

**Alternative considered**: a new normalised property (`identifier_display` or similar) alongside an
unchanged `identifier`. Rejected — it adds surface for a problem the widening already solves, and
leaves the file handler's existing string still outside the declared type.

## R10 — The typed silent-refresh decision

**Decision**: `handle_relogin` and `handle_relogin_sync` decide via a shared helper that reads
`errors[0].extensions.code == "TOKEN_EXPIRED"`, falling back to the existing
`"Expired Signature" in messages` check when no code is present (FR-019). The helper tolerates a
non-JSON or empty 401 body rather than letting `response.json()` raise, since the wrapper sees REST
responses too and only GraphQL carries the catalogue envelope.

**Rationale**: the wrapper inspects the raw response before any exception exists, so it cannot reuse
the factory; a small shared reader keeps the async and sync copies from drifting. Keeping the legacy
check as a fallback is what makes a pre-catalogue server still refresh.

**Out of scope, deliberately**: the GraphQL schema-validation probing used for server feature
detection matches on *uncatalogued* conditions and stays exactly as it is (FR-021).

## R11 — The re-rooted classes' missing attributes, and the CLI ladder

**The defect this fixes.** `NodeNotFoundError.__init__` does not call `GraphQLError.__init__`, and
neither do `BranchNotFoundError`'s or `SchemaNotFoundError`'s. Re-rooting them under `GraphQLError`
therefore produces instances on which `errors`, `query`, and `variables` do not exist *at all*. A
consumer writing `except GraphQLError as exc: … exc.errors` gets an `AttributeError` on any
client-side lookup miss, and `print_graphql_errors(errors=exc.errors)` raises while reading its
argument. Note that degrading the renderer on an *empty* `errors` does not address this: the attribute
is absent, not empty, so the renderer raises before it can check.

**Decision**:

- `handle_exception` gains a branch *above* the class-based ladder, keyed on `exc.code is not None` —
  any server-reported error carrying a catalogue code — which renders the code and the server's
  message, plus the GraphQL path where server errors exist. An error with no code falls through to
  today's ladder unchanged.
- The three adopted classes call `super().__init__(errors=[], query=None, variables=None, message=...)`
  explicitly, so their envelope attributes are set by the constructor that owns them. This is the fix
  rather than relying on class-level defaults: a default standing in for constructor state also makes
  `exc.errors` a *tuple* on a client-side raise and a *list* everywhere else, so the documented type
  would be wrong for exactly the classes this feature unifies.
- `ApiError` still declares defaults for `errors`, `query`, and `variables` — an immutable empty tuple
  for `errors` — but only as a can't-crash floor for a directly constructed `AuthenticationError`, whose
  constructor FR-015 freezes. Anything built from a response goes through a constructor or factory that
  sets a list.
- `print_graphql_errors` degrades to the exception's message when there is nothing to render. Its
  `isinstance(errors, list)` guard also needs the `return` it currently lacks, since today it prints the
  non-list value and then falls through and iterates it anyway.
- In `infrahub_sdk/ctl/utils.py::handle_exception`, move the
  `(SchemaNotFoundError, NodeNotFoundError, ResourceNotDefinedError, GraphQLQueryError)` branch
  *above* the `GraphQLError` branch, since re-rooting makes the later branch unreachable and would
  silently change CLI output for exactly the errors this feature makes specific.

**Tests**: read `exc.errors`, `exc.query`, and `exc.variables` off a purely client-side
`NodeNotFoundError`; drive `handle_exception` with each class to assert the ladder's behaviour rather
than reading the source; render an exception with no server errors behind it.

**Why a keyed branch rather than a reordered class branch.** The requirement is that a user can see why
something failed. Neither existing branch delivers that for a catalogued failure: the
`AuthenticationError` branch would print "Authentication failure: …" for a `PERMISSION_DENIED`, which
mislabels it — the user is authenticated and simply not permitted — while the `GraphQLError` branch
prints the server error list without naming the condition. Rendering the code plus the server's message
names the actual failure in both cases.

Keying the branch on `exc.code is not None` rather than on a class also removes the shadowing hazard for
catalogued errors permanently: it tests data rather than class identity, so no future re-rooting can
make it unreachable. And because it only claims errors carrying a code, every uncatalogued failure keeps
today's rendering byte-identical, which is the same guarantee FR-023 makes for messages.

**Also checked**: `infrahub_sdk/ctl/cli_commands.py:237` and `infrahub_sdk/ctl/validate.py:88` each
catch `GraphQLError` with no competing branch, so re-rooting cannot shadow anything there. The class
ladder still needs its reordering, because a client-side `NodeNotFoundError` has no code and so reaches
it.

## R12 — Testing strategy

**Decision**: response-envelope fixtures under `tests/fixtures/error_catalogue/`, loaded via
`read_fixture()`, driven through `httpx_mock` at the transport boundary — no `unittest.mock`.
Parametrized cases use the dataclass-with-`name` pattern, and every `pytest.raises` carries `match=`.

Coverage is split explicitly by layer, because SC-006 read literally ("across all catalogued codes")
would mean 15 codes on both clients through the client layer, which fights the constitution's
requirement that unit tests stay fast:

| Layer | Scope |
|-------|-------|
| Factory | Exhaustive: every catalogue code, its raised class, and every promoted attribute's value. All cross-version cases — unknown code, unknown payload field, absent `extensions`, pre-catalogue integer `code`, invalid payload falling back to the generic class — plus the malformed-envelope totality cases. |
| Client | Representative parity set covering both branches, both transports, and the file-upload variant, parametrized over `["standard", "sync"]` via the `BothClients` fixture. |
| Hierarchy | The dual base for auth codes; `NodeInvalidError` inheriting the re-rooting; attribute access on a client-side raise; the ladder's behaviour. |
| Public surface | Every name importable from `infrahub_sdk.exceptions` before the change is still importable from it, pinned against a committed snapshot list. |
| Broadenings | Both accepted behaviour changes asserted directly: `except GraphQLError` catches a client-side `NodeNotFoundError`; a catalogued message differs from the generic one while an uncatalogued message stays byte-identical. |
| Integration | A small number of real catalogued failures driven against a live server via testcontainers, on both clients. |

**Rationale**: the constitution requires both paths tested, concrete assertions, and deliberate
behaviour changes pinned by a test rather than worked around. The public-surface snapshot is what makes
"no name importable from `infrahub_sdk.exceptions` may disappear" a check rather than an intention —
necessary because the module is being restructured into a package.

**Why unit tests alone are not sufficient here.** Every fixture in the layers above is written by the
same hand that writes the parser, so the whole suite can pass green against an envelope shape the
server never sends — and the shape is the entire contract this feature consumes. The constitution is
explicit that behaviour depending on real server responses belongs in integration tests, and the tier
already exists (`tests/integration/`, `infrahub-testcontainers`, with per-client files
`test_infrahub_client.py` and `test_infrahub_client_sync.py`).

Scope it small and keep it there: drive two genuinely reachable failures — a uniqueness violation on
`.save()` and a missing node on `.delete()` — against a live server, and assert the raised class, the
code, and the promoted attributes. Two cases are enough to validate the envelope shape that every
unit fixture then reuses; the exhaustive per-code coverage stays at the fast, mocked layer where it
belongs.

## R13 — Documentation

**Decision**: a new hand-written `docs/docs/python-sdk/topics/error_handling.mdx` covering the
hierarchy, how to catch by branch versus by code, the cross-version guarantees, the two accepted
broadenings, and the note that `infrahub_sdk.exceptions` is the supported import path. It links to
Infrahub's published catalogue reference for the code list instead of restating it. The Python SDK
sidebar globs the `topics` directory, so no sidebar edit is needed.

**Rationale**: restating 15 codes in this repository creates a second source of truth that rots the
first time a code is added upstream, and nothing here validates it — a direct Principle VII risk.
Infrahub already generates that list from the same artefact. What is genuinely SDK-specific is the
hierarchy and the guarantees, and that is what the page carries.

One content note: a catalogued message now names the failing action and resource kind where the
catalogue provides them (`PermissionDeniedData` carries both), and that text reaches logs and CLI
output where a wall of query text used to be. Worth a line for anyone shipping SDK logs onward.

## R14 — Release notes

**Decision**: towncrier fragments in `changelog/`, one per user-visible change — the typed errors, the
`identifier` widening, and the `except GraphQLError` broadening.

**Rationale**: FR-016 requires the widening to be called out in the change's release notes, and this
repository's release notes are files, not prose in a pull request: `[tool.towncrier]` in
`pyproject.toml` sets `directory = "changelog"` with `orphan_prefix = "+"` for entries without an issue
number. Naming the fragments as work makes FR-016 verifiable instead of aspirational.

## R15 — Type-check the generated class shape before generating 15 of it

**Decision**: hand-write one generated-shape class and run both `mypy` and `ty` over it before the
template is finalised. The shape to check: promoted attributes assigned in `__init__`, a `from_payload`
classmethod returning `Self`, `**envelope` forwarded to `super().__init__`, and the dual base from R5.

**Rationale**: promotion removed the variance problem that made this a real risk, so what remains is
routine — but the constitution requires both checkers clean, `ty` is newer, and the dual base plus a
`Self`-returning classmethod is the least ordinary construct in the design. Finding a disagreement in
one hand-written class costs minutes; finding it across 15 generated ones costs a regeneration cycle in
another repository.

Note that no suppression is anticipated anywhere in this design. If the spike shows one is needed, that
is a signal the shape is wrong rather than a licence to add it.

## R16 — Sequencing across the two repositories

**Decision**: the Infrahub-side generator and its first hand-verified run come before the SDK-side
typed-raising work can be demonstrated, regardless of user-story priority labels.

**Rationale**: US1 is P1 and US5 is P2, but the per-code classes US1 delivers are produced by the
generator US5 builds. Priority labels describe value, not order. Task generation must take the order
from the dependency, not from the labels, or the P1 story will be picked up first and immediately
block. FR-002 does soften this — the envelope parses onto the base classes with no bindings at all, so
`code`, `http_status`, and the relogin fix (US4) are independently landable — but the typed per-code
classes are not.

## R17 — Landing order across the two repositories

**Decision**: the SDK change lands first, then Infrahub bumps its submodule pointer to it.

**Rationale**: this is the pattern the two repositories already follow. Infrahub's pointer-moving
commits — `chore(sdk): bump python_sdk to head of infrahub-develop` and feature commits that move the
pointer inline — target SDK commits already present on the SDK's `infrahub-develop` branch, so the SDK
side is merged before the pointer advances.

It is also the only order that works here. Infrahub's `validate_generated` diffs the submodule's
*content*, so the generated module must already exist in the SDK at the pointer Infrahub carries. The
first generation is therefore hand-run locally to produce the artefact for the SDK pull request, which
is what US5 anticipates, and every regeneration afterwards follows the same order.

Inferred from the repositories' history rather than from a written practice, so worth one confirmation
from whoever owns the release flow before the paired pull requests go up.

## R18 — What this plan does not touch

The git integrator's repository-import failure handling, anything about what the server emits, and
any release-time gate on either side. Pull-request-time validation is the only enforcement mechanism,
matching how the existing generated artefacts are treated (FR-027).
