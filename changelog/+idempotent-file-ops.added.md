Added SHA-1 idempotency primitives for `CoreFileObject` nodes:

- `InfrahubNode.matches_local_checksum(source)` / sync variant — compare a local `bytes | Path | BinaryIO` source against the node's server-stored checksum without invoking a transfer.
- `InfrahubNode.upload_if_changed(source, name=None)` / sync variant — stage + save only when the local source differs from the server, returning an `UploadResult(uploaded, checksum)` dataclass.
- `download_file(..., skip_if_unchanged=True)` — short-circuit the download when `dest` already exists on disk with a matching SHA-1. Returns `0` bytes written when skipped.

A shared `sha1_of_source` helper (streaming, 64 KiB chunks) centralises the hashing convention in `infrahub_sdk.file_handler`.
