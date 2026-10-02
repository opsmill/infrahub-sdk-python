`NodeNotFoundError`, `BranchNotFoundError`, and `SchemaNotFoundError` now descend from `GraphQLError`, so that one class covers a lookup miss however it arose: reported by the server, decided by the SDK, or turned from a REST 404.

An `except GraphQLError` clause therefore also catches lookup misses that involved no GraphQL request at all. Code that relied on those escaping such a clause should catch the specific class ahead of it, as an ordered `except` ladder already must. Each class keeps its name, its constructor, and the message it produces when no server reported the failure, and `errors`, `query`, and `variables` are now readable on every one of them rather than missing on a client-side raise.

`NodeInvalidError` inherits the re-rooting but not the adopted code: it means a node of the wrong kind rather than a lookup miss, so `NodeInvalidError.CODE` is `None` where `NodeNotFoundError.CODE` is `NODE_NOT_FOUND`.
