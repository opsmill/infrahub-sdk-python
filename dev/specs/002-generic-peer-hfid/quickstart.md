# Quickstart: validate references to generic peers

## Prerequisites

```bash
uv sync --all-groups --all-extras
```

## 1. Unit tests (no server)

```bash
uv run pytest tests/unit/sdk/spec/test_object.py -k "generic" -v
```

Expected results:

- A reference with `kind` and `hfid` to a generic peer is classified as a reference. The data sent for creation is `{"hfid": [...], "kind": "<kind>"}`.
- With one matching node returned by the mocked API, a list HFID without `kind` is rewritten to include that kind.
- With zero or two mocked matches, `create_node` raises `ObjectValidationError`. The message names the candidate kinds.
- A kind that is not in `used_by`, a kind without an HFID, or a wrong number of HFID parts produces an error from `validate_format`.
- The existing tests in the file still pass.

## 2. Integration test (testcontainers)

```bash
uv run pytest tests/integration/test_spec_object.py -k "generic" -v
```

The test loads a schema with the following parts:

- A generic `TestingSupportsSubintf` without an HFID.
- Two kinds that inherit from it and use the HFID `[device, name]`.
- A `TestingSubInterface` with `parent_interface` pointing to the generic.

The test then loads:

1. Sub-interfaces that reference both kinds with `kind` and `hfid`. Expected result: each `parent_interface` is linked to the expected node.
2. A sub-interface that references `[router1, Gi0/0/3]` without `kind`. Expected result: linked to the physical interface.
3. The same reference after creating a port-channel named `Gi0/0/3` on `router1`. Expected result: the load fails with the ambiguity error.

## 3. Manual check with the example from the request

Against an Infrahub instance loaded with `schemas/interfaces/interfaces.yml`, without the Option 1 or Option 2 schema changes:

```bash
uv run infrahubctl object validate objects/50_interfaces/06_tunnel_interfaces.yml
uv run infrahubctl object load objects/50_interfaces/
```

Expected result: both commands succeed, and `Tunnel0.source_interface` is `router1 / Gi0/0/3`.

## 4. Lint and docs

```bash
uv run invoke format lint-code
uv run invoke lint-docs
```
