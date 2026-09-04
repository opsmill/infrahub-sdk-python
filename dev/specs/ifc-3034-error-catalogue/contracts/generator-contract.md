# Contract: Generating the SDK's error bindings

One artefact crosses from the Infrahub repository into the SDK. This is the contract between the two
sides. The SDK holds no copy of the catalogue schema (FR-010).

## The artefact

- **Source**: `schema/error-catalogue.json` in the Infrahub repository.
- **Output**: `infrahub_sdk/exceptions/catalogue.py` in the SDK submodule.
- **Owner**: Infrahub. The SDK never regenerates it, exactly as it never regenerates `protocols.py`
  or its schema models.
- **Committed**: yes. Generation happens in a pull request, not at install time, so catalogue drift is
  visible in the diff.

The file is generated **in full**. There is never a hand-edited region inside a generated file, nor a
generated region inside a hand-written one.

## What the generated module contains

It opens with a header marking it generated and not to be edited, naming the source artefact, recording
the catalogue's `infrahub_catalogue_version`, and giving the regeneration command (FR-009) — the same
marking style as the repository's other generated files. It declares `__all__`, which is what lets the
package façade re-export it without a hand-maintained list.

The body holds three things:

- One pydantic payload model per catalogue code, including codes with an empty payload and including
  adopted codes. These validate the envelope and supply the promoted attributes' types.
- One exception class per catalogue code the SDK has not adopted, each promoting its payload's fields
  to directly typed attributes and exposing a `from_payload` classmethod.
- `CODE_TO_EXCEPTION`, mapping every catalogue code to its class — generated classes for most,
  imported adopted classes for the rest.

It imports only `infrahub_sdk.exceptions.base`, which imports nothing from inside the package. That
keeps the package's import graph one-way with no cycle: `base` → `catalogue` → `factory` → the façade.

Codes are emitted in sorted order so that reordering the catalogue's JSON does not churn the diff.

## Derivation rules

No hand-maintained per-code table exists on either side. Everything is derived from the catalogue
entry:

| Output | Derived from |
|--------|--------------|
| Exception class name | The code's parts capitalised and joined, with `Error` appended only if it does not already end in `Error`. `UNDEFINED_ERROR` → `UndefinedError`. |
| Payload model name | `data_schema.title`, verbatim. |
| Base classes | `GraphQLError` always; `http_status in {401, 403}` additionally adds `AuthenticationError`, emitted as `(GraphQLError, AuthenticationError)`. |
| `http_status` class attribute | The catalogue's declared `http_status`. |
| Docstring | The catalogue's `description` and `stability`. |
| Promoted attribute names | The payload field names, verbatim. |
| Field and attribute types | The JSON Schema mapping in [data-model.md](../data-model.md); a required field is non-optional, a nullable one carries its declared default. |

## Adoption

Some catalogue codes are represented by a class the SDK already ships. Those classes declare the code
they represent with a `CODE` class attribute. The generator parses
`infrahub_sdk/exceptions/base.py` with `ast`, collects every class whose body assigns a `CODE`
string, and for those codes emits an import and a map entry instead of a class definition. The payload
model is still generated.

An adopted class supplies its own `from_payload`, since its attribute names are its existing ones
rather than the catalogue's.

Adopting a further code later is a one-line change in the SDK's hand-written module with no generator
edit. Discovery is by parsing rather than importing, so the generator stays a pure text transform and
generation never depends on the SDK checkout being importable. The same walk collects every class name
defined in `base.py`, which is what the collision check below needs. Parsing also sidesteps a trap an
attribute walk would hit: `NodeInvalidError` inherits `CODE` from `NodeNotFoundError`, so two classes
would appear to claim the same code.

## Failing loudly

Generation aborts, rather than emitting a guess, when:

- a catalogue entry has no integer `http_status`;
- a catalogue entry has no non-empty `data_schema.title`;
- a `data_schema` uses a construct outside the supported vocabulary, in which case the offending
  fragment appears in the error;
- `codes` is empty or the root is not an object;
- a derived class name collides with a class already defined in `base.py` that has not declared that
  code as adopted.

The first four are the assertions the frontend generator already makes, for the same reason. The last
is specific to Python's import semantics: the SDK's façade re-exports `base` and then `catalogue`, so an
undeclared collision would let the generated class silently take the name and change what an existing
`except` clause catches. The SDK already defines `ValidationError`, `RateLimitError`,
`InvalidResponseError`, `FileNotValidError`, and `ResourceNotDefinedError` — every one of them the name
a plausible future code would derive — so this is a live hazard rather than a theoretical one. Failing
generation forces the choice (adopt the code, or rename) into the pull request that adds the code.

## Validation

No new command. `uv run invoke backend.generate` renders the artefact alongside the schema models and
the protocols — the other two things Infrahub generates into the submodule — and
`uv run invoke backend.validate-generated` verifies it with
`git -C python_sdk diff --exit-code infrahub_sdk/exceptions/catalogue.py`. The diff must run inside the
submodule, because from the superproject `git diff` only sees the submodule pointer, which is the same
reason the existing schema-model and protocol checks are written that way.

The `backend` namespace owns this because it names the *producer*: Infrahub generates, the SDK receives.
Nothing outside it generates the SDK's bindings — in particular not
`frontend.regenerate-error-bindings`, which belongs to a sibling consumer of the same catalogue.

In CI this needs no new step and no new path filter: `backend-validate-generated` already runs
`backend.validate-generated` and already checks out the submodule. The one edit is that job's trigger,
which gains `error_catalogue == 'true'` so a hand-edit of `schema/error-catalogue.json` alone cannot
slip past.

Everything else is already covered, and by design rather than by luck:

| Change | What CI sees | Filter that catches it |
|--------|--------------|------------------------|
| The committed bindings in the submodule | The `python_sdk` gitlink moving — never the inner path | `sdk_files`, commented in the repo as "Catch updates to the submodule commit", which feeds `backend_all` |
| The generator template | `backend/templates/generate_sdk_errors.j2` | `backend_files` (`backend/**`), which feeds `backend_all` |
| The catalogue JSON | `schema/error-catalogue.json` | `error_catalogue_files`, which already lists it |

Note the first row: a path filter on `python_sdk/infrahub_sdk/exceptions/catalogue.py` would never match
anything. From the superproject a submodule is a single gitlink entry, so a change to a file inside it
appears only as a change to `python_sdk` — the same limitation that forces the `git diff` above to run
inside the submodule.

**Across the catalogue's four derived artefacts, CI is what keeps the set in step.** The JSON, the
frontend bindings, the docs page, and the SDK bindings are each generated by their own owner; the
`error_catalogue` file filter gates all of their checks, so a catalogue change that skips any one of
them fails the pull request that made it. That is where the drift protection lives, not in any single
regenerate-everything command.

Submodule availability is not a factor in that placement. Infrahub declares
`infrahub-sdk = { path = "python_sdk", editable = true }`, so `uv sync` fails without the submodule and
every Python job there already requires `submodules: true`. Any job that needs the submodule declares
it; the check goes where it belongs and the checkout follows.

A catalogue change that skips regeneration therefore fails the pull request that made it (FR-026).
There is no release-time gate on either side; pull-request-time validation is the mechanism, matching
how the existing generated artefacts are treated (FR-027).

## What regeneration does and does not buy

Regenerating adds typed handling for newly catalogued codes. It never changes which exception a
byte-identical response produces for a code the SDK already knows, and correctness never depends on
having regenerated — an SDK with stale bindings falls back rather than failing.
