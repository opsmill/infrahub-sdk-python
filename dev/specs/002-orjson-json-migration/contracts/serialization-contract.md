# Serialization behavioral contract

This library exposes no new public API. The contract this migration MUST preserve is behavioral — what existing callers and consumers observe.

## Preserved (MUST NOT change)

1. **`infrahub_sdk.utils.dict_hash(dict) -> str`** — signature and return type unchanged. Returns the same MD5 hex string as before for any input whose values are ASCII strings, integers, floats, booleans, `None`, or nested dicts/lists thereof.
   - Committed vectors that MUST still hold:
     - `{"a": 1, "b": 2}` → `608de49a4600dbb5b173492759792e4a`
     - `{"b": 2, "a": {"c": 1, "d": 2}}` → `4d8f1a3d03e0b487983383d0ff984d13`
     - `{}` → `99914b932bd37a50b983c5e7c90ae93b`

2. **CLI JSON output** (`infrahubctl` via `ctl/formatters/json.py`, `ctl/validate.py`, `ctl/cli_commands.py`) — same indentation (2 spaces) and same textual rendering of date/time values (`str()` form, space separator) as before.

3. **Decode-error handling** — every input that previously raised a caught JSON decode error still raises one that is caught at the same site (no `except` gap).

4. **Serialized payloads sent to the API** (`graphql/multipart.py`, `graphql/renderers.py`) — semantically equivalent JSON; multipart form fields remain `str`.

5. **Recorded fixtures** (`recorder.py` → `playback.py`) — a file written by the recorder is readable by playback and yields the same decoded object.

## Allowed to change (documented)

1. **`dict_hash` for non-ASCII values** — returns a different (but stable) hash than the previous library. Consequence: the persisted query-group name derived from such params changes once on upgrade. Pinned by a new test vector; noted in release notes.

2. **Human-facing pretty-print width** — debug prints and pytest failure/diff output change from 4-space to 2-space indentation. Not machine-consumed, not compared.

## Contract tests

- `tests/unit/sdk/test_utils.py::test_dict_hash` — retains the three vectors above; adds a non-ASCII vector asserting the new orjson value.
- Existing CLI/formatter unit tests — pass unchanged (parity check for items 2 & 4).
- A record→replay round-trip test — covers item 5.
- A decode-of-invalid-input test — covers item 3.
