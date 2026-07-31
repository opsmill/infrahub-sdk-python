# Data Model: orjson migration

No new domain entities. This migration transforms serialization call sites. The "data model" here is the exhaustive call-site migration map — the source of truth for task generation.

## No new entities

The only data concept indirectly affected is the **query-group name**: an existing, persisted identifier partly derived from `dict_hash(params)`. Its structure and public type (`str`) are unchanged; only its value changes, and only for non-ASCII parameter values (see spec Edge Cases).

## Call-site migration map

Legend for transform: **D**=decode `.decode()` added · **OPT**=option flags · **EXC**=except-clause change · **FILE**=file-object rewrite · **COSMETIC**=4→2 indent width.

### Encode sites (`dumps` / `dump`)

| File:line | Current | Transform |
|---|---|---|
| `client.py:218` | `ujson.dumps(variables, indent=4)` (debug print) | `OPT_INDENT_2`, **D**, **COSMETIC** |
| `checks.py:112` | `print(ujson.dumps(log_message))` | **D** |
| `ctl/validate.py:107` | `ujson.dumps(response, indent=2, sort_keys=True)` | `OPT_INDENT_2 \| OPT_SORT_KEYS`, **D** |
| `ctl/cli_commands.py:355` | `ujson.dumps(result, indent=2, sort_keys=True)` | `OPT_INDENT_2 \| OPT_SORT_KEYS`, **D** |
| `ctl/telemetry.py:127` | `json.dumps(snapshots, indent=2)` → `write_text` | `OPT_INDENT_2`, **D** |
| `ctl/formatters/json.py:42,59` | `json.dumps(x, indent=2, default=str)` | `OPT_INDENT_2 \| OPT_PASSTHROUGH_DATETIME`, `default=str`, **D** |
| `graphql/multipart.py:46,60` | `ujson.dumps(operations)` (str for httpx) | **D**, `OPT_NON_STR_KEYS` |
| `graphql/renderers.py:54` | `json.dumps(value)` (string escaping) | **D** |
| `utils.py:253` | `ujson.dumps(dictionary, sort_keys=True).encode()` | `OPT_SORT_KEYS` (already bytes; drop `.encode()`) |
| `playback.py:52` | `str(json.dumps(payload)).encode("UTF-8")` | `orjson.dumps(payload)` (already bytes; drop wrappers) |
| `recorder.py:59` | `ujson.dump(data, fobj, indent=4, sort_keys=True)` | `OPT_INDENT_2 \| OPT_SORT_KEYS`, **FILE**, **COSMETIC** |
| `transfer/exporter/json.py:151,155,166` | `ujson.dumps(...)` → `write_text` | **D**, `OPT_NON_STR_KEYS` |
| `pytest_plugin/items/check.py:52` | `ujson.dumps(resp.json(), indent=4)` | `OPT_INDENT_2`, **D**, **COSMETIC** |
| `pytest_plugin/items/graphql_query.py:31` | same | `OPT_INDENT_2`, **D**, **COSMETIC** |
| `pytest_plugin/items/python_transform.py:54` | same | `OPT_INDENT_2`, **D**, **COSMETIC** |
| `pytest_plugin/items/jinja2_transform.py:63` | `... indent=4, sort_keys=True` | `OPT_INDENT_2 \| OPT_SORT_KEYS`, **D**, **COSMETIC** |
| `pytest_plugin/items/base.py:62,63` | `ujson.dumps(x, indent=4, sort_keys=True).splitlines()` | `OPT_INDENT_2 \| OPT_SORT_KEYS`, **D**, **COSMETIC** |

### Decode sites (`loads` / `load` / `response.json()`)

| File:line | Current | Transform |
|---|---|---|
| `utils.py:97` | `except json.decoder.JSONDecodeError` on `response.json()` | switch decode to `orjson.loads(response.content)`; **EXC** → `orjson.JSONDecodeError` |
| `schema/__init__.py:277` | `except json.decoder.JSONDecodeError` | same strategy; **EXC** |
| `ctl/parsers.py:27,28` | `json.loads(stripped)` + `except json.JSONDecodeError` | `orjson.loads`, **EXC** |
| `template/infrahub_filters.py:167,168` | `json.loads(value)` + `except (json.JSONDecodeError, TypeError)` | `orjson.loads`, **EXC** (keep `TypeError`) |
| `playback.py:57` | `ujson.load(fobj)` | `orjson.loads(fobj.read())`, **FILE** |
| `transfer/importer/json.py:67,150` | `ujson.loads(...)` | `orjson.loads(...)` |
| `pytest_plugin/models.py:57` | `ujson.loads(text)` | `orjson.loads(text)` |
| `pytest_plugin/items/{check,graphql_query,python_transform,jinja2_transform}.py` | `except ujson.JSONDecodeError` | **EXC** → matching orjson exception for the paired decode |

### Import + dependency changes

| File | Change |
|---|---|
| all 21 modules above | replace `import ujson` / `import json` with `import orjson` (remove both legacy imports) |
| `utils.py`, `playback.py` | remove the **dual** import (both `json` and `ujson`) |
| `pyproject.toml` | `- "ujson>=5"`, `+ "orjson>=3.10"`; dev: `- "types-ujson"` |
| `uv.lock` | refresh |

## Validation rules (from requirements)

- Zero `import ujson` / `import json` remain in `infrahub_sdk/` (FR-001).
- `indent=2` and CLI-formatter output byte-identical; datetime text form unchanged (FR-002).
- `dict_hash` unchanged for the 3 vectors + new non-ASCII vector pinned (FR-003).
- No bytes leak where str is expected (FR-004).
- Record→replay round-trip passes (FR-005).
- Malformed JSON still caught at every current site (FR-006).
- Manifest/lock reflect exactly the add/remove (FR-007).
- Int-keyed export payloads still serialize (FR-008).
