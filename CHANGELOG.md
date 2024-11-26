# Infrahub SDK Changelog

This is the changelog for the Infrahub SDK.
All notable changes to this project will be documented in this file.

Issue tracking is located in [Github](https://github.com/opsmill/infrahub/issues).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project uses [*towncrier*](https://towncrier.readthedocs.io/) and the changes for the upcoming release can be found in <https://github.com/opsmill/infrahub/tree/develop/infrahub/python_sdk/changelog/>.

<!-- towncrier release notes start -->

## [1.1.0rc0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.1.0rc0) - 2024-11-26

### Fixed

- CTL: `schema load` return a proper error message when authentication is missing or when the user doesn't have the permission to update the schema. ([#127](https://github.com/opsmill/infrahub-sdk-python/issues/127))
- CTL: List available transforms and generators if no name is provided ([#140](https://github.com/opsmill/infrahub-sdk-python/issues/140))

## [1.0.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.0.1) - 2024-11-12

### Removed

- Removed previously deprecated InfrahubTransform.init() method

### Deprecated

- Marked InfrahubCheck.init() as deprecated and scheduled to be removed in Infrahub SDK 2.0.0

### Added

- Adds `groups.group_add_subscriber` function to add a subscriber to a group.
- Adds order_weight property to AttributeSchema and RelationSchema classes.

### Fixed

- Fix generated GraphQL query when having a relationship to a pool node ([#27](https://github.com/opsmill/infrahub-sdk-python/issues/27))
- CTL: Fix support for relative imports for transforms and generators ([#81](https://github.com/opsmill/infrahub-sdk-python/issues/81))
- Fixes issues where InfrahubClient was not properly configured for a branch when running the `infrahubctl transform`, `infrahubctl check` and `infrhubctl generator` commands. ([#133](https://github.com/opsmill/infrahub-sdk-python/issues/133))
- Fixes an issue where a generator would not return any output if there are no members in the generator's target group.

## [1.0.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.0.0) - 2024-10-31

### Removed

- Breaking change: Removed all exports from infrahub_sdk/__init__.py except InfrahubClient, InfrahubClientSync and Config. If you previously imported other classes such as InfrahubNode from the root level these need to change to instead be an absolute path.

### Added

- Add support for specific timeout per request on InfrahubClient and InfrahubNode function calls. ([#25](https://github.com/opsmill/infrahub-sdk-python/issues/25))
- Added `infrahubctl menu` command to load menu definitions into Infrahub

### Fixed

- Fix SDK playback hash generation to read the correct filename ([#64](https://github.com/opsmill/infrahub-sdk-python/issues/64))
- CTL: Return friendly error on encoding violations when reading files. ([#102](https://github.com/opsmill/infrahub-sdk-python/issues/102))
- Changed the default connection timeout in the SDK to 60s.
- Fixes an issue where InfrahubClient was not properly URL encoding URL parameters.

## [0.14.1](https://github.com/opsmill/infrahub-sdk-python/tree/v0.14.1) - 2024-10-22

### Fixed

- Make `infrahubctl transform` command set up the InfrahubTransform class with an InfrahubClient instance ([#8](https://github.com/opsmill/infrahub-sdk-python/issues/8))
- Command `infrahubctl protocols` now supports every kind of schema attribute. ([#57](https://github.com/opsmill/infrahub-sdk-python/issues/57))

## [0.14.0](https://github.com/opsmill/infrahub-sdk-python/tree/v0.14.0) - 2024-10-04

### Removed

- Removed deprecated methods InfrahubClient.init and InfrahubClientSync.init ([#33](https://github.com/opsmill/infrahub-sdk-python/issues/33))

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
