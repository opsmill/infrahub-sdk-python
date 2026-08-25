`infrahub-sdk` now requires `pydantic>=2.0.3`, up from `>=2.0.0`.

If you pin `pydantic` to 2.0, 2.0.1 or 2.0.2, installing the SDK now fails while resolving dependencies. Those versions never actually worked: `import infrahub_sdk` raised a `SchemaError` on them, because their regex engine rejects a pattern used by the schema models. Pin `pydantic>=2.0.3` to resolve it.

`anyio`, `typing-extensions` and `packaging` are also now installed as direct requirements. The SDK has always imported them but relied on other packages to pull them in, so a minimal or heavily constrained environment could end up with the SDK installed and unusable. No action is needed, installs simply become reliable.
