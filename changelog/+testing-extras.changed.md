Two extras now cover testing, replacing the `tests` extra.

`pip install 'infrahub-sdk[testing]'` installs pytest and enables the bundled `pytest-infrahub` plugin, which is what you want to test your own Transforms, Queries and Checks. `pip install 'infrahub-sdk[testcontainers]'` additionally provides `infrahub_sdk.testing.docker`, which starts a real Infrahub in containers so your tests can run against a live instance instead of mocked responses.

They are kept apart because the container tooling is a much heavier install. `[testing]` adds four packages on top of a plain install; `[testcontainers]` adds around sixty, among them Docker, FastAPI and Prefect client libraries. Previously you would have had to take all of it to get either.

The `tests` extra is gone. It stopped installing anything in 1.16.0 while the documentation carried on advertising it, so since then `pip install 'infrahub-sdk[tests]'` has warned about an unknown extra and installed only the base package. If you are coming from 1.15.2 or earlier, `[testing]` is the direct replacement for what `[tests]` gave you.
