`numpy` and `mdxify` are no longer installed by the `ctl` and `all` extras.

Neither is used by the SDK. `numpy` was only ever needed because older `pyarrow` releases required it, and `pyarrow` still installs it itself on the versions that do. `mdxify` is a documentation tool used when building these docs, not at runtime.

If your project imports either package directly, add it to your own dependencies rather than relying on `infrahub-sdk[ctl]` to supply it.
