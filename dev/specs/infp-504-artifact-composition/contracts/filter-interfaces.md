# Filter Interface Contracts

**Feature**: INFP-504 | **Date**: 2026-03-20

## Jinja2 Filter Signatures

### artifact_content

```python
async def artifact_content(storage_id: str) -> str
```

| Input | Output | Error |
| ----- | ------ | ----- |
| Valid storage_id string | Raw artifact content (text) | — |
| `None` | — | `JinjaFilterError("artifact_content", "storage_id is null", hint="...")` |
| `""` (empty) | — | `JinjaFilterError("artifact_content", "storage_id is empty", hint="...")` |
| Non-existent storage_id | — | `JinjaFilterError("artifact_content", "content not found: {id}")` |
| Permission denied (401/403) | — | `JinjaFilterError("artifact_content", "permission denied for storage_id: {id}")` |
| No client provided | — | `JinjaFilterError("artifact_content", "requires InfrahubClient", hint="pass client via Jinja2Template(client=...)")` |

**Validation**: Blocked in `CORE` context. Allowed in `WORKER` and `LOCAL` contexts.

### file_object_content

```python
async def file_object_content(storage_id: str) -> str
```

| Input | Output | Error |
| ----- | ------ | ----- |
| Valid storage_id (text file) | Raw file content (text) | — |
| Valid storage_id (binary file) | — | `JinjaFilterError("file_object_content", "binary content not supported for storage_id: {id}")` |
| `None` | — | `JinjaFilterError("file_object_content", "storage_id is null", hint="...")` |
| `""` (empty) | — | `JinjaFilterError("file_object_content", "storage_id is empty", hint="...")` |
| Non-existent storage_id | — | `JinjaFilterError("file_object_content", "content not found: {id}")` |
| Permission denied (401/403) | — | `JinjaFilterError("file_object_content", "permission denied for storage_id: {id}")` |
| No client provided | — | `JinjaFilterError("file_object_content", "requires InfrahubClient", hint="pass client via Jinja2Template(client=...)")` |

**Validation**: Blocked in `CORE` context. Allowed in `WORKER` and `LOCAL` contexts.

### file_object_content_by_id

```python
async def file_object_content_by_id(node_id: str) -> str
```

| Input | Output | Error |
| ----- | ------ | ----- |
| Valid node UUID (text file) | Raw file content (text) | — |
| Valid node UUID (binary file) | — | `JinjaFilterError("file_object_content_by_id", "binary content not supported...")` |
| `None` | — | `JinjaFilterError("file_object_content_by_id", "node_id is null", hint="...")` |
| `""` (empty) | — | `JinjaFilterError("file_object_content_by_id", "node_id is empty", hint="...")` |
| Permission denied (401/403) | — | `JinjaFilterError("file_object_content_by_id", "permission denied for node_id: {id}")` |
| No client provided | — | `JinjaFilterError("file_object_content_by_id", "requires InfrahubClient", hint="...")` |

**Validation**: Blocked in `CORE` context. Allowed in `WORKER` and `LOCAL` contexts.

### file_object_content_by_hfid

```python
async def file_object_content_by_hfid(hfid: str | list[str], kind: str = "") -> str
```

| Input | Output | Error |
| ----- | ------ | ----- |
| Valid HFID + kind (text file) | Raw file content (text) | — |
| Valid HFID + kind (binary file) | — | `JinjaFilterError("file_object_content_by_hfid", "binary content not supported...")` |
| `None` | — | `JinjaFilterError("file_object_content_by_hfid", "hfid is null", hint="...")` |
| Missing `kind` argument | — | `JinjaFilterError("file_object_content_by_hfid", "'kind' argument is required", hint="...")` |
| Permission denied (401/403) | — | `JinjaFilterError("file_object_content_by_hfid", "permission denied for hfid: {hfid}")` |
| No client provided | — | `JinjaFilterError("file_object_content_by_hfid", "requires InfrahubClient", hint="...")` |

**Validation**: Blocked in `CORE` context. Allowed in `WORKER` and `LOCAL` contexts.

### from_json

```python
def from_json(value: str) -> dict | list
```

| Input | Output | Error |
| ----- | ------ | ----- |
| Valid JSON string | Parsed dict or list | — |
| `""` (empty) | `{}` | — |
| Malformed JSON | — | `JinjaFilterError("from_json", "invalid JSON: {error_detail}")` |

**Validation**: Allowed in all contexts (`ALL`).

### from_yaml

```python
def from_yaml(value: str) -> dict | list
```

| Input | Output | Error |
| ----- | ------ | ----- |
| Valid YAML string | Parsed dict, list, or scalar | — |
| `""` (empty) | `{}` | — |
| Malformed YAML | — | `JinjaFilterError("from_yaml", "invalid YAML: {error_detail}")` |

**Validation**: Allowed in all contexts (`ALL`).

## ObjectStore API Contract

### GET /api/storage/object/{identifier} (existing)

Used by `artifact_content`. Returns plain text content.

### File object endpoints

All three endpoints return file content with the node's `file_type` as content-type. The SDK validates that the content-type is text-based.

| Endpoint | Used by | Identifier |
| -------- | ------- | ---------- |
| `GET /api/files/by-storage-id/{storage_id}` | `file_object_content` | storage_id |
| `GET /api/files/{node_id}` | `file_object_content_by_id` | node UUID |
| `GET /api/files/by-hfid/{kind}?hfid=...` | `file_object_content_by_hfid` | kind + HFID components |

**Accepted content-types** (text-based):

- `text/*`
- `application/json`
- `application/yaml`
- `application/x-yaml`

**Rejected**: All other content-types → `JinjaFilterError` with binary content message.

## Validation Contract

### validate() method

```python
def validate(
    self,
    restricted: bool = True,
    context: ExecutionContext | None = None,
) -> None
```

| Context | Trusted filters | Worker filters | Untrusted filters |
| ------- | :-: | :-: | :-: |
| `CORE` | allowed | blocked | blocked |
| `WORKER` | allowed | allowed | blocked |
| `LOCAL` | allowed | allowed | allowed |

**Backward compat**: `restricted=True` → `CORE`, `restricted=False` → `LOCAL`.
