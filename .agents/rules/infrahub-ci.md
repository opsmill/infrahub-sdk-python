---
paths:
  - "infrahub_sdk/**"
---

# Run Infrahub's CI for changes that Infrahub uses

Infrahub installs this SDK from its `python_sdk` git submodule and calls it from its own code: the client, nodes and their relationships, `infrahubctl` and the pytest plugin. The CI of this repository runs the SDK unit tests, and integration tests against an Infrahub image started by `infrahub-testcontainers`. It does not run Infrahub's own tests with the changed SDK, so a change can pass here and still break Infrahub.

When a change edits code under `infrahub_sdk/` that Infrahub calls, suggest to the user, before the pull request is merged, that they run Infrahub's CI against the SDK branch. That means a draft pull request in `opsmill/infrahub` that changes only the `python_sdk` submodule commit and is marked as not to be merged. Ask before opening it: it is a pull request in another repository.

[Testing a change against Infrahub's CI](../../dev/guides/testing-against-infrahub-ci.md) lists the steps.
