# Research: Reference generic peers by HFID in object files

## R1. Can the Infrahub server resolve a peer from a kind plus an HFID?

- **Decision**: Yes. The SDK sends `{"hfid": [...], "kind": "<NodeKind>"}` for the related node and relies on the server to resolve it.
- **Evidence** (Infrahub server, `~/dev/opsmill/infrahub` at `b77a9ce7cf`):
  - `backend/infrahub/graphql/types/attribute.py:20`: `RelatedNodeInput` has `kind = String(required=False)`, commented "Only used to resolve hfid of a related node on a generic relationship, see #4649".
  - `backend/infrahub/core/relationship/model.py:555-569`: when the peer has no ID but has an HFID, the server uses `data["kind"]` as the lookup kind if the relationship's peer is a generic. Otherwise it uses the relationship's peer kind.
  - `backend/infrahub/core/manager.py:761`: a lookup by HFID on a kind without `human_friendly_id` raises "Unable to lookup node by HFID, schema '<kind>' does not have a HFID defined." This is the error users hit today. The SDK sends the HFID without a kind, so the server looks it up on the generic.
- **SDK side**: `infrahub_sdk/node/related_node.py:87-101` already reads `hfid` and `kind` from a dict. `_generate_input_data` (`related_node.py:263-266`) already sends `kind` with `hfid`. No change is needed in the node layer.
- **Alternatives considered**: resolving the HFID to a node ID in the SDK before the mutation. This was rejected for User Story 1 because it adds one query per reference and repeats a lookup that the server already does.

## R2. How does the object file express "kind plus HFID"?

- **Decision**: a mapping with the keys `kind` and `hfid`, used in place of a plain HFID:

  ```yaml
  parent_interface:
    kind: InterfacesPhysicalInterface
    hfid: [router1, Gi0/0/3]
  ```

- **Rationale**:
  - The object file already uses `kind` to choose a node kind for a nested object of a generic peer (`kind` plus `data`).
  - `hfid` is the key the server and `RelatedNode` use.
  - A mapping with `hfid` and without `data` cannot be confused with a nested object, which always has `data`.
- **Alternatives considered**:
  - A prefixed string such as `"InterfacesPhysicalInterface:router1/Gi0/0/3"`. Rejected because names can contain `/` and `:`.
  - A separate top-level parameter that maps each relationship to a kind. Rejected because one relationship can have peers of several kinds in the same file, for example physical interfaces and port-channels.

## R3. How does a reference without a kind find its peer (User Story 2)?

- **Decision**: when the relationship's peer is a generic without `human_friendly_id`, and a reference is a string or list without a kind, the loader does the following at load time:
  1. Reads `used_by` from the generic schema. `GenericSchemaAPI.used_by` exists.
  2. Keeps the kinds that define `human_friendly_id` with the same number of parts as the reference.
  3. Queries each kept kind with `client.get(kind=..., hfid=..., branch=..., raise_when_missing=False)`.
  4. Links the peer if exactly one node matches. It stops with an `ObjectValidationError` if none or more than one node matches.
  5. Rewrites the reference to `{"hfid": ..., "kind": <matched kind>}`, so the mutation uses the path from R1.
- **Rationale**: this needs no server change and returns a clear error when the reference is ambiguous. Filtering by the number of parts reduces the number of queries.
- **Ceiling**: one query per candidate kind per reference. Known generics have fewer than 10 inheriting kinds. Add a per-load cache keyed by `(kind, hfid)` only if large files become slow.
- **Alternatives considered**:
  - Querying the generic with a filter on each HFID path. Rejected because the HFID paths belong to the inheriting kinds and are not available as filters on the generic.
  - Making the server do this lookup. Out of scope (see the spec assumptions).

## R4. Where do errors appear: validation or load?

- **Decision**:
  - `validate_object` (used by `infrahubctl object validate` and before each create) checks only what the schema can detect:
    - The named kind is the peer kind or is in the generic's `used_by`.
    - The named kind has `human_friendly_id`.
    - The HFID has the same number of parts as that kind's HFID.
  - A missing or ambiguous peer is reported in `create_node`, at load time.
- **Rationale**: a peer can be created earlier in the same load. A check for existence at validation time would reject valid files. This matches today's behavior, because `validate_related_nodes` returns no errors for `ONE_REF` and `MANY_REF`.
- **Error type**: `ObjectValidationError` (`infrahub_sdk/exceptions.py:168`), which already includes the position in the file. No new exception class is needed.

## R5. Synchronous client parity (constitution, Principle I)

- **Decision**: no synchronous version is added.
- **Rationale**: `infrahub_sdk/spec/object.py` takes only `InfrahubClient`, and nothing in the module uses `InfrahubClientSync`. This change modifies an existing asynchronous-only API and adds no method to either client.
