`infrahubctl schema export` and `client.schema.export()` require Infrahub 1.13.0 or later, which serves the export. Against an earlier release they raise `VersionNotSupportedError` ("Schema export requires Infrahub 1.13.0 or later."). `client.schema.export()` now returns the `InfrahubSchemaWrite` document and takes a `mode` argument.

The client-side export is removed: `SchemaExport`, `NamespaceExport` and `schema_to_export_dict` are no longer exported from `infrahub_sdk.schema`, and the module `infrahub_sdk.schema.export`, with its `RESTRICTED_NAMESPACES`, no longer exists.
