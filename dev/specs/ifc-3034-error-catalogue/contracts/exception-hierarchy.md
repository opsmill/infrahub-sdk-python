# Contract: The exception hierarchy

The SDK's public interface here is the set of names a consumer can import from
`infrahub_sdk.exceptions`, catch, and read attributes off. This is what the change promises.

`infrahub_sdk.exceptions` is the supported import path for every exception the SDK raises, generated or
hand-written. A consumer never needs to know which module inside it defines a given class, and the
modules beneath it are internal. Every name importable from `infrahub_sdk.exceptions` before this
change is still importable from it afterwards, pinned by a test against a committed snapshot rather
than asserted.

## Catching

| Intent | Clause |
|--------|--------|
| Anything the server rejected, on either transport | `except ApiError` |
| Any GraphQL-path failure | `except GraphQLError` |
| Any failure the SDK observed as HTTP 401 or 403 | `except AuthenticationError` |
| One specific catalogued failure | `except UniquenessViolationError` (and so on per code) |
| One of the three authentication codes, whichever way it arrived | `except ApiError` then test `exc.code` |
| Anything the SDK raises | `except Error` |

The hierarchy is a plain tree: `GraphQLError` and `AuthenticationError` are siblings under `ApiError`,
and no class has more than one parent.

**The three authentication codes are the one asymmetry.** `AUTHENTICATION_REQUIRED`, `TOKEN_EXPIRED`,
and `PERMISSION_DENIED` have no class of their own, because they are the only codes that reach the SDK
on two different transports, and each transport already has a class an existing clause depends on:

| Arrival | Class raised | `exc.code` |
|---------|--------------|------------|
| A real 401 or 403, when the failure escapes before query execution | `AuthenticationError`, as today | the catalogue code |
| Inside an HTTP 200 `errors` array, when a resolver raised it | `GraphQLError`, as today | the catalogue code |

**Any of the three can arrive either way**, so the arrival path is a property of how the server
happened to fail, not of the code. Distinguish them by code, and catch `ApiError` unless you genuinely
want one arrival path only:

Catch the code however it arrived — the form to reach for:

```python
except ApiError as exc:
    if exc.code == "TOKEN_EXPIRED":
        ...
```

Or, to handle only the pre-execution arrivals from the table above, accepting that a resolver-raised
failure carrying the same code raises `GraphQLError` and escapes this clause:

```python
except AuthenticationError as exc:
    ...
```

These are alternatives, not a sequence. `AuthenticationError` descends from `ApiError`, so an
`except ApiError` clause placed first makes any later `except AuthenticationError` unreachable.

So `except AuthenticationError` is not the clause that spans both arrival paths for *any* of the three
codes — `except ApiError` is. That is not a coverage loss: such a response raises `GraphQLError` today
too, so no existing clause stops catching anything it catches now.

Every clause that worked before the change still catches what it caught before (FR-018). The
broadenings below are deliberate. They are not numbered, because adopting a further code adds one.

- `except GraphQLError` now also catches node, branch, and schema lookup misses that involved no
  GraphQL request at all — both the client-side ones and the REST 404 the file handler turns into a
  `NodeNotFoundError` — because those classes are re-rooted under it.
- Code that catches a generic error to inspect its message will now sometimes receive a subclass whose
  message names the code, or the same class carrying a described failure's message instead of the query
  text.
- A failure the server reports under an adopted code, with a payload carrying the fields that code's
  class needs, now raises that class rather than `GraphQLError`. A server-reported `NODE_NOT_FOUND`
  reaches an `except NodeNotFoundError` clause that only saw client-side lookup misses before. The
  specific class and `GraphQLError` are both caught by `except GraphQLError`, so no clause stops
  catching what it catches now; a ladder that handles the specific class differently sees the
  server-reported ones arrive there too, which is the point of adopting the code.

## Reading a caught error

Available on every `ApiError`:

| Attribute | Contract |
|-----------|----------|
| `code` | The catalogue code string, or `None`. Never an integer. `None` means the SDK resolved no catalogue code — a pre-catalogue server, a REST failure, an error with no `extensions`, or an integer `code` on the wire. An unrecognised string code from a newer server is still readable here. |
| `http_status` | The status the governing error's `extensions` declares, or `None` when it declared none. This is metadata about the failure, not the status the transport observed — a catalogued data error arrives as HTTP 200, and the observed status is not carried on the exception at all. Once the generated classes land, a class's own declared status fills this in for a code whose envelope omitted it. The envelope's value is the catalogue's except where the catalogue could not resolve a status more specific than 500, in which case the server substitutes the HTTP status it is about to return — so a generated class's declared 500 and the envelope's value can differ. |
| the payload's fields | Not on the base. Each catalogued class carries its payload's fields as directly typed attributes — `UniquenessViolationError.node_kind` is a `str`, `.fields` a `list[str]` — typed exactly as the catalogue declares them, so a required field is never optional and needs no guard. The three exceptions are `NodeNotFoundError`, `BranchNotFoundError`, and `SchemaNotFoundError`, whose attributes are optional because those classes are also raised with no catalogue code behind them — a client-side lookup miss, or the REST 404 that has a response but no code; guard on `exc.code is not None` there. The raw payload dict remains in `extensions["data"]` for anything forwarding it verbatim. |
| `extensions` | The raw `extensions` mapping of the governing error, or `None`. |
| `errors` | The complete server error list, unreordered — empty for a client-side raise. |
| `query`, `variables` | The GraphQL query and variables where there was one, otherwise `None`. |

