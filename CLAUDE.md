# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The **Infrahub Python SDK** (`infrahub-sdk`) is the official Python client library for interacting with [Infrahub](https://infrahub.app/), a data platform for infrastructure management. The SDK provides:

- Async and sync client implementations for the Infrahub API
- A CLI tool (`infrahubctl`) for managing Infrahub resources
- A pytest plugin for testing Infrahub integrations
- Support for checks, transforms, and generators

**Current Version**: 1.15.1
**Python Support**: 3.9 - 3.13

## Development Commands

### Essential Commands

```bash
# Install dependencies (full development environment)
poetry install --with dev --all-extras

# Format code
poetry run invoke format

# Run all linters (ruff + mypy + yamllint + markdownlint + vale)
poetry run invoke lint

# Run unit tests with coverage
poetry run pytest --cov infrahub_sdk tests/unit/

# Run integration tests (requires Docker/testcontainers)
poetry run pytest tests/integration/

# Generate documentation
poetry run invoke docs

# Validate generated documentation is committed
poetry run invoke docs-validate
```

### Testing Specific Components

```bash
# Run tests for specific modules
poetry run pytest tests/unit/sdk/test_client.py
poetry run pytest tests/unit/sdk/test_node.py
poetry run pytest tests/unit/ctl/

# Run with verbose output
poetry run pytest -v tests/unit/

# Run with parallel execution
poetry run pytest -n 4 tests/unit/
```

### Individual Linting Commands

```bash
# Run specific linters
poetry run invoke lint-ruff      # Python linting with ruff
poetry run invoke lint-mypy      # Type checking
poetry run invoke lint-yaml      # YAML validation
poetry run invoke lint-docs      # markdownlint + vale
```

## Architecture Overview

### Core Client Architecture

- **Dual Client Pattern**: `InfrahubClient` (async) and `InfrahubClientSync` (sync) provide identical interfaces
- **Configuration**: Pydantic-based `Config` class with `INFRAHUB_` environment variable support
- **Transport**: HTTPX-based with proxy support (single proxy or HTTP/HTTPS mounts)
- **Authentication**: API tokens or JWT with automatic refresh

### Complete Module Structure

