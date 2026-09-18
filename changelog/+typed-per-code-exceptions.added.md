Every code in Infrahub's error catalogue now has an exception class of its own, importable from `infrahub_sdk.exceptions`, carrying the failure's payload as directly typed attributes. Identifying a specific failure no longer means matching words in a message:

```python
from infrahub_sdk.exceptions import ApiError, UniquenessViolationError

try:
    await node.save()
except UniquenessViolationError as exc:
    print(exc.node_kind, exc.fields)   # "TestPerson", ["name"]
except ApiError as exc:
    print("some other failure:", exc.code)
```

The new classes are `AttributeConstraintViolationError`, `AttributeInvalidTypeError`, `AttributeRequiredError`, `BranchAlreadyMergedError`, `BranchNeedsRebaseError`, `MergeInProgressError`, `MergeRecoveryRequiredError`, `UndefinedError`, and `UniquenessViolationError`. Each is typed exactly as the catalogue declares the payload, so a required field is never optional and needs no guard. They all descend from `GraphQLError`, so no `except` clause stops catching what it catches today.

`AUTHENTICATION_REQUIRED`, `TOKEN_EXPIRED`, and `PERMISSION_DENIED` deliberately have no class of their own: each of them reaches the SDK on two transports, and which generic class it raises follows the transport the SDK observed rather than the status the code declares. Catch `ApiError` and test `exc.code` to handle one of the three whichever way it arrived.

A server predating a code, or one whose payload does not match what the catalogue declares for it, still raises the generic class for the transport with `exc.code` readable, so an SDK of any version keeps working against a server of any version.

`docs/python-sdk/topics/error_handling` covers the hierarchy, the attributes readable on a caught error, and the cross-version guarantees.
