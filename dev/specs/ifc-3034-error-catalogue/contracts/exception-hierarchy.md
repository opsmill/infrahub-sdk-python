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
| Any authentication or permission failure, either transport | `except AuthenticationError` |
| One specific catalogued failure | `except UniquenessViolationError` (and so on per code) |
| One of the three authentication codes | `except AuthenticationError` then test `exc.code` |
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

So distinguish them by code, not by type:

```python
except AuthenticationError as exc:
    if exc.code == "TOKEN_EXPIRED":
        ...
```

Every clause that worked before the change still catches what it caught before (FR-018). Two
broadenings are deliberate:

- `except GraphQLError` now also catches node, branch, and schema lookup misses that involved no
  GraphQL request at all — both the client-side ones and the REST 404 the file handler turns into a
  `NodeNotFoundError` — because those classes are re-rooted under it.
- Code that catches a generic error to inspect its message will now sometimes receive a subclass whose
  message names the code, or the same class carrying a catalogued message instead of the query text.

## Reading a caught error

Available on every `ApiError`:

| Attribute | Contract |
|-----------|----------|
| `code` | The catalogue code string, or `None`. Never an integer. `None` means the SDK resolved no catalogue code — a pre-catalogue server, a REST failure, an error with no `extensions`, or an integer `code` on the wire. An unrecognised string code from a newer server is still readable here. |
| `http_status` | The code's catalogue-declared status, or `None`. This is metadata about the failure, not the HTTP status of the response — a catalogued data error arrives as HTTP 200. Where the error carried an `extensions` mapping, the status the server actually returned is available as `exc.extensions["http_status"]` — guard on `exc.extensions` first, since it is `None` when the error carried none. The two can legitimately differ: the server replaces a declared 500 with the real HTTP status when it has a more accurate one. |
| the payload's fields | Not on the base. Each catalogued class carries its payload's fields as directly typed attributes — `UniquenessViolationError.node_kind` is a `str`, `.fields` a `list[str]` — typed exactly as the catalogue declares them, so a required field is never optional and needs no guard. The three exceptions are `NodeNotFoundError`, `BranchNotFoundError`, and `SchemaNotFoundError`, whose attributes are optional because those classes are also raised without a server response; guard on `exc.code is not None` there. The raw payload dict remains in `extensions["data"]` for anything forwarding it verbatim. |
| `extensions` | The raw `extensions` mapping of the governing error, or `None`. |
| `errors` | The complete server error list, unreordered — empty for a client-side raise. |
| `query`, `variables` | The GraphQL query and variables where there was one, otherwise `None`. |

`errors`, `query`, and `variables` are readable on every `ApiError`, not only on those built from a
server response. A purely client-side `NodeNotFoundError` has an empty `errors` and `None` for the rest,
so code that catches `GraphQLError` and inspects them never has to guard for a missing attribute.

`UNDEFINED_ERROR` is a code like any other: it means the server explicitly reported a gap in its own
catalogue, and it is not the same as an error carrying no `extensions`.

## Cross-version behaviour

Any SDK version talks to any server version. Parsing never raises.

| Situation | Behaviour |
|-----------|-----------|
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

A **server-reported** catalogued failure's message names the code and the server's message, and contains
no query text. An uncatalogued failure's message is byte-identical to today's, query text included. The
query is available as an attribute in both cases.

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
