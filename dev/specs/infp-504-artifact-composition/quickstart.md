# Quickstart: Artifact Content Composition

**Feature**: INFP-504 | **Date**: 2026-03-20

## Jinja2 Templates

### Inline artifact content

Query artifacts via GraphQL and use the `artifact_content` filter to include their content:

```jinja2
{% set device = data.NetworkDevice.edges[0].node %}
hostname {{ device.hostname.value }}

{% for artifact in device.artifacts.edges %}
{% set content = artifact.node.storage_id.value | artifact_content %}
{% if content %}
{{ content }}
{% endif %}
{% endfor %}
```

### Inline file object content

```jinja2
{% set file_content = file_object.storage_id.value | file_object_content %}
{{ file_content }}
```

### Parse structured content

Chain `artifact_content` with `from_json` or `from_yaml` to access structured data:

```jinja2
{% set config = artifact.node.storage_id.value | artifact_content | from_json %}
interface {{ config.interface_name }}
  ip address {{ config.ip_address }}
```

```jinja2
{% set config = artifact.node.storage_id.value | artifact_content | from_yaml %}
{% for route in config.static_routes %}
ip route {{ route.prefix }} {{ route.next_hop }}
{% endfor %}
```

## Python Transforms

For Python transforms, use the SDK's object store directly:

```python
async def transform(self, data: dict, client: InfrahubClient) -> str:
    storage_id = (
        data["NetworkDevice"]["edges"][0]["node"]
        ["artifacts"]["edges"][0]["node"]
        ["storage_id"]["value"]
    )
    content = await client.object_store.get(identifier=storage_id)
    return content
```

## GraphQL Query Pattern

Reference artifacts in your query via the `artifacts` relationship:

```graphql
query StartupConfig($name: String!) {
  NetworkDevice(hostname__value: $name) {
    edges {
      node {
        hostname { value }
        artifacts {
          edges {
            node(name__value: "base_config") {
              id
              storage_id { value }
            }
          }
        }
      }
    }
  }
}
```

## Known Limitations

- **No ordering guarantee**: Artifacts may be generated in parallel. A composite artifact template may render before its dependencies are ready. Future event-driven pipeline work (INFP-227) will address this.
- **Worker context only**: `artifact_content` and `file_object_content` are only available on Prefect workers, not in computed attributes or local CLI.
- **Text content only**: `file_object_content` rejects binary file objects. `artifact_content` always returns text (artifacts are text-only).
