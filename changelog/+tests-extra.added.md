`pip install 'infrahub-sdk[tests]'` now works. The `tests` extra is described in the installation guide but was never actually published, so the command warned that no such extra existed and installed nothing beyond the base package.

Install it if you use the `pytest-infrahub` plugin to test Transforms, Queries and Checks, or the `infrahub_sdk.testing` helpers. Previously you had to work out the missing requirements and declare them yourself.

Be aware that it is a large install, adding around 66 packages on top of the base SDK, among them Docker, FastAPI and Prefect client libraries. These come from the `infrahub_sdk.testing` helpers, which run Infrahub in containers. If you only need the `infrahubctl` CLI, install `infrahub-sdk[ctl]` instead. `infrahub-sdk[all]` now covers both `ctl` and `tests`, so it pulls in considerably more than it used to.
