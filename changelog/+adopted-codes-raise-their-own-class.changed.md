A lookup miss the server reports - `NODE_NOT_FOUND`, `BRANCH_NOT_FOUND` or `SCHEMA_NOT_FOUND` - now raises `NodeNotFoundError`, `BranchNotFoundError` or `SchemaNotFoundError` built from the payload the server sent, where it previously raised a generic `GraphQLError`:

```python
try:
    await client.delete(kind="NetworkDevice", id=device_id)
except NodeNotFoundError:
    ...  # already gone
```

These three are the only catalogued classes the SDK also raises on its own, for a lookup that returned nothing and for the REST 404 behind a missing file. A ladder that handles one of them specifically will now see server-reported failures arrive there alongside the SDK's own, and `exc.code is not None` tells the two apart.
