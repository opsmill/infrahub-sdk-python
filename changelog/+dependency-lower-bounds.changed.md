`infrahub-sdk` now requires `pydantic>=2.0.3`, up from `>=2.0.0`.

If you pin `pydantic` to 2.0, 2.0.1 or 2.0.2, installing the SDK now fails while resolving dependencies. Those versions never actually worked: `import infrahub_sdk` raised a `SchemaError` on them, because their regex engine rejects a pattern used by the schema models. Pin `pydantic>=2.0.3` to resolve it.

`anyio` and `typing-extensions` are now installed as direct requirements of the SDK itself. It has always imported them but relied on other packages to pull them in, so a minimal or heavily constrained environment could end up with the SDK installed and unusable. No action is needed, installs simply become reliable.

`packaging` is now a direct requirement of the `testcontainers` extra, which is where the `infrahub_sdk.testing.docker` helper that imports it lives. A plain `pip install infrahub-sdk` does not install it.
