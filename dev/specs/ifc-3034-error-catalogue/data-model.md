# Data Model: Error Catalogue in the Python SDK

The entities here are exception classes and pydantic models. Field lists are the observable contract;
see [contracts/exception-hierarchy.md](./contracts/exception-hierarchy.md) for what a consumer may
rely on and [contracts/generator-contract.md](./contracts/generator-contract.md) for how the generated
half is produced.

Which module holds what is [research.md](./research.md) R1. In short: the hand-written hierarchy sits
in `base.py`, which imports nothing from inside the package; the payload models and per-code exception
classes are generated into `catalogue.py`; `factory.py` sits above both. Imports only ever point
downward.

The payload of a catalogued error is read as **typed attributes on the exception**, not as a payload
object. No class in this design exposes a `data` attribute, and no payload attribute is typed `Any` —
see [research.md](./research.md) R6. `Any` appears only in the raw decoded JSON that `extensions` and
`errors` hold, where the value types genuinely are unknown at the type level.

## Hierarchy

```text
Error                                   (existing root, unchanged)
├── ApiError                            NEW — "the server reported an error"
│   ├── GraphQLError                     re-rooted under ApiError
│   │   ├── NodeNotFoundError            re-rooted, unified, adopts NODE_NOT_FOUND
│   │   │   └── NodeInvalidError         inherits the re-rooting
│   │   ├── BranchNotFoundError          re-rooted, unified, adopts BRANCH_NOT_FOUND
│   │   ├── SchemaNotFoundError          re-rooted, unified, adopts SCHEMA_NOT_FOUND
│   │   └── <generated, one per non-401/403 code>
│   └── AuthenticationError              re-rooted under ApiError, name and constructor unchanged
└── … every other existing exception, untouched

# GraphQLError and AuthenticationError are siblings; neither inherits from the other,
# and no class in the package has more than one parent.
#
# The three 401/403 codes get no class of their own. They arrive on whichever generic
# class their transport produces — AuthenticationError for a real 401/403, GraphQLError
# for a resolver-raised failure inside a 200 response — and carry their identity in
# `code`: "AUTHENTICATION_REQUIRED", "TOKEN_EXPIRED", "PERMISSION_DENIED".
```

## ApiError

The base for "the server reported an error", carrying the parsed envelope (FR-001).

| Attribute | Type | Notes |
|-----------|------|-------|
| `code` | `str \| None` | A catalogue code string, or `None`. Never an integer, so the REST envelope's integer `code` cannot be mistaken for a catalogue code (FR-003). Generated classes carry it as a class attribute, since they are only ever raised from a response. The factory sets it per-instance in the two cases a class attribute cannot cover: an unrecognised code on a generic class, and **an adopted class**, whose `code` must stay `None` on a client-side raise and be set when the same class carries a server-reported failure. |
| `http_status` | `int \| None` | The status the envelope declares, not the one observed on the wire, which the exception does not carry. `None` when the governing error declared none. Generated classes will carry the catalogue's declared status as a class attribute, covering a code whose envelope omitted it. The envelope's value is the catalogue's in all but one case: where the catalogue could not resolve a status more specific than 500, the server substitutes the HTTP status it is about to return, so a generated class's declared 500 and the envelope's value can differ. |
| `extensions` | `dict[str, Any] \| None` | The raw `extensions` mapping of the governing error, so nothing the SDK does not model is lost. `Any` here is the honest type of decoded JSON, not an escape hatch: the mapping's value types genuinely are not known at the type level. |
| `errors` | `Sequence[dict[str, Any]]` (empty tuple by default) | The complete, unreordered server error list (FR-013). Lives here rather than only on `GraphQLError` because the authentication branch must retain it too and FR-015 freezes `AuthenticationError`'s constructor. The default is an immutable empty tuple and is only a floor for a directly constructed `AuthenticationError`; anything built from a response, and every adopted class, is constructed with a list. |
| `query` | `str \| None` | Class-level default `None`. |
| `variables` | `dict \| None` | Class-level default `None`. |

`ApiError` adds no required constructor arguments. Its subclasses keep the constructors they have
today, and the factory sets these attributes after construction.

Two mechanisms sit behind these attributes, and they answer different questions. The class-level
defaults guarantee the attributes *exist* on any `ApiError`, including an `AuthenticationError`
constructed directly through the constructor FR-015 freezes — so `except GraphQLError as exc:
exc.errors` can never raise `AttributeError`. The three adopted classes additionally call
`GraphQLError.__init__` explicitly so their envelope state is set by the constructor that owns it and
`errors` is a *list*, matching the type documented on `GraphQLError` rather than the base's tuple
default.

## GraphQLError

| Attribute | Type | Change |
|-----------|------|--------|
| `errors` | `list[dict[str, Any]]` | Unchanged. Complete and unreordered; the first element governs the raised class (FR-013). Every subclass reaches this constructor — the adopted three call it with `errors=[]` — so it is a list on every `GraphQLError`, never the base's tuple default. |
| `query` | `str \| None` | Unchanged, still populated for catalogued failures (FR-024). |
| `variables` | `dict \| None` | Unchanged. |
| `message` | `str` | Constructor gains an optional `message`. Omitted → today's string, byte-identical. Supplied by the factory for a catalogued failure → names the code and the server's message, with no query text (FR-022, FR-023). |

## AuthenticationError

