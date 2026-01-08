# Infrahub SDK Changelog

This is the changelog for the Infrahub SDK.
All notable changes to this project will be documented in this file.

Issue tracking is located in [GitHub](https://github.com/opsmill/infrahub/issues).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project uses [*towncrier*](https://towncrier.readthedocs.io/) and the changes for the upcoming release can be found in <https://github.com/opsmill/infrahub/tree/develop/infrahub/python_sdk/changelog/>.

<!-- towncrier release notes start -->

## [1.18.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.18.0) - 2026-01-08

### Added

- Add ability to query for metadata on nodes to include information such as creation and update timestamps, creator and last user to update an object.
- Added ability to order nodes by metadata created_at or updated_at fields

### Removed

- The previously deprecated 'background_execution' parameter under client.branch.create() was removed.

### Fixed

- Rewrite and re-enable integration tests ([#187](https://github.com/opsmill/infrahub-sdk-python/issues/187))
- Fixed SDK including explicit `null` values for uninitialized optional relationships when creating nodes with object templates, which prevented the backend from applying template defaults. ([#630](https://github.com/opsmill/infrahub-sdk-python/issues/630))

### Housekeeping

- Fixed Python 3.14 compatibility warnings. Testing now requires pytest>=9.

## [1.17.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.17.0) - 2025-12-11

### Added

- Add support for Python 3.14

### Removed

- Removed copier as a dependency, this impacts the `infrahub repository init` command and contains new instructions for how to initialize a repository from the template.
- Remove `is_visible` property from Infrahub

## [1.16.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.16.0) - 2025-12-01

### Added

- Added infrahubctl branch report command to help with cleaning up branches in Infrahub.

### Changed

- Updated behaviour for recursive lookups for the conversion of nested relationships. Note that this change could cause issues in transforms or generators that use the convert_query_response feature if "id" or "__typename" isn't requested for nested related objects. ([#389](https://github.com/opsmill/infrahub-sdk-python/issues/389))
- The project now uses `uv` instead of `poetry` for package and dependency management.

### Removed

- Removed support for Python 3.9 (end of life)

## [1.15.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.15.1) - 2025-11-13

### Fixed

- Fixed nested object template range expansion. ([#624](https://github.com/opsmill/infrahub-sdk-python/issues/624))

## [1.15.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.15.0) - 2025-11-10

### Added

- Add `create_diff` method to create a diff summary between two timestamps
  Update `get_diff_summary` to accept optional time range parameters ([#529](https://github.com/opsmill/infrahub-sdk-python/issues/529))
- Add the ability to perform range expansions in object files. This feature allows users to define patterns in string fields that will be expanded into multiple objects, facilitating bulk object creation and management. The implementation includes validation to ensure that all expanded lists have the same length, preventing inconsistencies. Documentation has been updated to explain how to use this feature, including examples of valid and invalid configurations. ([#560](https://github.com/opsmill/infrahub-sdk-python/issues/560))
- Add `convert_object_type` method to allow converting an object to another type.
- Add `graph_version` and `status` properties to `Branch`
- Add `infrahubctl graphql` commands to export schema and generate Pydantic types from GraphQL queries
- Added deprecation warnings when loading or checking schemas

### Changed

- Deprecate the use of `raise_for_error=False` across several methods, using a try/except pattern is preferred. ([#493](https://github.com/opsmill/infrahub-sdk-python/issues/493))

### Fixed

- Respect default branch for client.query_gql_query() and client.set_context_properties() ([#236](https://github.com/opsmill/infrahub-sdk-python/issues/236))
- Fix branch creation with the sync client while setting `wait_until_completion=False` ([#374](https://github.com/opsmill/infrahub-sdk-python/issues/374))
- Replaced the `Sync` word in the protocol schema name so that the correct kind can be gotten from the cache ([#380](https://github.com/opsmill/infrahub-sdk-python/issues/380))
- Fix `infrahubctl info` command when run as an anonymous user ([#398](https://github.com/opsmill/infrahub-sdk-python/issues/398))
- JsonDecodeError now includes server response content in error message when JSON decoding fails, providing better debugging information for non-JSON server responses. ([#473](https://github.com/opsmill/infrahub-sdk-python/issues/473))
- Allow unsetting optional relationship of cardinality one by setting its value to `None` ([#479](https://github.com/opsmill/infrahub-sdk-python/issues/479))
- Bump docs dependencies ([#519](https://github.com/opsmill/infrahub-sdk-python/issues/519))
- Fix branch handling in `_run_transform` and `execute_graphql_query` functions in Infrahubctl to use environment variables for branch management. ([#535](https://github.com/opsmill/infrahub-sdk-python/issues/535))
- Allow the ability to clear optional attributes by setting them to None if they have been mutated by the user. ([#549](https://github.com/opsmill/infrahub-sdk-python/issues/549))
- Disable rich console print markup causing regex reformatting ([#565](https://github.com/opsmill/infrahub-sdk-python/issues/565))
- - Fixed issue with improperly escaped special characters in `hfid` fields and other string values in GraphQL mutations by implementing proper JSON-style string escaping

### Housekeeping

- Handle error gracefully when loading schema instead of failing with an exception ([#464](https://github.com/opsmill/infrahub-sdk-python/issues/464))
- Replace toml package with tomllib and tomli optionally for when Python version is less than 3.11 ([#528](https://github.com/opsmill/infrahub-sdk-python/issues/528))

## [1.14.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.14.0) - 2025-08-26

### Added

- Added `infrahubctl repository init` command to allow the initialization of an Infrahub repository using [infrahub-template](https://github.com/opsmill/infrahub-template). ([#466](https://github.com/opsmill/infrahub-sdk-python/issues/466))
- add support for NumberPool attributes in generated protocols

### Fixed

- Fix value lookup using a flat notation like `foo__bar__value` with relationships of cardinality one ([#6882](https://github.com/opsmill/infrahub-sdk-python/issues/6882))
- Create a new batch while fetching relationships instead of using the reusing the same one.
- Update internal calls to `count` to include the branch parameter so that the query is performed on the correct branch
- Update offset in process_page() which was causing a race condition in rare case. ([#514](https://github.com/opsmill/infrahub-sdk-python/pull/514))

## [1.13.5](https://github.com/opsmill/infrahub-sdk-python/tree/v1.13.5) - 2025-07-23

### Fixed

- Respect ordering when loading files from a directory

## [1.13.4](https://github.com/opsmill/infrahub-sdk-python/tree/v1.13.4) - 2025-07-22

### Fixed

- Fix processing of relationshhip during nodes retrieval using the Sync Client, when prefecthing related_nodes. ([#461](https://github.com/opsmill/infrahub-sdk-python/issues/461))
- Fix schema loading to ignore non-YAML files in folders. ([#462](https://github.com/opsmill/infrahub-sdk-python/issues/462))
- Fix ignored node variable in filters(). ([#469](https://github.com/opsmill/infrahub-sdk-python/issues/469))
- Fix use of parallel with filters for Infrahub Client Sync.
- Avoid sending empty list to infrahub if no valids schemas are found.

## [1.13.3](https://github.com/opsmill/infrahub-sdk-python/tree/v1.13.3) - 2025-06-30

### Fixed

- Update InfrahubNode creation to include __typename, display_label, and kind from a RelatedNode ([#455](https://github.com/opsmill/infrahub-sdk-python/issues/455))

## [1.13.2](https://github.com/opsmill/infrahub-sdk-python/tree/v1.13.2) - 2025-06-27

### Fixed

- Re-enable specifying a cardinality-one relationship using a RelatedNode when creating an InfrahubNode ([#452](https://github.com/opsmill/infrahub-sdk-python/issues/452))

## [1.13.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.13.1) - 2025-06-19

### Fixed

- Fix the import path of the Attribute class [#448](https://github.com/opsmill/infrahub-sdk-python/pull/448)

## [1.13.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.13.0) - 2025-06-11

This release adds support for the new NumberPool attribute and loading object and menu files from external repositories in Infrahub 1.3.

### Added

- Added NumberPool as a new attribute kind, for support in Infrahub 1.3
- Added support for object and menu files in the `.infrahub` repository configuration file
- Defined ordering in which object files are loaded

### Housekeeping

- Refactor InfrahubNode to avoid the creation of a dynamic Python class for each object defined

## [1.12.3](https://github.com/opsmill/infrahub-sdk-python/tree/v1.12.3) - 2025-06-10

## Fixed

- fix Python transforms tests in the resource testing framework by @ogenstad in https://github.com/opsmill/infrahub-sdk-python/pull/433
- add unit test for Python transforms test for the resource testing framework @wvandeun in https://github.com/opsmill/infrahub-sdk-python/pull/435

### Changed

- loosen requirement for the optional Rich dependency from v12.0.0 up to but not including v14.0.0 by @wvandeun in https://github.com/opsmill/infrahub-sdk-python/pull/434

## [1.12.2](https://github.com/opsmill/infrahub-sdk-python/tree/v1.12.2) - 2025-06-05

### Fixed

- fix bug in Timestamp.add by @ajtmccarty in [#403](https://github.com/opsmill/infrahub-sdk-python/pull/403)
- utils.py: improve file not found exception message by @granoe668 in [#425](https://github.com/opsmill/infrahub-sdk-python/pull/425)

### Changed

- Add partial_match to the client.count() by @BeArchiTek in [#411](https://github.com/opsmill/infrahub-sdk-python/pull/411)

### Housekeeping

- Loosen pinned requirement for `whenever` to allow versions from 0.7.2 up to but not including 0.8.0.
- Bump http-proxy-middleware from 2.0.7 to 2.0.9 in /docs by @dependabot in [#418](https://github.com/opsmill/infrahub-sdk-python/pull/418)

## [1.12.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.12.1) - 2025-05-12

### Changed

- Pin click to v8.1.* as a temporary workaround for #406 ([#406](https://github.com/opsmill/infrahub-sdk-python/issues/406))

## [1.12.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.12.0) - 2025-04-29

### Added

- Added the ability to convert the query response to InfrahubNode objects when using Python Transforms in the same way you can with Generators. ([#281](https://github.com/opsmill/infrahub-sdk-python/issues/281))
- Added a "branch" parameter to the client.clone() method to allow properly cloning a client that targets another branch.

## [1.11.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.11.1) - 2025-04-28

### Changed

- Set the HFID on related nodes for cardinality many relationships, and add HFID support to the RelationshipManager `add`, `extend` and `remove` methods.

## [1.11.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.11.0) - 2025-04-17

### Deprecated

- The 'timeout' parameter while creating a node or fetching the schema has been deprecated. the default_timeout will be used instead.

### Added

- Add support for object Template when generating protocols ([#329](https://github.com/opsmill/infrahub-sdk-python/issues/329))
- Add a Guide related to Python Typing
- Add method `client.schema.set_cache()` to populate the cache manually (primarily for unit testing)
- By default, schema.fetch will now populate the cache (this behavior can be changed with `populate_cache`)
- Add `menu validate` command to validate the format of menu files.

### Fixed

- Raise a proper branch not found error when requesting a node or schema for a branch that doesn't exist. ([#286](https://github.com/opsmill/infrahub-sdk-python/issues/286))
- Fix support for Sync when generating Python Protocols

### Housekeeping

- Add `invoke lint-doc` command to help run the docs linters locally
- Add a fixture to always reset some environment variables before running tests
- Update Pytest-httpx and set all responses as reusable

## [1.10.2](https://github.com/opsmill/infrahub-sdk-python/tree/v1.10.2) - 2025-04-11

### Fixed

- fix an issue where nodes attributes were not updated when setting the same value than the one used during node instantiation
- fixes an issue where the default branch of the client store was not properly set in a generator

## [1.10.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.9.1) - 2025-04-04

### Changed

- Improve error message when a schema received from the server is not JSON valid. The new exception will be of type `infrahub_sdk.exceptions.JsonDecodeError` instead of `json.decoder.JSONDecodeError`

## [1.10.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.10.0) - 2025-04-01

### Deprecated

- The method `get_by_hfid` on the object Store has been deprecated, use `get(key=[hfid])` instead
- Using a Store without specifying a default branch is now deprecated and will be removed in a future version.

### Added

- All nodes generated by the SDK will now be assigned an `internal_id` (`_internal_id`). This ID has no significance outside of the SDK.
- Jinja2 templating has been refactored to allow for filters within Infrahub. Builtin filters as well as those from Netutils are available.
- The object store has been refactored to support more use cases in the future and it now properly support branches.

### Fixed

- Fix node processing, when using fragment with `prefetch_relationships`. ([#331](https://github.com/opsmill/infrahub-sdk-python/issues/331))

## [1.9.2](https://github.com/opsmill/infrahub-sdk-python/tree/v1.9.2) - 2025-03-26

### Changed

- Remove hfid in upsert payload, to improve node upsert performances

## [1.9.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.9.1) - 2025-03-21

### Fixed

- Fixed an issue where the process_nodes method in the generators used the old format of the schema hash, so node population didn't work

## [1.9.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.9.0) - 2025-03-21

### Added

- Add 'schema_hash' parameter to client.schema.all to only optionally refresh the schema if the provided hash differs from what the client has already cached. ([#152](https://github.com/opsmill/infrahub-sdk-python/issues/152))

### Changed

- CoreStandardGroups created or updated by a generator in Infrahub are now stored as a member of the CoreGeneratorGroup. Previously they were being stored as children of the CoreGeneratorGroup.

### Fixed

- The SDK client query methods (get, filters, all) default behaviour has changed. The query methods will store the retrieved nodes in the internal store by default, where previously this behaviour had to be enabled explicitly using the `populate_store` argument. ([#15](https://github.com/opsmill/infrahub-sdk-python/issues/15))

## [1.8.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.8.0) - 2025-03-19

### Deprecated

- Timestamp: Direct access to `obj` and `add_delta` have been deprecated and will be removed in a future version. ([#255](https://github.com/opsmill/infrahub-sdk-python/issues/255))

### Added

- Added support for Enum in GraphQL query and mutation. ([#18](https://github.com/opsmill/infrahub-sdk-python/issues/18))

### Fixed

- Refactored Timestamp to use `whenever` instead of `pendulum` and extend Timestamp with `add()`, `subtract()`, and `to_datetime()`. ([#255](https://github.com/opsmill/infrahub-sdk-python/issues/255))
- Fixed support for Python 3.13 as it's no longer required to have Rust installed on the system.

## [1.7.2](https://github.com/opsmill/infrahub-sdk-python/tree/v1.7.2) - 2025-03-07

### Added

- Added logger to `InfrahubGenerator` class to allow users use built-in logging (`self.logger`) to show logging within Infrahub CI pipeline.

### Changed

- Aligned the environment variables used by `infrahubctl` with the environment variables used by the SDK.
- Allowed the `infrahubctl transform` command to return a regular string that does not get converted to a JSON string.
- Changed InfrahubNode/InfrahubNodeSync `artifact_fetch` and `artifact_generate` methods to use the name of the artifact instead of the name of the artifact definition.

### Fixed

- `protocols` CTL command properly gets default branch setting from environment variable. ([#104](https://github.com/opsmill/infrahub-sdk-python/issues/104))
- Fix typing for Python 3.9 ([#251](https://github.com/opsmill/infrahub-sdk-python/issues/251))
- Refactor Timestamp to use `whenever` instead of `pendulum` and extend Timestamp with add(), subtract(), and to_datetime(). ([#255](https://github.com/opsmill/infrahub-sdk-python/issues/255))
- Remove default value "main" for branch parameter from all Infrahub CTL commands. ([#264](https://github.com/opsmill/infrahub-sdk-python/issues/264))
- Fixed support for Python 3.13, it's no longer required to have Rust installed on the system.

### Housekeeping

- Move the function `read_file` from the ctl module to the SDK.
- Fixed typing for Python 3.9 and removed support for Python 3.13. ([#251](https://github.com/opsmill/infrahub-sdk-python/issues/251))
- Removed default value "main" for branch parameter from all Infrahub CTL commands. ([#264](https://github.com/opsmill/infrahub-sdk-python/issues/264))

### Housekeeping

- Moved the function `read_file` from the ctl module to the SDK.

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
