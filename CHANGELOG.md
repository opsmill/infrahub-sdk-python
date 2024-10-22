# Infrahub SDK Changelog

This is the changelog for the Infrahub SDK.
All notable changes to this project will be documented in this file.

Issue tracking is located in [Github](https://github.com/opsmill/infrahub/issues).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project uses [*towncrier*](https://towncrier.readthedocs.io/) and the changes for the upcoming release can be found in <https://github.com/opsmill/infrahub/tree/develop/infrahub/python_sdk/changelog/>.

<!-- towncrier release notes start -->

## [0.14.1](https://github.com/opsmill/infrahub-sdk-python/tree/v0.14.1) - 2024-10-22

### Fixed

- Make `infrahubctl transform` command set up the InfrahubTransform class with an InfrahubClient instance ([#8](https://github.com/opsmill/infrahub-sdk-python/issues/8))
- Command `infrahubctl protocols` now supports every kind of schema attribute. ([#57](https://github.com/opsmill/infrahub-sdk-python/issues/57))

## [0.14.0](https://github.com/opsmill/infrahub-sdk-python/tree/v0.14.0) - 2024-10-04

### Removed

- Removed depreceted methods InfrahubClient.init and InfrahubClientSync.init ([#33](https://github.com/opsmill/infrahub-sdk-python/issues/33))

### Changed

- Query filters are not validated locally anymore, the validation will be done on the server side instead. ([#9](https://github.com/opsmill/infrahub-sdk-python/issues/9))
- Method client.get() can now return `None` instead of raising an exception when `raise_when_missing` is set to False

  ```python
  response = await clients.get(
      kind="CoreRepository", name__value="infrahub-demo", raise_when_missing=False
  )
  ``` ([#11](https://github.com/opsmill/infrahub-sdk-python/issues/11))

### Fixed

- prefix and address attribute filters are now available in the Python SDK ([#10](https://github.com/opsmill/infrahub-sdk-python/issues/10))
- Queries using isnull as a filter are now supported by the Python SDK ([#30](https://github.com/opsmill/infrahub-sdk-python/issues/30))
- `execute_graphql` method for InfrahubClient(Sync) now properly considers the `default_branch` setting ([#46](https://github.com/opsmill/infrahub-sdk-python/issues/46))

## [0.13.1.dev0](https://github.com/opsmill/infrahub-sdk-python/tree/v0.13.1.dev0) - 2024-09-24

### Added

- Allow id filters to be combined when executing a query ([#3](https://github.com/opsmill/infrahub-sdk-python/issues/3))

### Fixed

- Add ability to construct HFIDs from payload for upsert mutations ([#45](https://github.com/opsmill/infrahub-sdk-python/issues/45))
- Fix pytest plugin integration tests unable to run because we were not properly setting the api_token configuration setting for the SDK.