```text
infrahub_sdk/
├── __init__.py             # Package entry point (exports InfrahubClient, InfrahubClientSync, Config)
├── client.py               # Main client implementations (~110KB, extensive API)
├── config.py               # Configuration management with Pydantic
│
├── node/                   # Node system (core data model)
│   ├── node.py             # InfrahubNode and InfrahubNodeSync
│   ├── attribute.py        # Node attributes
│   ├── relationship.py     # Relationship management
│   ├── related_node.py     # Related node handling
│   ├── parsers.py          # Data parsing utilities
│   ├── property.py         # Node properties
│   └── constants.py        # Node-related constants
│
├── schema/                 # Schema management
│   ├── main.py             # Schema API implementations
│   └── repository.py       # Schema repository handling
│
├── graphql/                # GraphQL utilities
│   ├── query.py            # Query building
│   ├── renderers.py        # Query rendering
│   ├── plugin.py           # GraphQL plugin support
│   └── utils.py            # GraphQL utilities
│
├── ctl/                    # CLI commands (infrahubctl)
│   ├── cli.py              # Main CLI entry point (Typer app)
│   ├── cli_commands.py     # Standalone commands
│   ├── branch.py           # Branch management commands
│   ├── schema.py           # Schema commands
│   ├── object.py           # Object CRUD commands
│   ├── check.py            # Check execution
│   ├── transform.py        # Transform execution
│   ├── generator.py        # Generator execution
│   ├── render.py           # Template rendering
│   ├── repository.py       # Repository commands
│   ├── menu.py             # Menu management
│   ├── validate.py         # Validation commands
│   ├── task.py             # Task management commands
│   ├── graphql.py          # GraphQL query execution
│   ├── exporter.py         # Data export functionality
│   └── importer.py         # Data import functionality
│
├── pytest_plugin/          # Custom pytest plugin for Infrahub testing
│   ├── plugin.py           # Plugin entry point
│   ├── loader.py           # Test loader
│   ├── models.py           # Test models
│   └── items/              # Test item types (check, transform, query)
│
├── spec/                   # Spec/Object file processing
│   ├── object.py           # InfrahubObjectFileData, ObjectFile classes
│   ├── models.py           # Spec models (InfrahubObjectParameters)
│   ├── menu.py             # Menu spec handling
│   ├── range_expansion.py  # Range expansion utilities
│   └── processors/         # Data processors (range expansion, etc.)
│
├── task/                   # Task management system
│   ├── manager.py          # InfrahubTaskManager, InfrahubTaskManagerSync
│   ├── models.py           # Task, TaskFilter models
│   ├── constants.py        # Task states
│   └── exceptions.py       # Task exceptions
│
├── template/               # Jinja2 template system
│   ├── __init__.py         # Jinja2Template class
│   ├── filters.py          # Built-in and netutils filters
│   ├── models.py           # Template models
│   └── exceptions.py       # Template exceptions
│
├── transfer/               # Data transfer utilities
│   ├── exporter/           # Export functionality
│   ├── importer/           # Import functionality
│   └── schema_sorter.py    # Schema dependency sorting
│
├── testing/                # Testing utilities
│
├── checks.py               # InfrahubCheck base class
├── transforms.py           # InfrahubTransform base class
├── generator.py            # InfrahubGenerator base class
├── batch.py                # Batch operations support
├── branch.py               # Branch management
├── store.py                # Node store management
├── query_groups.py         # Query group management
├── protocols.py            # Generated protocol classes
├── protocols_base.py       # Protocol base classes
├── protocols_generator/    # Protocol generation utilities
├── exceptions.py           # SDK exceptions
├── timestamp.py            # Timestamp utilities (uses 'whenever' library)
├── uuidt.py                # Time-based UUID utilities
├── yaml.py                 # YAML file handling (InfrahubFile, InfrahubFileKind)
└── utils.py                # General utilities
```

### Node System Design

- **Lazy Loading**: Nodes load attributes and relationships on demand
- **Batch Operations**: Support for bulk create/update/delete operations
- **Relationship Management**: Automatic handling of node relationships with add/remove/replace operations
- **Validation**: Built-in data validation with GraphQL query generation
- **Upsert Support**: `node.save(allow_upsert=True)` for idempotent operations

## Infrahub-Specific Patterns

### Checks Implementation

```python
# CRITICAL: Use validate() method, NOT check()
class MyCheck(InfrahubCheck):
    query = "my_graphql_query"  # Required: name of GraphQL query

    def validate(self, data: dict) -> None:  # Must be validate(), not check()
        # Use self.log_error() or self.log_info() for logging
        for item in data.get("items", []):
            if not item["valid"]:
                self.log_error(f"Invalid item: {item['name']}", object_id=item["id"])
```

### Transforms Implementation

```python
class MyTransform(InfrahubTransform):
    query = "my_graphql_query"  # Required: name of GraphQL query

    def transform(self, data: dict) -> Any:
        # Transform and return data
        return {"transformed": data}
```

### Generators Implementation

```python
class MyGenerator(InfrahubGenerator):
    async def generate(self, data: dict) -> None:
        # Use self.client to create/update nodes
        # Nodes are automatically tracked for deletion if no longer needed
        node = await self.client.create(kind="SomeKind", data={...})
        await node.save(allow_upsert=True)
```

### Async/Sync Pattern

All operations follow dual implementation pattern:

```python
# Async version (default)
client = InfrahubClient()
node = await client.get(kind="NetworkDevice", name__value="router1")
await node.save()

# Sync version
client = InfrahubClientSync()
node = client.get(kind="NetworkDevice", name__value="router1")
node.save()
```

### Task Manager

