`ObjectFile.validate_content()` and `MenuFile.validate_content()`, their `spec` properties, and `InfrahubFile.validate_content()` now raise `infrahub_sdk.exceptions.ValidationError` when a file has one of these problems:

- a `kind` of the other file type, such as `kind: Menu` in an object file, which previously raised `ValueError`
- an unknown `kind` or `apiVersion`, or a missing `spec`, which previously raised a pydantic `ValidationError`
- a `spec` that does not match the object or menu format, which previously raised a pydantic `ValidationError` for menu files

The exception's `identifier` is the file location. `messages` holds one line per problem, in the form `path | reason, received value (type)`, for example `kind | Input should be 'Menu' or 'Object', received 'Schema' (enum)`. `infrahubctl object load`, `object validate`, `menu load` and `menu validate` therefore report these problems as a validation error for the file instead of stopping with a Python traceback. `infrahubctl` also no longer drops text in square brackets from these messages.

The SDK `ValidationError` does not subclass `ValueError` or the pydantic `ValidationError`. Code that catches either of those around these methods should catch `infrahub_sdk.exceptions.ValidationError` instead.
