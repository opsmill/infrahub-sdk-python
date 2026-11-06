# Implementation Plan: Reference generic peers by HFID in object files

**Branch**: `atg/strict-waves-stop` | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-generic-peer-hfid/spec.md`

## Summary

When a relationship's peer is a generic without an HFID, object files cannot reference an existing peer by HFID. The SDK sends the HFID without a kind, and the server looks it up on the generic, which has no HFID.

The server already resolves `{hfid, kind}` for generic peers (research R1), so the fix is in the object file loader only:

1. Accept a `{kind, hfid}` mapping as a reference, check it against the schema, and pass it through to the server unchanged.
2. When a reference gives only an HFID and the peer is a generic without an HFID, search the inheriting kinds for exactly one match and add its kind before the mutation.

## Technical Context

**Language/Version**: Python 3.10 to 3.13

**Primary Dependencies**: pydantic >= 2.0, httpx (no new dependencies)

**Storage**: N/A

**Testing**: pytest with `httpx_mock` for unit tests, and testcontainers for integration tests

**Target Platform**: library and `infrahubctl` CLI

**Project Type**: library

**Performance Goals**:

- References with a kind: no extra queries.
- References with an HFID alone to a generic peer: at most one query for each inheriting kind whose HFID has the same number of parts.

**Constraints**: object files that are valid today must load with the same result (FR-008)

**Scale/Scope**: one module (`infrahub_sdk/spec/object.py`), one documentation page, and tests

## Constitution Check

| Principle | Status | Note |
|-----------|--------|------|
| I. Async/sync parity | Pass (justified) | The object file API is asynchronous only today, and this change adds no client method (research R5). |
| II. Backward compatibility | Pass | The format change only adds a form. Existing forms take the same code path (FR-008). No public signature changes. |
| III. Layered architecture | Pass | All logic is in `infrahub_sdk/spec/object.py`, and the CLI is not changed. The local checks cover only what the server does not check before a write: validation runs without a mutation. |
| IV. Typed errors | Pass | Uses the existing `ObjectValidationError(Error)`, which carries the position in the file. |
| V. Test-first | Pass | Unit tests for each format and error, and one integration test that reproduces the reported failure. |
| VI. Lint | Pass | `uv run invoke format lint-code lint-docs`. |
| VII. Docs accuracy | Pass | `docs/docs/python-sdk/topics/object_file.mdx` is updated in the same pull request. A changelog fragment is added. |

Re-check after design: no change, and the Complexity Tracking table is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/002-generic-peer-hfid/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/object-file-reference.md
└── checklists/requirements.md
```

### Source code (repository root)

```text
infrahub_sdk/spec/object.py                 # all logic changes
docs/docs/python-sdk/topics/object_file.mdx # new reference form and generic example
changelog/<n>.added.md                      # towncrier fragment
tests/unit/sdk/spec/test_object.py          # format, validation, resolution (mocked)
tests/integration/test_spec_object.py       # end-to-end with a generic peer schema
```

## Design

All changes are in `infrahub_sdk/spec/object.py`.

1. **Classification** (`get_relationship_info`):
   - A dict with `hfid` and without `data` is a valid `ONE_REF`. Today line 152 rejects every dict without `data`.
   - The existing `"kind" in value` branch already sets `peer_kind`, so `peer_human_friendly_id` comes from the named kind.
   - For cardinality many, `validate_list_of_hfids` also accepts `{kind, hfid}` dicts.
   - Record whether the declared peer is a generic without an HFID, and its `used_by`.
2. **Validation** (`validate_related_nodes`, `ONE_REF` and `MANY_REF` branches): apply rules V1 to V4 from `data-model.md` to each `{kind, hfid}` item. These checks use only the schema.
3. **Normalization** (`create_node`): a `{kind, hfid}` item becomes `{"hfid": normalize(hfid), "kind": kind}`. `RelatedNode` already sends both (`related_node.py:263-266`).
4. **Resolution by HFID alone** (`create_node`): for a generic peer without an HFID, call a new private helper, `_resolve_generic_hfid(client, rel_info, hfid, position, branch)`, for each string or list item. The helper follows research R3 and returns `{"hfid", "kind"}` or raises `ObjectValidationError`.
5. Every other path stays as it is.

## Risks

- **Reference to a node created later in the same file**: User Story 2 needs the peer to exist at load time. Loads already run in file order, and the same limit applies to plain HFID references today.
- **Server behavior on other server versions**: `RelatedNodeInput.kind` dates from server issue #4649. The SDK's supported server range must include it. Confirm the minimum version against the compatibility matrix before release.
