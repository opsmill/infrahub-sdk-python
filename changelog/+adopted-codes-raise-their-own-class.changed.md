A failure the server reports as `NODE_NOT_FOUND`, `BRANCH_NOT_FOUND`, or `SCHEMA_NOT_FOUND` now raises `NodeNotFoundError`, `BranchNotFoundError`, or `SchemaNotFoundError` respectively, built from the payload the server sent, instead of a generic `GraphQLError`. One class therefore covers a lookup miss however it arose, and telling one apart from any other GraphQL failure no longer means matching words in a message:

```python
try:
    await client.delete(kind="NetworkDevice", id=device_id)
except NodeNotFoundError:
    ...  # already gone
```

Both classes are caught by `except GraphQLError`, so no clause stops catching what it catches today. A ladder that handles the specific class differently will now see server-reported failures arrive there as well as client-side ones; `exc.code is not None` distinguishes the two.
