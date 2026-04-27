# Phase 0 Research: Marketplace Download Command Update

## R-1: Auto-detection strategy for schema vs. collection

**Problem**: The CLI receives a `namespace/name` identifier and must decide whether to hit `/api/v1/schemas/...` or `/api/v1/collections/...` without the user having to pass `--collection`.

**Options evaluated**:

| # | Approach | Round-trips (schema case) | Round-trips (collection case) | Depends on new API? |
| - | -------- | ------------------------- | ----------------------------- | ------------------- |
| A | Probe `/schemas/{ns}/{name}/download` first; on 404 fall back to `/collections/{ns}/{name}/download` | 1 | 2 (first 404, then success) | No |
| B | Probe both endpoints in parallel with `asyncio.gather`; take whichever returns 200; if both 200, apply precedence rule | 1 wall-clock (2 wire) | 1 wall-clock (2 wire) | No |
| C | Call a dedicated resolver endpoint (e.g. `/api/v1/items/{ns}/{name}`) that returns the item type, then fetch the download | 2 | 2 | **Yes** — requires marketplace API addition |
| D | Use `HEAD` on both endpoints, then `GET` the winner | 2 (HEAD + GET) | 2 (HEAD + GET) | No (assuming HEAD is supported) |

**Decision**: **Option B — parallel probe with precedence tie-break.**

**Rationale**:

- One wall-clock round-trip for both schema and collection cases keeps the user-perceived latency identical to the pre-auto-detect behaviour.
- Requires no new marketplace endpoint, so it can ship without server-side coordination.
- Naturally implements FR-012 (collision precedence): if both endpoints succeed, apply "schema wins" and print the resolved type so the user notices.
- The extra wire request over Option A is one cheap 404 on the common case (either schema or collection, not both present). The wasted bandwidth is negligible versus the win on the collection case.

**Alternatives considered**:

- **Option A** was rejected because collection lookups would incur a doubled latency for what should be a first-class code path.
- **Option C** was rejected as out-of-scope: we don't control the marketplace API surface inside this feature. If such an endpoint is added later, the CLI can transparently switch to it (see R-5).
- **Option D** was rejected because not all HTTP deployments support `HEAD` cleanly on download endpoints that stream payloads, and we'd still need a subsequent `GET`.

**Implementation notes**:

- Use `httpx.AsyncClient` with `asyncio.gather(..., return_exceptions=True)` so one probe failing with 404 does not abort the other.
- For the schema probe, prefer the lightweight metadata endpoint (if one exists under `/api/v1/schemas/{ns}/{name}`, i.e. without `/download`) to avoid paying for the payload twice in collision cases. Verify endpoint availability in R-2 before relying on this — otherwise, accept that the schema probe downloads the payload on success.

---

## R-2: Available probe endpoints on the marketplace

**Problem**: Option B is most efficient if we can probe without downloading payloads. Need to confirm what lightweight endpoints are exposed.

**Decision**: **Use the existing `/download` endpoints for the initial implementation** and treat any future metadata endpoints as a later optimisation.

**Rationale**:

- We only have direct evidence of `/api/v1/schemas/{ns}/{name}/download` and `/api/v1/collections/{ns}/{name}/download` being live today (from the current `marketplace.py` implementation and its test fixtures).
- Starting with what is known to work means the feature ships without a cross-team dependency. The cost is a single wasted YAML payload in the "both exist" collision case and zero extra cost in every other case.
- **Follow-up action** (out of scope for this feature): file an issue against the marketplace service to add `GET /api/v1/schemas/{ns}/{name}` and `GET /api/v1/collections/{ns}/{name}` metadata endpoints that return type + available versions without the payload. When those land, swap the probe targets in a small follow-up.

**Alternatives considered**:

- Guessing endpoints (`/api/v1/items/{ns}/{name}`) based on common REST conventions — rejected; speculative and unverifiable inside this feature.

---

## R-3: Name collision precedence

**Problem**: `acme/foo` could legally exist both as a schema and as a collection. A deterministic rule is needed (FR-012).

**Decision**: **Schema wins**, and the CLI prints the resolved type so the user can detect an unexpected match.

**Rationale**:

