# infrahub_sdk/pytest_plugin/AGENTS.md

Custom pytest plugin for testing Infrahub resources via YAML test files.

## YAML Test Format

```yaml
infrahub_tests:
  - resource: Check  # Check, GraphQLQuery, Jinja2Transform, PythonTransform
    resource_name: my_check
    tests:
      - name: test_success_case
        spec:
          kind: check-smoke  # See test kinds below
        input:
          data: {...}
        output:
          passed: true
```

## Test Kinds

| Resource | Smoke | Unit | Integration |
| -------- | ----- | ---- | ----------- |
| Check | `check-smoke` | `check-unit-process` | `check-integration` |
| GraphQL | `graphql-query-smoke` | - | `graphql-query-integration` |
| Jinja2 | `jinja2-transform-smoke` | `jinja2-transform-unit-render` | `jinja2-transform-integration` |
| Python | `python-transform-smoke` | `python-transform-unit-process` | `python-transform-integration` |

## Plugin Structure

```text
infrahub_sdk/pytest_plugin/
├── plugin.py      # Pytest hooks (pytest_collect_file, etc.)
├── loader.py      # YAML loading, ITEMS_MAPPING
├── models.py      # Pydantic schemas for test files
└── items/         # Test item implementations
    ├── base.py    # InfrahubItem base class
    └── check.py   # Check-specific items
```

## Adding New Test Item

```python
# 1. Create item class in items/
class MyCustomItem(InfrahubItem):
    def runtest(self):
        result = self.process(self.test.input)
        assert result == self.test.output

# 2. Register in loader.py
ITEMS_MAPPING = {
    "my-custom-test": MyCustomItem,
    ...
}
```

## Boundaries

✅ **Always**

- Register new items in `ITEMS_MAPPING`
- Inherit from `InfrahubItem` base class

🚫 **Never**

- Forget to add new test kinds to `ITEMS_MAPPING`
