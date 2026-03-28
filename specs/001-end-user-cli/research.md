# Research: End-User CLI (`infrahub` command)

## R1: Entry Point & Packaging Strategy

**Decision**: Add `infrahub` as a second entry point in `[project.scripts]` within the
same package, pointing to a new app in `infrahub_sdk/ctl/enduser_cli.py`.

**Rationale**: The existing `infrahubctl` entry point lives in `infrahub_sdk/ctl/cli.py`
and uses the same `[ctl]` optional dependency group (typer, rich, click, pyyaml). The
end-user CLI needs identical dependencies. A separate package would duplicate
configuration, authentication, and client initialization code. A second entry point in
the same package reuses all existing infrastructure.

**Alternatives considered**:

- Separate Python package: rejected — duplicates config/client code, complicates releases
- Subcommand of `infrahubctl`: rejected — user explicitly wants separate `infrahub`
  command with end-user focus distinct from developer tooling

## R2: CLI Framework & Async Pattern

**Decision**: Use `AsyncTyper` (existing wrapper at `infrahub_sdk/async_typer.py`) with
Rich console output, matching the `infrahubctl` patterns exactly.

**Rationale**: The project already has a proven async CLI pattern. AsyncTyper wraps
`asyncio.run()` around async command functions. All existing utilities (`catch_exception`,
`initialize_client`, `CONFIG_PARAM`) work with this pattern.

**Alternatives considered**:

- Click directly: rejected — less ergonomic, would diverge from existing patterns
- Sync-only CLI: rejected — SDK client methods are async-first

## R3: Query Implementation

**Decision**: Use `client.all()` for list queries and `client.get()` for single-object
detail view. Filters pass through as `**kwargs` to `client.filters()`.

**Rationale**: `client.all()` wraps `client.filters()` internally and supports
`offset`, `limit`, `prefetch_relationships`, `include`, `exclude`, and `order`
parameters. Filter syntax is `attribute__value="x"` or `relationship__id="uuid"`.
Pagination is handled automatically with `client.pagination_size`.

**Key findings**:

- `node.display_label` provides the human-readable name for table display
- `node.<attr>.value` accesses attribute values
- `schema.attribute_names` and `schema.relationship_names` enumerate fields
- `schema.display_labels` identifies which attributes form the display label

## R4: Object YAML Round-Trip Format

**Decision**: Reuse the existing `InfrahubObjectFileData` model from
`infrahub_sdk/spec/object.py` for file input. For YAML output, build the reverse:
serialize query results into the same `apiVersion: infrahub.app/v1` / `kind: Object`
structure.

**Rationale**: The spec object format is already defined with Pydantic models. Input
parsing uses `ObjectFile.load_from_disk()` → `InfrahubObjectFileData.process()`. The
reverse direction needs a serializer that walks node attributes and relationships to
produce the same dict structure.

**Key classes**:

- `InfrahubObjectFileData` — spec model with `kind`, `parameters`, `data` fields
- `ObjectFile` — file wrapper with `validate_content()` and `process()` methods
- Relationship formats: `ONE_REF`, `MANY_REF`, `ONE_OBJ`, `MANY_OBJ_DICT_LIST`

## R5: Schema Discovery

**Decision**: Use `client.schema.all(branch=branch)` for listing kinds and
`client.schema.get(kind=kind, branch=branch)` for kind details.

**Rationale**: Schema API returns `NodeSchemaAPI` / `GenericSchemaAPI` objects with
`attribute_names`, `relationship_names`, `mandatory_input_names`, `display_labels`,
`human_friendly_id`, `namespace`, `label`, and `description` properties.

## R6: Create/Update/Delete Implementation

**Decision**: Use existing SDK CRUD methods:

- Create: `client.create(kind=kind, data=data)` → `node.save(allow_upsert=True)`
- Update: `client.get(kind=kind, id=identifier)` → modify attrs → `node.save()`
- Delete: `client.get(kind=kind, id=identifier)` → `node.delete()`

**Rationale**: These are the standard SDK patterns used by `infrahubctl` commands.
The `--set` flag maps directly to the `data` dict passed to `client.create()` or
applied to node attributes before `node.save()`.

**Key detail**: Identifier resolution accepts both UUID and HFID (human-friendly ID)
via the `id` parameter of `client.get()`.

## R7: Configuration Reuse

**Decision**: Reuse `infrahub_sdk/ctl/config.py` and `CONFIG_PARAM` from
`infrahub_sdk/ctl/parameters.py` directly.

**Rationale**: The `Settings` class reads from `infrahubctl.toml` (or
`INFRAHUBCTL_CONFIG` env var) with `server_address`, `api_token`, and
`default_branch`. No new configuration mechanism needed.

## R8: Output Formatting

**Decision**: Implement four output formatters: table (Rich), JSON, CSV, YAML.
Auto-detect: table when stdout is a TTY, JSON when piped.

**Rationale**: Rich is already a dependency. JSON uses stdlib `json`. CSV uses stdlib
`csv`. YAML uses `pyyaml` (already in `[ctl]` deps). The auto-detect pattern
(`sys.stdout.isatty()`) is standard CLI practice.
