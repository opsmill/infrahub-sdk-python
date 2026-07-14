# Quickstart: validating the orjson migration

Prerequisites: `uv sync --all-groups --all-extras` (installs orjson, removes ujson).

## 1. No legacy JSON library remains (FR-001 / SC-001)

```bash
# Must return nothing:
grep -rn "import ujson" infrahub_sdk/
grep -rn "^import json\|^\s*import json$" infrahub_sdk/
# Must show orjson only:
grep -rln "import orjson" infrahub_sdk/ | wc -l
```

Expected: first two commands print nothing; orjson import count matches the migrated module count.

## 2. Dependency manifest (FR-007)

```bash
grep -n "orjson\|ujson" pyproject.toml   # orjson>=3.10 present; no ujson / types-ujson
uv lock --check                          # lockfile consistent
```

## 3. Parameter hashing parity (FR-003)

```bash
uv run pytest tests/unit/sdk/test_utils.py::test_dict_hash -q
```

Expected: the three committed vectors still pass; the added non-ASCII vector asserts the new pinned value.

## 4. Full behavioral parity (FR-002, FR-004, FR-006, FR-008 / SC-002)

```bash
uv run pytest tests/unit/ -q            # includes CLI/formatter output, decode-error, export paths
uv run invoke lint-code                 # ty/mypy catch any bytes-where-str-expected leak
```

Expected: green. Type checking passing confirms no `bytes` leaked into `str` call sites.

## 5. Record → replay round-trip (FR-005)

Exercise the recorder/playback path (a targeted unit test, or a scripted record-then-replay) and confirm the replayed object equals the recorded input.

## 6. Integration suite (SC-002)

```bash
uv run pytest tests/integration/ -q
```

Expected: green, no behavioural change to queries, exports, generators, or checks.

## Done criteria

All of the above pass, and the only externally observable change is the one-time non-ASCII query-group-name shift (SC-004), captured in release notes.
