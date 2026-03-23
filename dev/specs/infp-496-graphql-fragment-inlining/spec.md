# SDK Spec: GraphQL Fragment Inlining

**Jira**: INFP-496
**Created**: 2026-03-13
**Status**: Implemented
**Parent spec**: [infrahub/dev/specs/infp-496-graphql-fragment-inlining/spec.md](../../../../dev/specs/infp-496-graphql-fragment-inlining/spec.md)

## Scope

This spec covers the SDK-side responsibilities for the GraphQL Fragment Inlining feature (FR-015). The Infrahub server and backend integration are documented in the parent spec.

Per the architecture decision in the parent spec:

> Fragment parsing, resolution, and rendering is **SDK responsibility**, not server responsibility.

The SDK must provide:

1. **Config model extension** — `graphql_fragments` in `.infrahub.yml`
2. **Fragment renderer** — parse, resolve (transitively), and render queries
3. **CLI integration** — `infrahubctl` local workflows apply fragment rendering automatically

---

## Component Responsibilities

| Responsibility | SDK Module |
| --- | --- |
| `InfrahubRepositoryFragmentConfig` model | `infrahub_sdk/schema/repository.py` |
| `graphql_fragments` field on `InfrahubRepositoryConfig` | `infrahub_sdk/schema/repository.py` |
| Read fragment file content from disk | `InfrahubRepositoryFragmentConfig.load_fragments()` |
| Parse `.gql` fragment files into AST | `infrahub_sdk/graphql/query_renderer.py` |
| Build fragment name index (across all declared files) | `infrahub_sdk/graphql/query_renderer.py` |
| Detect duplicate fragment names across files | `infrahub_sdk/graphql/query_renderer.py` |
| Resolve transitive fragment dependencies | `infrahub_sdk/graphql/query_renderer.py` |
| Detect circular fragment dependencies | `infrahub_sdk/graphql/query_renderer.py` |
| Render self-contained query document | `infrahub_sdk/graphql/query_renderer.py` |
| High-level `render_query()` entry point (load + render) | `infrahub_sdk/graphql/query_renderer.py` |
| Typed error exceptions | `infrahub_sdk/exceptions.py` |
| Apply rendering in `infrahubctl` execution | `infrahub_sdk/ctl/utils.py` |
| Apply rendering in `infrahubctl` transform | `infrahub_sdk/ctl/cli_commands.py` |

---

## API Contract: Fragment Renderer

### CLI-facing entry point

```python
# infrahub_sdk/graphql/query_renderer.py

def render_query(name: str, config: InfrahubRepositoryConfig, relative_path: str = ".") -> str:
    """Return a self-contained GraphQL document for the named query, with fragment definitions inlined.

    Loads the query file and all declared fragment files from config, then delegates to
    render_query_with_fragments.

    Raises:
        ResourceNotDefinedError: Query name not found in config.
        FragmentFileNotFoundError: A declared fragment file path does not exist.
        DuplicateFragmentError: Same fragment name declared in multiple files.
        FragmentNotFoundError: Query references a fragment not found in any declared file.
        CircularFragmentError: Circular dependency detected among fragments.
    """
```

### Low-level entry point

```python
# infrahub_sdk/graphql/query_renderer.py

def render_query_with_fragments(query_str: str, fragment_files: list[str]) -> str:
    """Return a self-contained GraphQL document with required fragment definitions inlined.

    If the query contains no fragment spreads, query_str is returned unchanged.

    Raises:
        QuerySyntaxError: Query string or a fragment file contains invalid GraphQL syntax.
        DuplicateFragmentError: Same fragment name declared in multiple files.
        FragmentNotFoundError: Query references a fragment not found in any declared file.
        CircularFragmentError: Circular dependency detected among fragments.
    """
```

### Public helpers in `query_renderer.py`

```python
def build_fragment_index(fragment_files: list[str]) -> dict[str, FragmentDefinitionNode]:
    """Parse all fragment file contents and return a mapping from fragment name to its AST node."""

def collect_required_fragments(
    query_doc: DocumentNode,
    fragment_index: dict[str, FragmentDefinitionNode],
) -> list[str]:
    """Walk query_doc and collect all fragment names required (transitively).

    Returns a topologically ordered list of unique fragment names.
    """
```

### Error types (additions to `infrahub_sdk/exceptions.py`)