```python
# Async task management
task_manager = client.task
tasks = await task_manager.filter(filter=TaskFilter(states=["running"]))
task = await task_manager.wait_for_completion(id="task-id", timeout=120)

# Sync version
task_manager = client.task
tasks = task_manager.all(include_logs=True)
```

### Configuration Management

- Environment variables prefixed with `INFRAHUB_`
- Key variables:
  - `INFRAHUB_ADDRESS`: Server URL
  - `INFRAHUB_API_TOKEN`: API authentication token
  - `INFRAHUB_PROXY`: Single proxy URL
  - `INFRAHUB_PROXY_MOUNTS_HTTP` / `INFRAHUB_PROXY_MOUNTS_HTTPS`: Separate proxy configuration
- Mutual exclusivity validation between proxy configuration methods

## Testing Framework

### Custom Pytest Plugin

The repository includes a custom pytest plugin (`infrahub_sdk.pytest_plugin`) that provides:

- Fixtures for Infrahub clients and configuration
- Support for testing checks, transforms, and queries
- Integration with `infrahub-testcontainers` for Docker-based testing

Register via `pyproject.toml`:
```toml
[tool.poetry.plugins."pytest11"]
"pytest-infrahub" = "infrahub_sdk.pytest_plugin.plugin"
```

### Test Structure

```text
tests/
├── unit/                   # Unit tests (no external dependencies)
│   ├── sdk/                # SDK core tests
│   │   ├── test_client.py
│   │   ├── test_node.py
│   │   ├── graphql/
│   │   ├── checks/
│   │   └── spec/
│   ├── ctl/                # CLI tests
│   └── pytest_plugin/      # Plugin tests
├── integration/            # Integration tests (require Infrahub instance)
├── fixtures/               # Test fixtures and data
└── helpers/                # Test utilities
```

### Running Tests

```bash
# Unit tests with coverage
poetry run pytest --cov infrahub_sdk tests/unit/

# Specific test file
poetry run pytest tests/unit/sdk/test_client.py -v

# Integration tests (requires Docker)
poetry run pytest tests/integration/

# Parallel execution
poetry run pytest -n 4 tests/unit/
```

## CLI Architecture (`infrahubctl`)

The CLI is built with Typer and provides extensive functionality:

### Command Groups

- **branch**: Create, delete, merge, rebase, and diff branches
- **schema**: Load, check, and manage Infrahub schemas
- **object**: Create, list, and manage Infrahub objects
- **repository**: Manage external repositories
- **menu**: Manage navigation menus
- **task**: List and monitor background tasks

### Standalone Commands

- **check**: Execute validation checks against Infrahub data
- **transform**: Run Python or Jinja2 data transformations
- **generator**: Execute data generators
- **render**: Render Jinja2 templates
- **validate**: Validate local files (spec objects, menus)
- **run**: Execute GraphQL queries
- **version**: Display version information
- **shell**: Interactive Python shell with client
- **protocols**: Generate Python protocol classes from schema

CLI entry point: `infrahub_sdk/ctl/cli.py`

## Documentation System

### Structure

- **Docusaurus-based**: React/Node.js documentation system
- **Auto-generation**: CLI docs and config reference generated via invoke tasks
- **Location**: `docs/` directory

### Documentation Development

```bash
# Generate all documentation (CLI + SDK config + template reference)
poetry run invoke docs

# Generate specific docs
poetry run invoke generate-infrahubctl  # CLI documentation
poetry run invoke generate-sdk          # SDK configuration docs

# Start development server (requires Node.js)
cd docs && npm install && npm start

# Validate generated docs are committed
poetry run invoke docs-validate
```

## Development Tooling

### Code Quality

- **Ruff** (0.11.0): Comprehensive linting and formatting
  - Configured with `select = ["ALL"]` with specific ignores
  - Line length: 120 characters
- **mypy**: Type checking with strict configuration
  - `disallow_untyped_defs = true`
- **yamllint**: YAML file validation
- **markdownlint-cli2**: Documentation consistency
- **Vale** (3.7.1): Documentation style checking

