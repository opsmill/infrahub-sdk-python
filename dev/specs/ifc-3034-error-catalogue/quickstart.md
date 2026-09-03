# Quickstart: validating the error catalogue in the SDK

Runnable checks that prove the feature works end to end. Each scenario names what it proves and the
success criterion it maps to. Details of the promised behaviour live in
[contracts/exception-hierarchy.md](./contracts/exception-hierarchy.md); the generation half lives in
[contracts/generator-contract.md](./contracts/generator-contract.md).

## Prerequisites

```bash
uv sync --all-groups --all-extras
```

Two checkouts are involved. Scenarios 1 to 6 run here; scenario 7 runs from an Infrahub checkout with
the SDK as its `python_sdk` submodule.

## Scenario 1 — Typed errors and their payloads

Proves that every catalogue code is reachable as its own type with its payload's fields as typed
attributes, and that a developer never has to read a message (SC-001).

```bash
uv run pytest tests/unit/sdk/test_error_catalogue.py -v
```

Expected: one passing case per catalogue code. Each asserts the raised class and concrete attribute
values read directly off the exception — `exc.node_kind` and `exc.fields` for `UNIQUENESS_VIOLATION`,
`exc.node_type` and `exc.identifier` for `NODE_NOT_FOUND` — and asserts `exc.code` and
`exc.http_status` match the catalogue entry. No test reads a payload object, because there isn't one.

## Scenario 2 — Cross-version tolerance

Proves that nothing raises during parsing on any server version, old or new (SC-004).

```bash
uv run pytest tests/unit/sdk/test_error_catalogue.py -k crossversion -v
```

Expected: passing cases for an unknown code (generic class for the branch, `code` readable as a
string), an unknown payload field (ignored), an absent `extensions` (`code is None`, today's
behaviour), a pre-catalogue integer `code` on `/graphql` (`code is None`), and a payload that
violates the catalogue contract (the generic class for the branch, with `exc.code` still readable). No
case raises during parsing.

Then prove the factory cannot make things worse than they were, by feeding it malformed envelopes —
`errors` as a bare string, `extensions` as a list, `code` as a nested object:

```bash
uv run pytest tests/unit/sdk/test_error_catalogue.py -k malformed -v
```

Expected: each degrades to today's generic exception. A bug in resolution can never replace the
server's error with an SDK `TypeError`.

## Scenario 3 — The hierarchy and the existing clauses

Proves that no `except` clause loses coverage, that the CLI ladder is not shadowed, and that one
clause catches every server-reported error on either transport (SC-003, SC-008).

```bash
uv run pytest tests/unit/sdk/test_exceptions.py tests/unit/sdk/test_exceptions_public_names.py \
    tests/unit/ctl/test_utils.py -v
uv run pytest tests/unit/ -q
```

Expected: `TokenExpiredError` is caught by `except AuthenticationError` **and** by
`except GraphQLError`; `NodeInvalidError` is an instance of `GraphQLError`; `ApiError` catches both a
GraphQL and an authentication failure; every name importable from `infrahub_sdk.exceptions` before the
change is still importable from it; reading `exc.errors`, `exc.query`, and `exc.variables` off a purely
client-side `NodeNotFoundError` returns empty/`None` rather than raising `AttributeError`; driving
`handle_exception` with `NodeNotFoundError` produces the not-found rendering rather than the GraphQL
error rendering; a catalogued failure renders as its code plus the server's message rather than as
"Authentication failure" or a bare error list; rendering an exception with no server errors behind it
prints the message. The full unit suite is green, with any deliberately changed assertion updated rather
than skipped.

## Scenario 3b — The exceptions package has no import cycle

Proves the package's import graph points strictly downward, so the cycle the layout was designed to
avoid cannot creep back in.

```bash
uv run pytest tests/unit/sdk/test_exceptions_layering.py -v
uv run python -c "import infrahub_sdk.exceptions.base"
```

Expected: the layering test passes, reporting any intra-package import that points at its own layer or
higher — including imports written inside a function body, which is how a cycle usually returns once the
obvious route is closed. The bare import succeeds on its own, which is the observable form of the rule
that `base.py` depends on nothing else in the package, generated or otherwise.

