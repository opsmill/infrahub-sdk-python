# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Essential Commands

```bash
# Install dependencies
uv sync --all-groups --all-extras

# Install specific groups
uv sync --group tests               # Testing dependencies only
uv sync --group lint                # Linting dependencies only
uv sync --extra ctl                 # CLI dependencies only
uv sync --all-groups --all-extras   # All optional dependencies

# Format code
uv run invoke format

# Run linting (ruff + mypy + yamllint + markdownlint)
uv run invoke lint

# Run unit tests with coverage
uv run pytest --cov infrahub_sdk tests/unit/

# Run integration tests
uv run pytest tests/integration/

# Generate documentation
uv run invoke docs

# Validate documentation
uv run invoke docs-validate
```

### Testing Specific Components

```bash
# Run tests for specific modules
uv run pytest tests/unit/test_client.py
uv run pytest tests/unit/test_node.py

# Run with verbose output
uv run pytest -v tests/unit/

# Run with parallel execution
uv run pytest -n 4 tests/unit/
```

## Architecture Overview

### Core Client Architecture

- **Dual Client Pattern**: `InfrahubClient` (async) and `InfrahubClientSync` (sync) provide identical interfaces
- **Configuration**: Pydantic-based `Config` class with environment variable support
- **Transport**: HTTPX-based with proxy support (single proxy or HTTP/HTTPS mounts)
- **Authentication**: API tokens or JWT with automatic refresh

### Key Modules Structure

```text
infrahub_sdk/
├── client.py           # Main client implementations
├── config.py          # Configuration management with Pydantic
├── node/              # Node system (core data model)
│   ├── node.py        # InfrahubNode and InfrahubNodeSync
│   ├── attribute.py   # Node attributes
│   └── relationship.py # Relationship management
├── ctl/               # CLI commands (infrahubctl)
├── pytest_plugin/    # Custom pytest plugin for Infrahub testing
└── protocols.py       # Generated protocol classes
```

### Node System Design

- **Lazy Loading**: Nodes load attributes and relationships on demand
- **Batch Operations**: Support for bulk create/update/delete operations
- **Relationship Management**: Automatic handling of node relationships with add/remove/replace operations
- **Validation**: Built-in data validation with GraphQL query generation

## Infrahub-Specific Patterns

### Checks Implementation

```python
# CRITICAL: Use validate() method, NOT check()
class MyCheck(InfrahubCheck):
    def validate(self, data):  # Must be validate(), not check()
        # validation logic
        pass
```

### Async/Sync Pattern

All operations follow dual implementation pattern:

```python
# Async version (default)
client = InfrahubClient()
node = await client.get(kind="NetworkDevice")
await node.save()

# Sync version
client = InfrahubClientSync()
node = client.get(kind="NetworkDevice")
node.save()
```

### Configuration Management

- Environment variables prefixed with `INFRAHUB_`
- Proxy configuration: `INFRAHUB_PROXY` (single) or `INFRAHUB_PROXY_MOUNTS_HTTP`/`INFRAHUB_PROXY_MOUNTS_HTTPS` (separate)
- Mutual exclusivity validation between proxy configuration methods

## Testing Framework

### Custom Pytest Plugin

The repository includes a custom pytest plugin (`infrahub_sdk.pytest_plugin`) that provides:

- Fixtures for Infrahub clients and configuration
- Support for testing checks, transforms, and queries
- Integration with infrahub-testcontainers for Docker-based testing

### Test Structure

- **Unit Tests**: `tests/unit/` - Test individual components in isolation
- **Integration Tests**: `tests/integration/` - Test against real Infrahub instances
- **Coverage Target**: Maintained through codecov integration

## CLI Architecture (`infrahubctl`)

The CLI is built with Typer and provides extensive functionality:

- **Schema Management**: Load, validate, and manage Infrahub schemas
- **Transformations**: Run Jinja2-based data transformations
- **Checks**: Execute validation checks against Infrahub data
- **Branch Operations**: Create, merge, and manage branches
- **Object Management**: CRUD operations on Infrahub objects

