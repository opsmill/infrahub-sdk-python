# CLI Design Principles

Guidelines for writing `infrahubctl` commands. These complement the structural rules in `cli-architecture.md`.

## Don't pre-validate what the server validates

The CLI's job is to translate user intent into API calls, not to reimplement server-side logic. When in doubt, just fire the request and let the server respond.

**Avoid**:

- Extra round-trips to check whether an object already exists before creating it
- Re-implementing uniqueness, permission, or referential-integrity checks client-side
- Heuristics that guess at server behavior (e.g., deriving identifiers from partial data to simulate a lookup)

**Why this matters**:

- Pre-validation is stale by the time the real call is made (TOCTOU).
- The server returns better errors than the CLI can construct.
- Every client-side check is a duplication that will drift from the server implementation.
- Extra calls slow the CLI down and make it feel laggy on high-latency links.

**Exception**: local-only validation that doesn't need the server is fine — malformed `--set` arguments, mutually exclusive flags, missing required options, etc. The test is: "could the server figure this out from the request alone?" If yes, let the server do it.

## Prefer HFID over `default_filter`

When resolving identifiers, HFID (human-friendly ID) is the long-term path. `default_filter` is deprecated and will be removed. New code should not depend on it, and existing code should be written so its removal is a straightforward change.

## Output phrasing should match semantics

Messages like `Created`, `Updated`, `Deleted` are promises about what actually happened. When using upsert semantics (`allow_upsert=True`), the CLI genuinely doesn't know whether the object was created or updated — so use neutral phrasing like `Saved` or `Applied`. Don't lie to the user for the sake of a cleaner message.

## Deduplicate redundant output

When printing an object's label and ID, check that they're actually different before printing both. Many objects have `display_label == id`, in which case repeating the value adds noise:

```python
if node.display_label and node.display_label != node.id:
    console.print(f"Saved {kind} '{node.display_label}' (ID: {node.id})")
else:
    console.print(f"Saved {kind} (ID: {node.id})")
```

## Raise errors directly, don't invoke dead calls

If the CLI has determined a call will fail (e.g., no lookup strategy matched), raise the appropriate exception directly rather than making a request you know will error out just to piggyback on the server's error message. The request is wasted network traffic and the roundabout path is harder to read.
