# External Contract: Marketplace REST API

**Scope**: This document reverse-describes the subset of the `marketplace.infrahub.app` REST API that the `infrahubctl marketplace download` command relies on. **This is not a contract we own** — it captures the CLI's assumptions so that drift between client expectation and server reality can be caught in tests.

**Base URL**: `https://marketplace.infrahub.app` (default). Overridable via `--marketplace-url` or the `marketplace_url` setting in `infrahubctl.toml` / `INFRAHUB_MARKETPLACE_URL` env.

---

## Endpoint 1 — Download latest schema

```text
GET {base_url}/api/v1/schemas/{namespace}/{name}/download
```

**Success (200)**:

- `Content-Type`: `application/yaml` (or `text/yaml` / `text/plain`)
- Response body: raw YAML payload of the schema.
- Response header: `x-schema-version: <semver>` — resolved version the server returned. Required for the CLI to echo the version to the user.

**Not found (404)**: JSON body `{"detail": "<reason>"}`. Treated by the CLI as input to the not-found / auto-detect fallback flow.

**Other 4xx**: JSON body `{"detail": "<reason>"}`; surfaced as an error with the detail message.

**5xx / transport failure**: surfaced as a network-class error (see `research.md` R-4).

---

## Endpoint 2 — Download specific schema version

```text
GET {base_url}/api/v1/schemas/{namespace}/{name}/versions/{version}/download
```

Same response contract as Endpoint 1, but `{version}` is a user-supplied semver.

**404 semantics**:

- If the schema itself does not exist, a 404 is returned. Cannot be distinguished from "version missing" by URL alone, so the CLI MUST probe the unversioned endpoint first when constructing a "version-not-found" vs. "not-found" error (see `research.md` R-4).
- If the schema exists but the specific version is not published, a 404 is returned.

---

## Endpoint 3 — Download collection

```text
GET {base_url}/api/v1/collections/{namespace}/{name}/download
```

**Success (200)**: JSON body with shape:

```json
{
  "collection": {
    "namespace": "acme",
    "name": "starter-pack",
    "schema_count": 2,
    "downloaded_count": 2,
    "skipped": [
      { "namespace": "acme", "name": "broken", "reason": "no published version" }
    ]
  },
  "schemas": [
    {
      "namespace": "acme",
      "name": "network-base",
      "semver": "1.0.0",
      "filename": "acme-network-base-1.0.0.yml",
      "content": "---\n..."
    }
  ]
}
```

The CLI writes each `schemas[].content` to disk under `<output_dir>/<collection_name>/<schemas[].name>.yml` (today) or a flat layout under `<output_dir>/` (future — see implementation notes below).

**404 / other errors**: same as Endpoint 1.

---

## Implicit contract for auto-detection

The CLI issues Endpoints 1 and 3 in parallel when the user omits `--collection`. The contract assumed is:

- Both endpoints are idempotent and safe to issue concurrently.
- Either endpoint responds with a well-formed 404 (not a 5xx) when the identifier is not present as that item type. A 5xx from either probe is treated as a transport failure and aborts auto-detection.
- If both endpoints return 200, the CLI applies the documented "schema wins" precedence (`research.md` R-3).

**Follow-up (out of scope)**: Request the marketplace team add lightweight metadata endpoints (`GET /api/v1/schemas/{ns}/{name}` and `GET /api/v1/collections/{ns}/{name}` without `/download`) so the CLI can probe cheaply without paying for the payload on the wasted side of a 200-200 collision. When those ship, the CLI swaps its probe targets and keeps the download endpoints only for the winner.

---

## Versions of this contract

This document reflects the API shape observed on or before **2026-04-21**. Any new fields added server-side are expected to be backward compatible; breaking changes require a coordinated CLI update.
