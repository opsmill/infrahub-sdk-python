`infrahubctl schema export` now asks Infrahub to build the export, so it needs an Infrahub server with the schema export endpoint (Infrahub 1.13.0 or later). With the default `BRIEF` mode, the files it writes differ from the files earlier versions wrote:

- `branch` on an attribute or relationship is written when it differs from the value Infrahub derives from the node or the peer.
- Values that Infrahub derives when it loads the schema, such as a `label` taken from the name, are left out.
- When an attribute has `unique: true`, the `human_friendly_id` and `uniqueness_constraints` that Infrahub derives from it are left out, and `unique` is written.
- The relationship `identifier`, `cardinality` and `optional`, and the attribute `read_only` and `choices`, are written when they differ from their default value.
- `IpamNamespace` is no longer written.
- The `object_template` relationship that Infrahub generates is no longer written.
- On a `Text` or `TextArea` attribute, `regex`, `min_length` and `max_length` are written under `parameters`. On a `List` attribute, `regex` is written under `parameters`, and `min_length` and `max_length` stay at the top level. On an attribute of any other kind, these settings stay at the top level.
- NumberPool `start_range` and `end_range` are written as one entry of `ranges`.
- Each file has an `infrahub_version` field with the version of the Infrahub server that built it.
