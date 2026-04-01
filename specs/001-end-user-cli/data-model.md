# Data Model: End-User CLI

This feature does not introduce new persistent data entities. It operates on
Infrahub's existing data model (Kinds, Nodes, Attributes, Relationships) via
the SDK client.

The CLI introduces transient structures for formatting and serialization:

## Output Format Envelope

Used when serializing query results to YAML output format.

**Fields**:

- `apiVersion` (str): Always `"infrahub.app/v1"`
- `kind` (str): Always `"Object"`
- `spec.kind` (str): The Infrahub Kind being exported (e.g., `"InfraDevice"`)
- `spec.data` (list[dict]): Array of serialized node objects

Each node in `spec.data` contains:

- Attribute fields as `key: value` pairs
- Relationship fields as `key: display_name` (single) or
  `key: {data: [list]}` (many)

This structure matches the existing `InfrahubObjectFileData` model in
`infrahub_sdk/spec/object.py` and is round-trippable with `ObjectFile`.

## Set Flag Parser

Parses `--set key=value` arguments into a dict suitable for SDK calls.

**Input**: List of `"key=value"` strings from CLI
**Output**: `dict[str, str | list[str]]`

Validation rules:

- Key MUST exist as an attribute or relationship name in the target Kind's schema
- Value is a string; the SDK handles type coercion
- For relationships (cardinality ONE), value is the HFID or UUID of the target node (e.g., `--set site=DC1`)
- For relationships (cardinality MANY), value is a JSON array of HFID arrays (e.g., `--set tags=[["blue"], ["red"]]`). Each inner array is an HFID supporting multi-component keys (e.g., `[["Cisco", "NX-OS"]]`). The parser detects `[...]` and parses as JSON.

**Relationship resolution**: The CLI passes relationship values through to the
SDK as HFID references. The SDK/server is responsible for resolving HFIDs to
internal IDs. The CLI MUST NOT perform its own lookup round-trips.

**SDK dependencies**:

- [opsmill/infrahub-sdk-python#267](https://github.com/opsmill/infrahub-sdk-python/issues/267) — `rebuild_hfid_from_data()`: reconstruct HFID from flat user data based on schema definition
- [opsmill/infrahub-sdk-python#272](https://github.com/opsmill/infrahub-sdk-python/issues/272) — `node.update(data)`: update attributes and relationships from a dict (eliminates manual per-field mutation)

## Filter Parser

Parses `--filter key=value` arguments into kwargs for `client.filters()`.

**Input**: List of `"attribute__value=x"` strings from CLI
**Output**: `dict[str, Any]` passed as `**kwargs`

Validation rules:

- Key MUST follow the `attribute__value` or `relationship__id` pattern
- Invalid keys produce a validation error with available field names
