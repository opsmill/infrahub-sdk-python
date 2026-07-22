**Breaking:** The hand-maintained schema models in `infrahub_sdk.schema` are now backed by the generated write/read contract (`infrahub_sdk.schema.generated`). Public names, import paths, and behavior methods are unchanged, but a few defaults and constraints now match the server contract:

- `AttributeKind.STRING` has been removed. It was deprecated and `kind="String"` was already rejected server-side; use `AttributeKind.TEXT` instead.
- Write and read models drop unknown fields silently (`extra="ignore"`). A submitted field that is not part of the write contract — read-level, internal, or a typo — is dropped rather than rejected, and a read model tolerates additional fields returned by a newer server.
- Write-model defaults now match the server contract: relationship `min_count`/`max_count` default to `0` (was `None`), node `branch` defaults to `"aware"`, `generate_profile` defaults to `True`, and `generate_template` defaults to `False`. This changes the round-trip output of programmatically-built schemas.

Constructing `AttributeSchema(name=..., kind=AttributeKind.TEXT, ...)`, `NodeSchema`, `GenericSchema`, `RelationshipSchema`, `SchemaRoot`, and the read-side `*API` models continues to work unchanged.