`errors`, `query`, and `variables` are readable on every `ApiError`, not only on those built from a
server response. A purely client-side `NodeNotFoundError` has an empty `errors` and `None` for the rest,
so code that catches `GraphQLError` and inspects them never has to guard for a missing attribute.

`UNDEFINED_ERROR` is readable on `code` like any other: it means the server explicitly reported a gap
in its own catalogue, and it is not the same as an error carrying no `extensions`. It is the one code
that never shapes the message, because it describes nothing; see [Messages](#messages).

A current server codes **every** error it reports, falling back to `UNDEFINED_ERROR` where its
catalogue has no entry, so `exc.code is not None` is not the test for "the server described this".
`code_names_the_failure(exc.code)` is, and it is importable from `infrahub_sdk.exceptions`.

## Cross-version behaviour

Any SDK version talks to any server version. Parsing never raises.

| Situation | Behaviour |
|-----------|-----------|
| A code the SDK has a class for | That class is raised, built from the envelope's payload through its own `from_payload`. Until the generated bindings land, that is the three adopted codes (`NODE_NOT_FOUND`, `BRANCH_NOT_FOUND`, `SCHEMA_NOT_FOUND`) and every other code raises the generic class for the branch. |
| A code the SDK has never heard of | The generic class for the branch is raised — `GraphQLError` for data failures, `AuthenticationError` for 401/403 — with `code` set to the string the server sent. |
| A known code whose payload gained a field | The unknown field is ignored; behaviour is unchanged. |
| A server predating the catalogue, or an error with no `extensions` | Today's behaviour exactly; `code` is `None`. |
| An integer `code` on `/graphql` from a pre-catalogue server | Not surfaced as a catalogue code; `code` is `None`. |
| A payload that violates the catalogue's own contract | The generic class for the branch, with the code still readable. The specific class's attributes are typed as the catalogue declares them, so there is nothing to populate a required one with. |

Every fallback above is logged at debug level with the code involved, so an SDK meeting a newer server
is diagnosable in the field rather than only in tests.

Regenerating bindings buys typed handling of newly catalogued codes. It never changes which exception
a byte-identical response produces for a code the SDK already knows, because the first error in the
response governs unconditionally — not the first *recognised* one.

## Multiple errors in one response

The first error in the response determines the class raised. The complete list is retained on the
exception, unreordered, and nothing is discarded. If the first error carries no code and a later one
does, the generic class for the branch is raised.

## Messages

A **server-reported** failure the catalogue describes has a message naming the code and the governing
error's message, and contains no query text. A failure the catalogue does not describe - one with no
`extensions`, an integer `code`, or the code `UNDEFINED_ERROR` - keeps a message byte-identical to
today's, query text and full error list included. The query is available as an attribute in both cases.

`UNDEFINED_ERROR` sits on the second side of that line deliberately. Since the server codes every
error it reports, treating it as described would apply the short message to every failure the
catalogue has no entry for, replacing the query text and the later errors with a code that says only
that the server had nothing to say. It stays readable on `exc.code`.

Both transports follow the same rule about **which** message may be named beside a code: the governing
error's, which is the first one. Joining the rest would file them under a code that is not theirs; the
complete list stays on `exc.errors`.

The qualifier matters because three catalogued classes can also be raised with **no catalogue code
behind them**: `NodeNotFoundError`, `BranchNotFoundError`, and `SchemaNotFoundError`. That covers a
client-side lookup miss, which has no server response at all, and the REST 404 the file handler turns
into a `NodeNotFoundError`, which has a response and a message but no catalogue code, since REST carries
the legacy envelope. Both keep the message they produce today, because there is no code to name. As
everywhere else, `exc.code is not None` is the test for which case you are holding.

Where the catalogue provides them, the server's message names the failing action and resource kind, so
that detail now appears in logs and CLI output in place of the query text that used to be there.

## Parity

The async and sync clients raise the same type with the same attributes for the same failure, for
every catalogued code.

## Stability

`infrahub_sdk.exceptions` is treated as public and is the one import path a consumer needs. That is a
stronger promise than the constitution's tiering strictly requires — only `Config`, `InfrahubClient`,
and `InfrahubClientSync` are exported at top level — and it is made deliberately, because
`infrahubctl`, the Ansible collection, and external consumers already import from it directly.

Concretely:

- No name is removed or renamed, and no constructor loses a signature it has today.
- Every name importable from `infrahub_sdk.exceptions` before this change remains importable from it,
  which a test pins against a committed snapshot. Restructuring the module into a package must not be
  observable from the outside.
- Modules beneath `infrahub_sdk.exceptions` are internal. Importing `…exceptions.catalogue` or
  `…exceptions.payloads` directly is not supported, and their layout may change.
- One annotation widens: `NodeNotFoundError.identifier` becomes `Mapping[str, list[str]] | str`. It is
  called out in a changelog fragment because external consumers read these attributes even though
  nothing in this repository does.
