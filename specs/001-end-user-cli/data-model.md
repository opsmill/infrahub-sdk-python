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
- For relationships, value is the display name or UUID of the target node

## Filter Parser

Parses `--filter key=value` arguments into kwargs for `client.filters()`.

**Input**: List of `"attribute__value=x"` strings from CLI
**Output**: `dict[str, Any]` passed as `**kwargs`

Validation rules:
- Key MUST follow the `attribute__value` or `relationship__id` pattern
- Invalid keys produce a validation error with available field names
