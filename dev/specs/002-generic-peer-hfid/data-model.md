# Data model: Reference generic peers by HFID in object files

No stored data changes. This feature changes how the object file loader reads values and passes them to the server.

## Peer reference (object file value)

A value under a relationship key that identifies an existing node. The accepted forms are:

| Form | Example | New |
|------|---------|-----|
| ID string | `"1797...-uuid"` | no |
| HFID string (one part) | `"Gi0/0/3"` | no |
| HFID list | `[router1, Gi0/0/3]` | no |
| Kind plus HFID mapping | `{kind: InterfacesPhysicalInterface, hfid: [router1, Gi0/0/3]}` | yes |

- A relationship of cardinality one takes one reference.
- A relationship of cardinality many takes a list of references, and the forms can be mixed in the list.
- A mapping with `data` remains a nested object, not a reference.

### Validation rules (schema only, at validation time)

These rules apply to a kind plus HFID mapping:

- **V1**: `kind` equals the relationship's peer kind, or appears in the peer generic's `used_by`.
- **V2**: the schema of `kind` defines `human_friendly_id`.
- **V3**: `hfid` is a string or a list of strings. A string becomes a one-part list. The list has as many parts as `kind`'s `human_friendly_id`.
- **V4**: the mapping has no keys other than `kind` and `hfid`.

### Resolution rules (at load time)

| Peer schema | Reference | Result |
|-------------|-----------|--------|
| Node, or generic with an HFID | string or list | Unchanged from today: normalize with the peer's HFID and send `hfid`. |
| Any | kind plus HFID mapping | Send `{"hfid": [...], "kind": kind}`. The server resolves it (research R1). |
| Generic without an HFID | string or list | Search the inheriting kinds (research R3). If exactly one node matches, send `{"hfid": [...], "kind": matched}`. If none or more than one matches, raise `ObjectValidationError`. |
| Any | ID string | Unchanged: send `id`. |

## RelationshipInfo (internal, `infrahub_sdk/spec/object.py`)

- `format`: `ONE_REF` also covers the kind plus HFID mapping. `MANY_REF` also covers lists that contain such mappings.
- New read-only value: whether the peer is a generic without an HFID. It is computed from the peer schema that `get_relationship_info` already fetches.
