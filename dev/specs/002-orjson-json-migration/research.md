# Research: orjson migration

All findings below were verified empirically against orjson and the current codebase, not taken from documentation alone.

## Decision 1 — orjson as the single library; remove ujson AND stdlib json

**Decision**: orjson is the only JSON library in `infrahub_sdk/`. Remove `ujson` (runtime + `types-ujson`) and all stdlib `json` imports. Add `orjson>=3.10`.

**Rationale**: One library removes the dual-library decode-error hazard and the "which one do I use" ambiguity, and orjson (Rust/serde_json) is faster on the SDK's hot path. `>=3.10` guarantees wheels for all supported interpreters (3.10–3.14) and all options in use.

**Alternatives considered**:

- *Standardize on ujson first, orjson later*: two passes re-touching the same sites; rejected.
- *orjson + stdlib json for exceptions*: keeps two libraries and needs a written exception list; rejected once it was confirmed no pretty-print output is contractual.

## Decision 2 — Byte-parity of pretty-printed output

**Decision**: `indent=2` sites migrate to `OPT_INDENT_2` unchanged; `indent=4` human-facing sites accept a cosmetic 4→2 width shift.

**Rationale**: Verified `orjson.dumps(d, option=OPT_INDENT_2)` is byte-identical to `json.dumps(d, indent=2)` (same `\n`, same `": "`/`","` separators). All `indent=4` occurrences are debug prints, pytest failure/diff messages, or recorder fixture files read back by a whitespace-agnostic loader — none are compared programmatically.

**Alternatives considered**: Preserving 4-space width by keeping stdlib json at those sites — rejected; no contract to protect.

## Decision 3 — datetime rendering in CLI JSON

**Decision**: `ctl/formatters/json.py` uses `option=OPT_INDENT_2 | OPT_PASSTHROUGH_DATETIME` with `default=str`.

**Rationale**: orjson natively renders datetimes as RFC 3339 (`T` separator), which would change `infrahubctl` output. `OPT_PASSTHROUGH_DATETIME` routes datetimes back through `default=str`, producing `"2026-07-14 00:00:00"` — verified byte-identical to today's stdlib `default=str` output.

## Decision 4 — Decode-error handling / stdlib removal

**Decision**: Decode sites relying on httpx `response.json()` switch to `orjson.loads(response.content)`; pure `loads` sites swap library and their paired `except` together. All `except` clauses use `orjson.JSONDecodeError`.

**Rationale**: Verified `orjson.JSONDecodeError` is a subclass of both `json.JSONDecodeError` and `ValueError`, and that `except json.JSONDecodeError` catches an orjson decode failure. Decoding explicitly via orjson makes each decode+except pair internally consistent and lets stdlib `json` be removed entirely — directly resolving the #1165 hazard.

**Alternatives considered**: Catching `ValueError` (broader, orjson-only) — viable but less precise; keeping `import json` only for the `except` type — rejected (violates zero-stdlib-json).

## Decision 5 — dict_hash / query-group naming stability

**Decision**: `orjson.dumps(d, option=OPT_SORT_KEYS)`; accept non-ASCII divergence, pin with a test vector, note in release notes.

**Rationale**: Verified byte-identical output (hence identical MD5) to `ujson.dumps(d, sort_keys=True).encode()` for the three committed vectors and for int/float/nested inputs. Divergence occurs only for non-ASCII string values (orjson raw UTF-8 vs ujson escaped). `dict_hash` feeds `query_groups.py:68`, so a changed hash changes a persisted group name once on upgrade (old group orphaned). Judged low-incidence and acceptable.

## Decision 6 — Non-string dict keys

**Decision**: Add `OPT_NON_STR_KEYS` at arbitrary-data serialization sites (`transfer/exporter/json.py`, `graphql/multipart.py`).

**Rationale**: Verified orjson raises `TypeError("Dict key must be str")` for non-str keys unless the option is set; with it, keys coerce to strings (`{1:'a'}` → `{"1":"a"}`), matching ujson's prior silent behaviour and preventing a regression on previously-working payloads.

## Decision 7 — File-object I/O

**Decision**: Rewrite `recorder.py` (`ujson.dump(x, fobj, ...)` → `fobj.write(orjson.dumps(x, option=...).decode())`) and `playback.py` (`ujson.load(fobj)` → `orjson.loads(fobj.read())`).

**Rationale**: orjson exposes only `dumps`/`loads` on in-memory bytes; it has no `load`/`dump` file-handle API. A record-then-replay round-trip test confirms parity.
