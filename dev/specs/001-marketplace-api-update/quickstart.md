# Quickstart: Marketplace Download Command

End-to-end smoke test for the updated `infrahubctl marketplace download` command. These steps exercise each acceptance scenario in `spec.md` and should be green before merging.

## Prerequisites

```bash
uv sync --all-groups --all-extras
```

## Unit tests (fast loop)

```bash
uv run pytest tests/unit/ctl/test_marketplace_app.py -v
```

All existing tests must stay green, and new tests MUST be added to cover:

- Auto-detection when identifier is a schema (no `--collection` passed).
- Auto-detection when identifier is a collection (no `--collection` passed).
- Auto-detection when both endpoints return 200 — resolved as schema, type printed in output.
- Auto-detection when both endpoints return 404 — error class "not found".
- `--version` with an unpublished version — error class "version not found".
- 5xx on either probe endpoint — error class "network".
- Invalid identifier (no slash) — error class "invalid input" — caught before any network call.

## Manual verification against the public marketplace

```bash
# Scenario 1: download a schema by auto-detection
uv run infrahubctl marketplace download acme/network-base
ls schemas/

# Scenario 2: download a collection by auto-detection
uv run infrahubctl marketplace download acme/starter-pack
ls schemas/

# Scenario 3: pin a specific schema version
uv run infrahubctl marketplace download acme/network-base --version 0.9.0
grep '^version:' schemas/network-base.yml

# Scenario 4: custom output directory
uv run infrahubctl marketplace download acme/network-base --output-dir ./tmp/market-test
ls ./tmp/market-test

# Scenario 5: explicit --collection still works (override path)
uv run infrahubctl marketplace download acme/starter-pack --collection

# Scenario 6: version on a collection emits a warning, proceeds
uv run infrahubctl marketplace download acme/starter-pack --version 1.0.0
# Expect: "Warning: --version is ignored when downloading a collection." followed by success output.
```

## Manual verification against a local/staging marketplace

```bash
uv run infrahubctl marketplace download acme/test \
  --marketplace-url http://localhost:8000 \
  --output-dir ./tmp/local-market
```

This must exercise the same auto-detection behaviour against the overridden host.

## Expected success output shape

For a schema:

```text
Downloaded schema acme/network-base v1.2.0 -> schemas/network-base.yml
```

For a collection:

```text
Downloaded acme/network-base v1.0.0 -> schemas/starter-pack/network-base.yml
Downloaded acme/dcim v2.1.0 -> schemas/starter-pack/dcim.yml

Collection acme/starter-pack: 2/2 schemas downloaded
```

The CLI MUST announce the resolved item type (schema vs. collection) explicitly so the user can detect an unintended match in a collision case.

## Expected error output shapes

```text
# Not found
No schema or collection named 'acme/missing' found on marketplace.infrahub.app

# Version not found
Schema 'acme/network-base' has no published version '9.9.9'. Run without --version for the latest.

# Network
Could not reach marketplace at https://marketplace.infrahub.app: connection timed out. Check your connection or --marketplace-url.

# Invalid input
Invalid identifier 'acme-network-base'. Expected format: namespace/name
```

## Lint / format / type gates (must all pass)

```bash
uv run invoke format lint-code
```
