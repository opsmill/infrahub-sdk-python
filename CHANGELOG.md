# Infrahub SDK Changelog

This is the changelog for the Infrahub SDK.
All notable changes to this project will be documented in this file.

Issue tracking is located in [Github](https://github.com/opsmill/infrahub/issues).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project uses [*towncrier*](https://towncrier.readthedocs.io/) and the changes for the upcoming release can be found in <https://github.com/opsmill/infrahub/tree/develop/infrahub/python_sdk/changelog/>.

<!-- towncrier release notes start -->

## [1.8.0rc0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.8.0rc0) - 2025-02-23

### Changed

- Changes InfrahubNode `artifact_fetch` and `artifact_generate` methods to use the name of the artifact instead of the name of the artifact definition.

### Fixed

- `protocols` CTL command properly gets default branch setting from environment variable. ([#104](https://github.com/opsmill/infrahub-sdk-python/issues/104))
- Fix typing for Python 3.9 and remove support for Python 3.13. ([#251](https://github.com/opsmill/infrahub-sdk-python/issues/251))
- Remove default value "main" for branch parameter from all Infrahub CTL commands. ([#264](https://github.com/opsmill/infrahub-sdk-python/issues/264))

### Housekeeping

- Move the function `read_file` from the ctl module to the SDK.

## [1.7.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.7.1) - 2025-01-30

### Removed

- All mention of pylint have been removed from the project. ([#206](https://github.com/opsmill/infrahub-sdk-python/issues/206))

## [1.7.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.7.0) - 2025-01-23

### Added

- adds `infrahubctl repository list` command

## [1.6.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.6.1) - 2025-01-16

Fixes release of v1.6.0

## [1.6.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.6.0) - 2025-01-16

### Added

- Replace GitPython with dulwich ([#130](https://github.com/opsmill/infrahub-sdk-python/issues/130))

### Changed

- Added possibility to use filters for the SDK client's count method

### Fixed

- Fixes issue where using `parallel` query execution could lead to excessive and unneeded GraphQL queries

## [1.5.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.5.0) - 2025-01-09

### Added

- Adds `infrahubctl info` command to display information of the connectivity status of the SDK. ([#109](https://github.com/opsmill/infrahub-sdk-python/issues/109))
- Add `count` method to both sync and async clients to retrieve the number of objects of a given kind ([#158](https://github.com/opsmill/infrahub-sdk-python/issues/158))
- Add the ability to batch API queries for `all` and `filter` functions. ([#159](https://github.com/opsmill/infrahub-sdk-python/issues/159))
- `client.all` and `client.filters` now support `order` parameter allowing to disable order of retrieve nodes in order to enhance performances

## [1.4.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.3.0) - 2025-01-05

### Fixed

- Fixes an issue introduced in 1.4 that would prevent a node with relationship of cardinality one from being updated.

## [1.4.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.4.0) - 2025-01-03

### Changed

- The inclusion of properties for Attribute and Relationships by default has been disabled when querying nodes from Infrahub.
  it can be enabled by using the parameter `property` in `client.get|all|filters` method ([#191](https://github.com/opsmill/infrahub-sdk-python/issues/191))
- Fix an issue with python-transform-unit-process failing to run ([#198](https://github.com/opsmill/infrahub-sdk-python/issues/198))
- Add processing of nodes when no variable are passed into the command to run generators ([#176](https://github.com/opsmill/infrahub-sdk-python/issues/176))

## [1.3.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.3.0) - 2024-12-30

### Added

#### Testing library (**Alpha**)

A new collection of tools and utilities to help with testing is available under `infrahub_sdk.testing`.

The first component available is a `TestInfrahubDockerClient`, a pytest Class designed to help creating integration tests based on Infrahub. See a simple example below to help you get started.

> the installation of `infrahub-testcontainers` is required

```python
import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.testing.docker import TestInfrahubDockerClient

class TestInfrahubNode(TestInfrahubDockerClient):

    @pytest.fixture(scope="class")
    def infrahub_version(self) -> str:
        """Required (for now) to define the version of infrahub to use."""
        return "1.0.10"

    @pytest.fixture(scope="class")
    async def test_create_tag(self, default_branch: str, client: InfrahubClient) -> None:
        obj = await client.create(kind="BuiltinTag", name="Blue")
        await obj.save()
        assert obj.id
```

### Changed

- The Pydantic models for the schema have been split into multiple versions to align better with the different phase of the lifecycle of the schema.
  - User input: includes only the options available for a user to define (NodeSchema, AttributeSchema, RelationshipSchema, GenericSchema)
  - API: Format of the schema as exposed by the API in infrahub with some read only settings (NodeSchemaAPI, AttributeSchemaAPI, RelationshipSchemaAPI, GenericSchemaAPI)

### Fixed

- Fix behaviour of attribute value coming from resource pools for async client ([#66](https://github.com/opsmill/infrahub-sdk-python/issues/66))
- Convert import_root to a string if it was submitted as a Path object to ensure that anything added to sys.path is a string
- Fix relative imports for the pytest plugin, note that the relative imports can't be at the top level of the repository alongside .infrahub.yml. They have to be located within a subfolder. ([#166](https://github.com/opsmill/infrahub-sdk-python/issues/166))

## [1.2.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.2.0) - 2024-12-19

### Added

- Add batch feature, that use threading, to sync client ([#168](https://github.com/opsmill/infrahub-sdk-python/issues/168))
- Added InfrahubClient.schema.in_sync method to indicate if a specific branch is in sync across all worker types
- Added Python 3.13 to the list of supported versions

### Fixed

- Fix an issue with with `infrahubctl menu load` that would fail while loading the menu

## [1.1.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.10.0) - 2024-11-28

### Added

- Added InfrahubClient.schema.wait_until_converged() which allowes you to wait until the schema has converged across all Infrahub workers before proceeding with an operation. The InfrahubClient.schema.load() method has also been updated with a new parameter "wait_until_converged".

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

- Breaking change: Removed all exports from `infrahub_sdk/__init__.py` except InfrahubClient, InfrahubClientSync and Config. If you previously imported other classes such as InfrahubNode from the root level these need to change to instead be an absolute path.

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