```python
class GraphQLQueryError(Error):
    """Base class for all errors raised during GraphQL query rendering."""


class QuerySyntaxError(GraphQLQueryError):
    def __init__(self, syntax_error: str) -> None: ...
    # message: f"GraphQL syntax error: {syntax_error}"


class FragmentNotFoundError(GraphQLQueryError):
    def __init__(self, fragment_name: str, query_file: str | None = None, message: str | None = None) -> None: ...
    # message: f"Fragment '{fragment_name}' not found." (or mentions query_file if provided)


class DuplicateFragmentError(GraphQLQueryError):
    def __init__(self, fragment_name: str, message: str | None = None) -> None: ...
    # message: f"Fragment '{fragment_name}' is defined more than once across declared fragment files."


class CircularFragmentError(GraphQLQueryError):
    def __init__(self, cycle: list[str], message: str | None = None) -> None: ...
    # message: f"Circular fragment dependency detected: {' -> '.join(cycle)}."


class FragmentFileNotFoundError(GraphQLQueryError):
    def __init__(self, file_path: str, message: str | None = None) -> None: ...
    # message: f"Fragment file '{file_path}' declared in graphql_fragments does not exist."
```

`GraphQLQueryError` is also handled in `handle_exception()` in `ctl/utils.py` so CLI commands print
a clean error message and exit instead of raising an unhandled exception.

---

## Config Model Extension

```python
# infrahub_sdk/schema/repository.py

class InfrahubRepositoryFragmentConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Logical name for this fragment file or directory")
    file_path: Path = Field(..., description="Path to a .gql file or directory of .gql files, relative to repo root")

    def load_fragments(self, relative_path: str = ".") -> list[str]:
        """Read and return raw content of all fragment files at file_path.

        If file_path is a .gql file, returns a single-element list.
        If file_path is a directory, returns one entry per .gql file found (sorted).
        Raises FragmentFileNotFoundError if file_path does not exist.
        """
        resolved = Path(f"{relative_path}/{self.file_path}")
        if not resolved.exists():
            raise FragmentFileNotFoundError(file_path=str(self.file_path))
        if resolved.is_dir():
            return [f.read_text(encoding="UTF-8") for f in sorted(resolved.glob("*.gql"))]
        return [resolved.read_text(encoding="UTF-8")]


class InfrahubRepositoryConfig(BaseModel):
    # ... existing fields ...
    graphql_fragments: list[InfrahubRepositoryFragmentConfig] = Field(
        default_factory=list, description="GraphQL fragment files"
    )
```

---

## infrahubctl Integration

Both CLI call sites use `render_query()` from `query_renderer.py`, which handles loading fragment
files from config and delegating to `render_query_with_fragments`.

### `execute_graphql_query()` in `ctl/utils.py`

```python
# Before
query_str = query_object.load_query()

# After
query_str = render_query(name=query, config=repository_config)
```

### `transform()` in `ctl/cli_commands.py`

```python
# Before
query_str = repository_config.get_query(name=transform.query).load_query()

# After
query_str = render_query(name=transform.query, config=repository_config)
```

---

## Testing Requirements

### Unit tests — `tests/unit/sdk/graphql/test_fragment_renderer.py` (imports from `query_renderer`)

- Render query with single direct fragment spread → correct output
- Render query with fragment spreads across two files → correct output
- Render query with transitive dependency (A → B across files) → correct output
- Render query with no fragment spreads → returned unchanged
- Same fragment spread used twice → fragment definition appears once in output
- Only required fragments included, not all from the file
- `FragmentNotFoundError` raised for unresolved spread
- `DuplicateFragmentError` raised for duplicate name across multiple content strings
- `DuplicateFragmentError` raised for duplicate name within the same content string
- `CircularFragmentError` raised for A→B→A cycle
- `QuerySyntaxError` raised for invalid GraphQL syntax in query or fragment file

### Unit tests — `tests/unit/sdk/graphql/test_query_renderer.py`

- `render_query()` loads query + fragments from config and returns rendered document
- `render_query()` with no `graphql_fragments` in config returns query unchanged

### Unit tests — `tests/unit/sdk/test_repository.py`

- `InfrahubRepositoryConfig` parses `graphql_fragments` YAML correctly
- `InfrahubRepositoryFragmentConfig.load_fragments()` with a file path returns a single-element list with the file content
- `InfrahubRepositoryFragmentConfig.load_fragments()` with a directory path returns one entry per `.gql` file found
- `load_fragments()` raises `FragmentFileNotFoundError` for a path that does not exist

### Integration / functional tests — caller-side

- See main repo plan for backend integration tests and E2E fixtures

---

## Constraints

- Fragment rendering uses only `graphql-core` (already a dependency). No new dependencies.
- All new public functions carry full type hints.
- Both async and sync `InfrahubClient` paths are unaffected — rendering is a pure string transformation with no I/O.
- Generated files (`protocols.py`) are not touched.