### CI/CD Integration

GitHub Actions workflow (`.github/workflows/ci.yml`) runs:

1. Multi-version Python testing (3.9, 3.10, 3.11, 3.12, 3.13)
2. Linting pipeline (ruff, mypy, yamllint, markdownlint, actionlint, vale)
3. Documentation build and validation
4. Integration testing with Infrahub testcontainers
5. Coverage reporting to Codecov

## Key Configuration Files

- **pyproject.toml**: Poetry dependencies, tool configurations (ruff, mypy, pytest, towncrier)
- **tasks.py**: Invoke task definitions for development workflows
- **.github/workflows/ci.yml**: CI/CD pipeline
- **.markdownlint.yaml**: Markdown linting rules
- **.vale.ini**: Vale style configuration
- **.yamllint.yml**: YAML linting rules
- **codecov.yml**: Coverage configuration

## Dependencies

### Core Dependencies

- **pydantic** (>=2.0.0): Configuration and data validation
- **pydantic-settings** (>=2.0): Environment-based configuration
- **httpx**: Async/sync HTTP client with proxy support
- **graphql-core** (>=3.1,<3.3): GraphQL query building and parsing
- **ujson** (^5): Fast JSON serialization
- **dulwich** (^0.21.4): Git operations
- **whenever** (>=0.7.2,<0.8.0): Timestamp handling
- **netutils** (^1.0.0): Network utilities and Jinja2 filters

### Optional Dependencies (Extras)

```toml
[tool.poetry.extras]
ctl = ["Jinja2", "numpy", "pyarrow", "pyyaml", "rich", "tomli", "typer", "click", "copier", "ariadne-codegen"]
tests = ["Jinja2", "pytest", "pyyaml", "rich"]
all = [...]  # All optional dependencies
```

## Changelog Management

Uses **towncrier** for changelog generation:

```bash
# Create a changelog fragment
echo "Description of change" > changelog/+my-change.added.md

# Types: security, removed, deprecated, added, changed, fixed, housekeeping
```

## Common Patterns and Best Practices

### Creating Nodes

```python
# Create with data dict
node = await client.create(kind="InfraDevice", data={"name": {"value": "router1"}})
await node.save()

# Upsert pattern (idempotent)
await node.save(allow_upsert=True)
```

### Querying Nodes

```python
# Get single node
node = await client.get(kind="InfraDevice", name__value="router1")

# Get multiple nodes
nodes = await client.all(kind="InfraDevice")

# Filter with GraphQL
nodes = await client.filters(kind="InfraDevice", name__value="router%", partial_match=True)
```

### Working with Relationships

```python
# Add relationship
await node.related_nodes.add(other_node)

# Remove relationship
await node.related_nodes.remove(other_node)

# Replace all relationships
await node.related_nodes.update([node1, node2])
```

### Batch Operations

```python
batch = await client.create_batch()
batch.add(task=client.create, kind="InfraDevice", data={...})
batch.add(task=client.create, kind="InfraDevice", data={...})
async for result in batch.execute():
    print(result)
```

## Documentation Writing Guidelines

When writing or modifying MDX documentation files in this repository, follow these established patterns:

### Framework: Diataxis

All documentation follows the [Diataxis framework](https://diataxis.fr/):

- **Tutorials** (learning-oriented): Step-by-step learning experiences
- **How-to guides** (task-oriented): Problem-solving instructions
- **Explanation** (understanding-oriented): Clarification and discussion of topics
- **Reference** (information-oriented): Technical descriptions and specifications

### Tone and Style

- **Professional but approachable**: Use plain language with technical precision
- **Concise and direct**: Prefer short, active sentences with minimal fluff
- **Informative over promotional**: Focus on explaining how and why, not marketing
- **Consistent structure**: Follow predictable patterns across documents

### Code Examples

- Use proper language tags for all code blocks
- Include both async and sync examples where applicable
- Provide realistic examples that reflect real-world complexity
- Add validation steps to confirm success