CLI commands are auto-documented and organized in `infrahub_sdk/ctl/`.

## Documentation System

### Structure

- **Docusaurus-based**: React/Node.js documentation system
- **Auto-generation**: CLI docs and config reference generated via invoke tasks
- **Multi-format**: Guides (task-oriented) and reference (API documentation)

### Documentation Development

```bash
# Generate all docs
uv run invoke docs

# Start development server (requires Node.js)
cd docs && npm start
```

## Development Tooling

### Code Quality

- **Ruff**: Comprehensive linting and formatting (0.14.5)
- **mypy**: Type checking with strict configuration
- **yamllint**: YAML file validation
- **markdownlint**: Documentation consistency
- **Vale**: Documentation style checking

### CI/CD Integration

GitHub Actions workflow runs:

1. Multi-version Python testing (3.10-3.13)
2. Comprehensive linting pipeline
3. Documentation generation and validation
4. Integration testing with Infrahub containers
5. Coverage reporting

## Key Configuration Files

- **pyproject.toml**: Poetry dependencies, tool configurations (ruff, mypy, pytest)
- **tasks.py**: Invoke task definitions for development workflows
- **.github/workflows/ci.yml**: Comprehensive CI/CD pipeline
- **docs/package.json**: Documentation build dependencies

## Dependencies Management

### Core Dependencies

- **pydantic** (>=2.0.0): Configuration and data validation
- **httpx**: Async/sync HTTP client with proxy support
- **graphql-core**: GraphQL query building and parsing
- **ujson**: Fast JSON serialization

### Optional Dependencies

- **ctl extra**: CLI functionality (typer, rich, jinja2)
- **tests extra**: Testing framework extensions
- **all extra**: Complete development environment

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

### Document Structure Patterns

#### How-to Guides (Task-oriented)

```markdown
---
title: How to [accomplish specific task]
---

# Brief introduction stating the problem/goal

## Prerequisites
- What the user needs before starting
- Required environment setup

## Step-by-step Instructions

### Step 1: [Action/Goal]
- Clear, actionable instructions
- Code snippets with proper language tags
- Screenshots/images for visual guidance
- Use Tabs for alternative methods (Web UI, GraphQL, Shell)

### Step 2: [Next Action]
- Continue structured approach

## Validation
- How to verify the solution worked
- Expected outputs and potential issues

## Related Resources
- Links to related guides and topics
```

#### Topics (Understanding-oriented)

```markdown
---
title: Understanding [concept or feature]
---

# Introduction to what this explanation covers

## Concepts & Definitions
- Key terms and how they fit into Infrahub

## Background & Context  
- Design decisions and rationale
- Technical constraints and considerations

## Architecture & Design
- Diagrams and component interactions
- Mental models and analogies

## Connections
- How this relates to other Infrahub concepts
- Integration points and relationships

## Further Reading
- Links to guides, references, and external resources
```

### Content Guidelines

#### For Guides

- Use conditional imperatives: "If you want X, do Y"
- Address users directly: "Configure...", "Create...", "Deploy..."
- Focus on practical tasks without digressing into explanations
- Maintain focus on the specific goal

#### For Topics

- Use discursive, reflective tone that invites understanding
- Include context, background, and rationale behind design decisions
- Make connections between concepts and existing knowledge
- Present alternative perspectives where appropriate

### Terminology and Quality

- **Define new terms** when first introduced
- **Use domain-relevant language** from user perspective (playbooks, branches, schemas, commits)
- **Be consistent** with Infrahub's data model and UI naming conventions
- **Validate accuracy** against latest Infrahub version
- **Follow markdown style** as defined in `.markdownlint.yaml` and Vale styles in `.vale/styles/`

### Code Examples and Formatting

- Use proper language tags for all code blocks
- Include both async and sync examples where applicable using Tabs component
- Provide realistic examples that reflect real-world complexity
- Add validation steps to confirm success
- Use callouts for warnings, tips, and important notes