- Matches the pre-auto-detect behaviour, where absent `--collection` the CLI always queried the schema endpoint. Users with existing scripts see no change.
- Collections are the "larger" deliverable — requiring an explicit `--collection` to pick them in a collision avoids accidental multi-file downloads.
- Users who intend to download the collection in a collision case must pass `--collection`, which also forces the explicit-override branch (FR-011).

**Alternatives considered**:

- **Collection wins**: rejected because it changes default behaviour for existing scripts without notice.
- **Error on collision**: rejected; it makes auto-detection fragile on operator edge cases and requires a full dual fetch even when the user would be satisfied with the schema.

---

## R-4: Error taxonomy

**Problem**: FR-008 requires four distinguishable failure classes: not-found, version-not-found, network-unreachable, invalid-input.

**Decision**:

| Class | Trigger | User-facing message template | Exit code |
| ----- | ------- | ---------------------------- | --------- |
| Invalid input | `namespace/name` fails `_parse_identifier` OR `--version` is malformed | `Invalid identifier '<value>'. Expected format: namespace/name` (or version-specific variant) | 1 |
| Not found | Both schema and collection probes return 404 | `No schema or collection named '<ns>/<name>' found on <marketplace-host>` | 1 |
| Version not found | Schema probe succeeds in general but `--version <v>` returns 404 | `Schema '<ns>/<name>' has no published version '<v>'. Run without --version for the latest.` | 1 |
| Network | `httpx.ConnectError`, `httpx.TimeoutException`, or any 5xx response | `Could not reach marketplace at <base-url>: <short-reason>. Check your connection or --marketplace-url.` | 2 |

**Rationale**:

- Exit codes 1 vs. 2 let CI pipelines distinguish "bad input/absent content" (deterministic) from "transient infrastructure" (retryable).
- Each class mentions the identifier or host, so the message is self-diagnosing in terminal scrollback.
- The `--version` class only applies when the schema itself is present, which we can detect because the no-version probe returns 200 while the versioned probe returns 404.

**Alternatives considered**:

- A single exit code with only text differentiation: rejected because automation frequently branches on exit code.
- Including stack traces for network errors: rejected; tracebacks bury the cause.

---

## R-5: Behaviour when only pre-release versions are published

**Problem**: A schema may have only pre-release semvers (e.g. `1.0.0-rc1`) and no stable published version. Without `--version`, what should the default `/download` (no version path) return, and what should the CLI show?

**Decision**: **Trust whatever the marketplace returns as "latest" via its default `/download` endpoint.** Echo the resolved version (from the `x-schema-version` header the server already provides — see existing `marketplace.py:57`) so the user sees what they got. If the server refuses to resolve a default when only pre-releases exist (404 or a specific error body), surface that as a "version-not-found" class error with guidance to pass `--version`.

**Rationale**:

- Version selection policy belongs on the server, not in the CLI. The marketplace knows its own publishing model; the CLI only reports the decision.
- Keeps the CLI logic simple and avoids encoding semver-rules locally.
- The existing code already echoes `x-schema-version`, so no new client behaviour is needed for the happy path.

**Alternatives considered**:

- Client-side logic to enumerate versions and pick the highest stable one: rejected; requires a list endpoint we haven't confirmed exists, and duplicates server policy.

---

## R-6: Removal of `--load`

**Problem**: The existing command carried a `--load` convenience flag that pushed downloaded schemas into a running Infrahub instance in the same invocation. Does it stay?

**Decision**: **Remove `--load`**. The `download` command is now pure — it only writes files to disk.

**Rationale**:

- Single-responsibility: download and load are distinct concerns with different failure modes (network vs. schema validation). Combining them makes the error surface harder to reason about and couples a marketplace-client concern to a server-state mutation.
- The `infrahubctl schema load <path>` workflow already exists for loading schemas, so chaining `marketplace download` → `schema load` is a two-line script, not a feature gap.
- Reduces the CLI's dependency surface: no import of `initialize_client` or `yaml` at module load time, no coupling to the live Infrahub instance for marketplace operations.

**Migration note**: scripts that previously relied on `infrahubctl marketplace download <id> --load` should switch to:

```bash
infrahubctl marketplace download <id> -o ./schemas
infrahubctl schema load ./schemas
```

---

## Summary of resolved clarifications

All items in the spec's Assumptions section have been either confirmed or elevated into explicit rules here. No `NEEDS CLARIFICATION` markers remain.