## Scenario 4 — Async and sync parity

Proves both clients raise the same type with the same attributes (SC-006).

```bash
uv run pytest tests/unit/sdk/test_error_catalogue.py tests/unit/sdk/test_client.py -k "standard or sync" -v
```

Expected: every raise-path case passes for both `client_type` values, asserting the same class and the
same payload attributes.

## Scenario 5 — No string matching left, and refresh still works

Proves the silent-refresh decision is typed while a pre-catalogue server still refreshes (SC-002).

```bash
uv run pytest tests/unit/sdk/test_relogin_headers.py -v
grep -rn "Expired Signature" infrahub_sdk/
```

Expected: a refresh is attempted for a 401 carrying `TOKEN_EXPIRED` and for a 401 carrying the legacy
`"Expired Signature"` message, and not for an unrelated 401. The `grep` returns exactly one site — the
documented pre-catalogue fallback inside the shared decision helper, down from the two occurrences
today, one in each relogin wrapper — and no other message match for a catalogued failure. The GraphQL
schema-validation probing used for server feature detection is out of scope and still present.

## Scenario 6 — Messages, lint, and docs

Proves the message change and the repository gates (SC-007).

```bash
uv run pytest tests/unit/sdk/test_exceptions.py -k message -v
uv run invoke format lint-code
uv run invoke docs-generate && uv run invoke docs-validate
uv run invoke lint-docs
ls changelog/
```

Expected: a catalogued failure's message names the code and the server's message and contains no
query text; an uncatalogued failure's message is byte-identical to today's. `docs-validate` passes with
no change to `sdk_ref`, since the `exceptions` package is categorised as ignored for API-doc
generation — if it is not categorised at all, `docs-generate` fails with
`Uncategorized packages under infrahub_sdk/`. `changelog/` carries fragments for the typed errors, the
`identifier` widening, and the `except GraphQLError` broadening.

## Scenario 6b — The envelope shape is what the server actually sends

Proves the contract against a live server rather than against fixtures written alongside the parser
that reads them. Requires Docker.

```bash
uv run pytest tests/integration/test_infrahub_client.py tests/integration/test_infrahub_client_sync.py \
    -k "catalogue" -v
```

Expected: saving a node that collides on a unique attribute raises `UniquenessViolationError` with the
node kind and colliding fields populated from the real payload; deleting a missing node raises
`NodeNotFoundError` with its kind and identifier. Both pass on the async and sync clients. If these
fail while scenario 1 passes, the unit fixtures encode an envelope the server does not send.

## Scenario 7 — Generated bindings cannot silently drift

Proves that a catalogue change omitting regeneration fails validation, and that a regenerated artefact
is byte-identical to a fresh generation (SC-005). Run from the Infrahub checkout.

```bash
uv run invoke backend.generate
git -C python_sdk diff --exit-code infrahub_sdk/exceptions/catalogue.py   # clean: byte-identical
uv run invoke backend.validate-generated                                  # passes
```

Then prove the negative: add a code to the backend catalogue, regenerate the catalogue JSON alone, and
re-run the validator.

```bash
uv run invoke backend.export-error-catalogue
uv run invoke backend.validate-generated   # must fail, naming the stale submodule artefact
```

Expected: the second run exits non-zero with a hint pointing at `uv run invoke backend.generate`.
Revert the catalogue change afterwards.

The generator is a pure text transform over `schema/error-catalogue.json` plus an `ast` parse of the
SDK's `base.py`, so it needs no running Infrahub — only the submodule checked out, which every Python
job in that repository already requires.

## Manual end-to-end check

Against a running Infrahub, with the SDK installed:

```python
from infrahub_sdk import InfrahubClient
from infrahub_sdk.exceptions import ApiError, UniquenessViolationError

client = InfrahubClient()
node = await client.create(kind="TestPerson", name="Jane")   # a name that already exists
try:
    await node.save()
except UniquenessViolationError as exc:
    print(exc.code, exc.http_status, exc.node_kind, exc.fields)
except ApiError as exc:
    print("uncatalogued or unrecognised:", exc.code)
```

Expected: the specific class, its catalogue code and status, and the colliding field names read
directly off the exception with no guard and no intermediate object — and no query text in the message.
