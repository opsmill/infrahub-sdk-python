`query` and `variables` are now readable on every `ApiError`, not only on the GraphQL branch. Reading either off an `AuthenticationError` previously raised `AttributeError`:

```python
try:
    await client.execute_graphql(query=query)
except ApiError as exc:
    log.error("request failed", code=exc.code, query=exc.query)   # no longer raises on a 401
```

That clause is the one the SDK recommends for the three authentication codes, since each of them can arrive either on a real 401 or 403 or inside a GraphQL `errors` array, so it is exactly where the attributes had to exist. They join `code`, `http_status`, `extensions` and `errors`, which were already declared there for the same reason.

`None` means the failed request was not recorded on the exception rather than that there was no query: an authentication failure is observed at the transport, which has neither to hand. Nothing that reads these attributes today changes - `GraphQLError` still populates both from the request it was raised for.
