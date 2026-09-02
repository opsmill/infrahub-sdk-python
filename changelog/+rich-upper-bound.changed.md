The `rich` requirement is now `>=12` with no upper bound, so the SDK can be installed alongside rich 14 and later.

The previous `<14` cap would otherwise have applied to every install rather than only those using the `infrahubctl` CLI, and would have conflicted with any project already on a newer rich. The SDK's unit tests pass against rich 13, 14 and 15.
