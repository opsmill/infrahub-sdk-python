# Marketplace Browsing — Design

**Date:** 2026-07-02
**Branch:** `ic-feat-add-marketplace-browsing`
**Status:** Approved for planning

## Problem

`infrahubctl marketplace get <namespace/name>` can download a schema or collection,
but only if the user already knows the exact identifier. There is no way to discover
what the marketplace offers. This feature adds discovery ("browsing") commands.

## Guiding principle

Every addition is checked against the minimalism ladder (stop at the first that applies):

1. Does this need to exist? → no: skip it (YAGNI)
2. Already in this codebase? → reuse it, don't rewrite
3. Stdlib does it? → use it
4. Native platform feature? → use it
5. Installed dependency? → use it
6. One line? → one line
7. Only then: the minimum that works

Concretely: raw dict access (no new models — matches existing `marketplace.py`), Rich
for tables (already used), httpx for HTTP (already used), `json` stdlib for `--json`,
and reuse of every existing helper listed below. No new dependencies.

## Command surface

All commands live in `infrahub_sdk/ctl/marketplace.py`, registered on the existing
`AsyncTyper` `app`, alongside `get`.

| Command | Purpose |
| --- | --- |
| `marketplace list [--collections] [--limit N] [--json]` | Browse all schemas (default) or collections |
| `marketplace search <term> [--collections] [--limit N] [--json]` | Browse filtered by the API `search=` param |
| `marketplace show <namespace/name> [--collection] [--json]` | Full detail of one schema or collection |

- `--collections` (on `list`/`search`) switches the listing target to collections.
- `--collection` (on `show`) forces the collection endpoint; default auto-detects (mirrors `get`).
- `--limit N` caps total output.
- `--json` emits raw structured JSON to stdout; status/errors go to stderr.
- `--marketplace-url` and `CONFIG_PARAM` follow the existing resolution
  (flag → `INFRAHUB_MARKETPLACE_URL` env → config file → `https://marketplace.infrahub.app`).

## Marketplace API (confirmed against the live service)

### List / search

```text
GET {base}/api/v1/schemas       # default listing
GET {base}/api/v1/collections   # with --collections
```

Query params (only these are honoured; others are ignored by the service):

- `search=<term>` — filters on name / display_name / description
- `limit=<n>` — page size
- `cursor=<end_cursor>` — cursor pagination (NOTE: `after=` is ignored; the param is `cursor`)

Response envelope (both endpoints):

```json
{
  "items": [ ... ],
  "page_info": { "has_next_page": true, "end_cursor": "..." },
  "total_count": 52
}
```

Schema list item fields used: `namespace`, `name`, `display_name`, `download_count`,
`tags[].name`, `latest_version.semver`.
Collection list item fields used: `namespace`, `name`, `display_name`,
`download_count`, `schema_count`.

### Detail (for `show`)

```text
GET {base}/api/v1/schemas/{namespace}/{name}       # returns versions[], dependencies, ...
GET {base}/api/v1/collections/{namespace}/{name}   # returns items[] (members), dependencies, ...
```

`show` auto-detects type by probing both detail endpoints (schema wins on a 200/200
collision, consistent with `get`); `--collection` forces the collection endpoint.

## Pagination behaviour

Chosen: **fetch all, `--limit` to cap.**

- With no `--limit`: a `while` loop follows `page_info.end_cursor` (passing `cursor=`)
  until `has_next_page` is false, accumulating all items. Sensible at current scale
  (~52 schemas, ~10 collections).
- With `--limit N`: request a single page with `limit=N` (no cursor loop needed).
- The table footer prints `Showing <N> of <total_count>` when output is truncated.

## Reuse vs new code (all in `marketplace.py`)

**Reuse (no rewrite):**

- `_make_http_client(sdk_cfg)` — HTTP client honouring SDK proxy/TLS.
- `_parse_identifier(str)` — `namespace/name` → NamedTuple (used by `show`).
- `_host_from(url)` — hostname for error messages.
- `_is_transport_failure(...)` — 5xx / exception detection.
- `_ErrorClass` taxonomy — INVALID_INPUT / NOT_FOUND (exit 1), NETWORK (exit 2).
- Marketplace-URL / config / env resolution and `CONFIG_PARAM`.
- The `@catch_exception(console=console)` + Rich `console` output convention.

**New (minimal):**

- `_list_url(base, item_type)` — one-liner mirroring `_schema_url` / `_collection_url`.
- `_detail_url(base, item_type, ident)` — one-liner.
- `_fetch_all(client, url, *, search, limit)` — the one genuinely new helper: the
  cursor pagination loop returning `(items, total_count)`.
- Renderers: a Rich table builder for list/search results and a detail renderer for
  `show`. Plain functions using the existing `console`.

No pydantic models: the existing module reads API responses as raw dicts; this feature
matches that (ladder step 2).

## Output

**Default (Rich table):**

- Schemas: `Identifier (ns/name) · Display Name · Version (latest semver) · Downloads · Tags`
- Collections: `Identifier · Display Name · Schemas (count) · Downloads`
- `show`: a detail block (identifier, display name, description, downloads, author,
  timestamps) plus a versions table (schema) or members table (collection), and
  dependencies when present.
- Footer `Showing <N> of <total>` when truncated by `--limit`.

**`--json`:** the raw item list (`list`/`search`) or the raw detail object (`show`)
serialized with `json`, printed to stdout. Status messages and errors go to stderr,
so `--json` output is cleanly pipeable.

## Error handling

Reuse the existing taxonomy:

- Bad `namespace/name` for `show` → INVALID_INPUT (exit 1).
- 404 (no such item, or empty catalog is *not* an error — an empty list prints an
  empty table / `[]`) → NOT_FOUND for `show` only (exit 1).
- 5xx / transport failure → NETWORK (exit 2), message points at `--marketplace-url`.

## Scope notes

- **CLI-only; no async/sync dual variant.** Like `get`, these hit REST directly and
  are not `InfrahubClient` methods. The async/sync dual pattern applies to the client,
  not CLI commands.
- **No new dependencies.**

## Testing

Extend `tests/unit/ctl/test_marketplace_app.py` (Typer `CliRunner` + `HTTPXMock`):

- `list` schemas; `list --collections`.
- Multi-page cursor pagination (mock two pages; assert all items and correct `cursor=`).
- `--limit N` caps output and requests a single page.
- `search <term>` (passes `search=`); search with empty results.
- `show` schema (renders versions); `show` collection (renders members).
- `show` not-found; `show` auto-detect (schema-wins collision) and `--collection` force.
- `--json` output for `list`, `search`, `show` (valid JSON on stdout).
- Network error (5xx → exit 2) and invalid identifier (exit 1).

## Docs

- Regenerate `docs/docs/infrahubctl/infrahubctl-marketplace.mdx` via
  `uv run invoke docs-generate` (commands are introspected).
- Add a towncrier newsfragment `changelog/<issue>.added.md`.