Name, constructor, and default message unchanged (FR-015). It gains no subclasses and inherits the
`ApiError` attributes. It remains the class raised for every failure the SDK observed as HTTP 401 or
403, with `code` set per-instance by the factory: `None` on the REST path, which carries no catalogue
code, and the catalogue code on the GraphQL path — `"TOKEN_EXPIRED"`, `"AUTHENTICATION_REQUIRED"`, or
`"PERMISSION_DENIED"`.

`GraphQLError` likewise carries a `code` when a resolver-raised authentication or permission failure
arrives inside an HTTP 200 response. So both generic classes can be catalogued or uncatalogued, and
`exc.code` is the only thing that distinguishes those cases.

## Adopted classes

Three hand-written classes declare the catalogue code they represent, which is how the generator
knows not to define them:

| Class | `CODE` | Payload field promoted onto | Type change |
|-------|--------|----------------------------|-------------|
| `NodeNotFoundError` | `NODE_NOT_FOUND` | `node_kind` → `node_type`, `identifier` → `identifier` | `identifier` widens to `Mapping[str, list[str]] \| str` |
| `BranchNotFoundError` | `BRANCH_NOT_FOUND` | `branch_name` → `identifier` | none |
| `SchemaNotFoundError` | `SCHEMA_NOT_FOUND` | `kind` → `identifier` | none |

Their `from_payload` is hand-written, because the target attribute names already exist and are not the
catalogue's. Every construction shape in use today keeps working: the filter mappings passed from
`infrahub_sdk/store.py` and `infrahub_sdk/client.py`, and the plain string passed from
`infrahub_sdk/file_handler.py` that the current annotation wrongly excludes. `exc.code is not None`
distinguishes a server-reported raise from a client-side one.

Unlike the generated classes, **every attribute on these three is optional**, even where the catalogue
declares the underlying field required. Neither provenance populates the full set — the catalogue
supplies no `branch_name`, and four of the nine construction sites supply no node kind — so a
required attribute would be a promise the class cannot keep. See [research.md](./research.md) R9, which
also records the tripwire for splitting these classes and why that is a later change.

## Generated exception classes

Generated into `catalogue.py`, one per catalogue code that is not adopted. Each declares:

| Member | Value |
|--------|-------|
| `CODE` | The catalogue code string. |
| `code` | Class attribute equal to `CODE`. |
| `http_status` | The catalogue-declared status. |
| `DATA_MODEL` | The payload model class, used to validate the envelope. |
| Promoted attributes | One per payload field, typed as the catalogue declares it — required fields non-optional, nullable fields carrying their declared default. Assigned in `__init__`, so they always exist. |
| `from_payload` | Classmethod taking a validated payload plus the envelope, returning the constructed exception. The factory's only construction path. |
| docstring | The catalogue's `description`, plus its stability level. |

The declared status decides whether a code gets a class at all, not which parent it takes: a 401/403
code gets none, and everything else descends from `GraphQLError` (FR-008). Twelve generated classes
today, each with exactly one parent.

## Generated payload models

Generated into `catalogue.py` alongside the classes, one per catalogue code, including codes with an
empty payload and including the adopted codes. Named from the catalogue's `data_schema.title` verbatim
(FR-007), so SDK and frontend binding names agree. `model_config = ConfigDict(extra="ignore")` makes an
unknown field from a newer server a no-op (FR-004). Required fields stay required; nullable fields carry
the catalogue's declared default.

These models are the validation mechanism and the source of the promoted attributes' types. They are
importable — useful for building a test fixture — but a consumer never reads one off an exception.

A payload that fails validation falls back to the generic class for the branch, with the code still
readable. The server has a reachable path that emits an empty payload under a code whose schema declares
required fields, so this is a real state rather than a hypothetical one.

Field types, mapped from the catalogue's JSON Schema vocabulary:

| JSON Schema | Python |
|-------------|--------|
| `{"type": "string"}` | `str` |
| `{"type": "string", "format": "date-time"}` | `datetime` |
| `{"type": "integer"}` / `{"type": "number"}` | `int` / `float` |
| `{"type": "boolean"}` | `bool` |
| `{"type": "array", "items": T}` | `list[T]` |
| `{"anyOf": [T, {"type": "null"}]}` | `T \| None` |

Anything outside that vocabulary fails generation loudly rather than emitting a guess.

## Resolution map

`CODE_TO_EXCEPTION: dict[str, type[ApiError]]` in `catalogue.py`, covering every catalogue
code: generated classes for most, imported adopted classes for the three. It is the only lookup the
factory performs, and a miss is the entire fallback story (FR-012).

## The two envelopes

Both shapes are read; only one is a catalogue envelope.

**GraphQL** (`/graphql`) — the catalogue envelope. Data errors arrive as HTTP 200 with an `errors`
array; auth failures arrive as a real 401/403.

```json
{
  "errors": [
    {
      "message": "…",
      "extensions": {"code": "UNIQUENESS_VIOLATION", "http_status": 422,
                     "data": {"node_kind": "TestPerson", "fields": ["name"]}}
    }
  ]
}
```

**REST** (`/api/…`) — the legacy envelope, where `extensions.code` is an *integer* mirroring the HTTP
status. No catalogue code, no `data`. Parsed for its messages only; `exc.code` stays `None`.

```json
{"errors": [{"message": "…", "extensions": {"code": 401}}]}
```

## State transitions

None. Exceptions are constructed, raised, and read.
