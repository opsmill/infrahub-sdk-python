# Infrahub SDK Changelog

This is the changelog for the Infrahub SDK.
All notable changes to this project will be documented in this file.

Issue tracking is located in [GitHub](https://github.com/opsmill/infrahub/issues).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project uses [*towncrier*](https://towncrier.readthedocs.io/) and the changes for the upcoming release can be found in <https://github.com/opsmill/infrahub/tree/develop/infrahub/python_sdk/changelog/>.

<!-- towncrier release notes start -->

## [1.24.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.24.0) - 2026-11-09

### Security

- Raised the `graphql-core` requirement from `>=3.1` to `>=3.2.12`, so installing the SDK can no longer resolve a release affected by CVE-2026-75507 or CVE-2026-75508. Both are denial-of-service bugs: one in the validation rule that checks for conflicting fields, which `infrahubctl graphql generate-return-types` runs, and one in the parser, which ignored comments when counting tokens. With 3.2.12 or later, a query that would make field-conflict validation run for minutes now fails validation with an error instead.

### Removed

- `numpy` and `mdxify` are no longer installed by the `ctl` and `all` extras.

  Neither is used by the SDK. `numpy` was only ever needed because older `pyarrow` releases required it, and `pyarrow` still installs it itself on the versions that do. `mdxify` is a documentation tool used when building these docs, not at runtime.

  If your project imports either package directly, add it to your own dependencies rather than relying on `infrahub-sdk[ctl]` to supply it.

### Deprecated

- Deprecated support for Python 3.10. Python 3.10 is end of life, and `infrahub-sdk` 1.24.0 is the last release that supports Python 3.10. The next release removes that support.

### Added

- A `CoreNumberPool` can be created with its ranges in one call, by passing `ranges` as a list of dictionaries with `start`, `end` and `allocation_weight`, any of which can be left out. Saving with `allow_upsert=True` sets the ranges of an existing pool to the declared list. Before, the SDK sent each range as an empty object, which Infrahub read as one range without a start or an end. A single range of an existing pool is still created, changed or deleted through its `CoreNumberPoolRange` node. An object file declares the same list under `ranges`, as objects holding the bounds, on a new pool and on one that already exists. Requires Infrahub 1.12 or later.
- Add the `connect_timeout` setting (`INFRAHUB_CONNECT_TIMEOUT`, default 10 seconds) so the TCP/TLS connection phase of every request is bounded separately from the request `timeout`. An unreachable address now fails fast instead of consuming the whole request budget, which lets endpoints published through DNS round robin fall over to the next address quickly.
- Add the `infrahubctl troubleshooting trace-sample-ratio` commands to read, set and clear the temporary trace sampling ratio of an Infrahub instance.
- Add the `shared` option to `GitRepo` in `infrahub_sdk.testing.repository`. With `shared=True`, every user on the machine can read and write the Git repository that `GitRepo` creates, so Infrahub containers that run as another user than the test process can fetch from it and push to it. The default, `False`, keeps the current behavior.
- Added support for Python 3.15. The `requires-python` range now allows 3.15, and the unit tests run on 3.15 in CI.
- Added the `only` argument to `get`, `all`, `filters` and relationship `fetch`, to fetch only the named attributes and relationships; reading a field that was not fetched raises `FieldNotLoadedError`, and `is_loaded` tells whether a field was fetched.
- Added the location, the received value and the reason as separate fields (`loc`, `input`, `reason`) on every schema validation error, next to the unchanged `field` and `message`, so a consumer can report each problem without parsing the message text.
- Codes in Infrahub's error catalogue now raise an exception class of their own, importable from `infrahub_sdk.exceptions`, carrying the failure's payload as directly typed attributes. Identifying a specific failure no longer means matching words in a message:

  ```python
  from infrahub_sdk.exceptions import ApiError, UniquenessViolationError

  try:
      await node.save()
  except UniquenessViolationError as exc:
      print(exc.node_kind, exc.fields)   # "TestPerson", ["name"]
  except ApiError as exc:
      print("some other failure:", exc.code)
  ```

  The new classes are `AttributeConstraintViolationError`, `AttributeInvalidTypeError`, `AttributeRequiredError`, `BranchAlreadyMergedError`, `BranchNeedsRebaseError`, `MergeInProgressError`, `MergeRecoveryRequiredError`, `UndefinedError`, `UniquenessViolationError`, and `WorkerTimeoutError`. Each is typed exactly as the catalogue declares the payload, so a required field is never optional and needs no guard. They all descend from `GraphQLError`, so no `except` clause stops catching what it catches today. `NODE_NOT_FOUND`, `BRANCH_NOT_FOUND` and `SCHEMA_NOT_FOUND` reach the classes the SDK already had for them, listed under Changed.

  `exc.http_status` reads the status the envelope declares. Where the envelope omits one, a generated class supplies the status the catalogue gives its code; the three lookup-miss classes declare none, since they are also raised with no server behind them, and stay `None` there.

  `AUTHENTICATION_REQUIRED`, `TOKEN_EXPIRED`, and `PERMISSION_DENIED` deliberately have no class of their own: each of them reaches the SDK on two transports, and which generic class it raises follows the transport the SDK observed rather than the status the code declares. Catch `ApiError` and test `exc.code` to handle one of the three whichever way it arrived.

  A server predating a code, or one whose payload does not match what the catalogue declares for it, still raises the generic class for the transport with `exc.code` readable, so an SDK of any version keeps working against a server of any version.

  `docs/python-sdk/topics/error_handling` covers the hierarchy, the attributes readable on a caught error, and the cross-version guarantees.
- Number attributes have `attach_to_pool()` and `detach_from_pool()`. `attach_to_pool()` makes a number pool track the number the attribute holds, without allocating a new one, and `detach_from_pool()` makes the pool stop tracking it while the attribute keeps its number. Both take effect when the node is saved, and require Infrahub 1.12 or later.
- Object files can now reference an existing node through a relationship whose peer is a generic, by giving the node's `kind` and `hfid`. When the generic has no HFID, a reference can also be an HFID alone, and the load uses the single node that matches it among the kinds that inherit from the generic. The load fails when no node or more than one node matches.
- Resource pool nodes have `get_pool_allocations()`, which lists the resources a pool holds and, for a number pool, whether the pool allocated each number or a user attached it. Requires Infrahub 1.12 or later. `get_pool_allocated_resources()` is unchanged.
- The SDK sends the W3C `traceparent` header with each request to Infrahub when OpenTelemetry is installed and a span is active, so the Infrahub server records its spans in the caller's trace. The new `tracing` extra installs the OpenTelemetry API.
- The schema models accept `parameters.ranges` on NumberPool attributes, a list of ranges with an optional `start`, `end` and `weight`; a range without a `start` or an `end` is open on that side. The `start_range`/`end_range` shorthand is now optional and deprecated. `ranges` is `None` when a NumberPool attribute declares no range, which Infrahub reads as one range without a start or an end, and an empty list declares no range.
- `query` and `variables` are now readable on every `ApiError`, not only on the GraphQL branch. Reading either off an `AuthenticationError` previously raised `AttributeError`:

  ```python
  try:
      await client.execute_graphql(query=query)
  except ApiError as exc:
      log.error("request failed", code=exc.code, query=exc.query)   # no longer raises on a 401
  ```

  That clause is the one the SDK recommends for the three authentication codes, since each of them can arrive either on a real 401 or 403 or inside a GraphQL `errors` array, so it is exactly where the attributes had to exist. They join `code`, `http_status`, `extensions` and `errors`, which were already declared there for the same reason.

  `None` means the failed request was not recorded on the exception rather than that there was no query: an authentication failure is observed at the transport, which has neither to hand. Nothing that reads these attributes today changes - `GraphQLError` still populates both from the request it was raised for.

### Changed

- `InfrahubGroupContext.delete_unused()` and its sync counterpart no longer raise. They attempt every unused member and return a `ReapResult`, importable from `infrahub_sdk.query_groups`, that lists the members the server refused to delete, the members the cleanup never reached, and the failure that stopped it, if any. A caller that invoked `delete_unused()` directly and relied on it raising must now inspect that result. `update_group()` and the tracking context manager still raise, as described below.

  Leaving a tracking context whose cleanup was refused now raises `TrackingGroupCleanupError` once every member has been attempted and the tracking group has been written, in place of the first `GraphQLError`. If the group write itself fails, its error is raised instead. `TrackingGroupCleanupError` is not a `GraphQLError`, so a caller that caught the cleanup failure with `except GraphQLError` must catch it explicitly. A cleanup stopped by a failure that is not about a member, such as a timeout, still raises that failure itself. ([#572](https://github.com/opsmill/infrahub-sdk-python/issues/572))
- Generators, transforms and checks run without an explicit branch now target the configured `default_branch` (`INFRAHUB_DEFAULT_BRANCH`, `main` by default) instead of the active branch of the local Git checkout. If you run `infrahubctl transform`, `generator` or `check` locally and relied on them following your Git branch, set `INFRAHUB_DEFAULT_BRANCH_FROM_GIT=true` or pass `--branch` explicitly. ([#1290](https://github.com/opsmill/infrahub-sdk-python/issues/1290))
- A failure the server's error catalogue describes now carries a message naming that code and the server's own words, in place of the query text. `GraphQLError` previously rendered as `An error occurred while executing the GraphQL Query <query>, <errors>` and now reads `UNIQUENESS_VIOLATION: Node of kind TestPerson already has name 'John'`; `AuthenticationError` reads `AUTHENTICATION_REQUIRED: <reason>`. On both transports the code names the first error only, which is the one that determines the exception raised; the complete list stays on `exc.errors`, and the query and variables stay on `exc.query` and `exc.variables`.

  A failure the catalogue does **not** describe keeps today's message exactly, query text and full error list included, as does one of the lookup-miss classes raised without a server behind it. That covers a server predating the catalogue, an error carrying no `extensions`, and, since a current server codes every error it reports, anything the server coded `UNDEFINED_ERROR`. `exc.code` is readable in every case, so it is not the test for which message form you are holding: `code_names_the_failure(exc.code)`, importable from `infrahub_sdk.exceptions`, is.

  In `infrahubctl`, a described failure is now reported by its code and message rather than prefixed with `Authentication failure:` or rendered as a bare error list. An undescribed one renders exactly as before, so a GraphQL validation error still shows the line and column it failed on. Code matching on any of these strings should branch on `exc.code` instead.
- A lookup miss the server reports - `NODE_NOT_FOUND`, `BRANCH_NOT_FOUND` or `SCHEMA_NOT_FOUND` - now raises `NodeNotFoundError`, `BranchNotFoundError` or `SchemaNotFoundError` built from the payload the server sent, where it previously raised a generic `GraphQLError`:

  ```python
  try:
      await client.delete(kind="NetworkDevice", id=device_id)
  except NodeNotFoundError:
      ...  # already gone
  ```

  These three are the only catalogued classes the SDK also raises on its own, for a lookup that returned nothing and for the REST 404 behind a missing file. A ladder that handles one of them specifically will now see server-reported failures arrive there alongside the SDK's own, and `exc.code is not None` tells the two apart.
- Authentication failures now surface the server's error envelope. `AuthenticationError` and `GraphQLError` share a new `ApiError` base carrying `code`, `http_status`, `extensions`, and `errors`, so a caller can branch on the server's catalogue code instead of matching on message text.

  A 401 or 403 whose body the SDK cannot read as an error envelope now raises `AuthenticationError` carrying the best reason available: the REST API's bare `detail` string where the body has one, and otherwise the plain status. Previously the same responses raised `JsonDecodeError` (or, from the object store and file handler, a raw `json.JSONDecodeError`) when the body was not JSON, and `TypeError` when the body carried an `errors` array whose entries had no `message`. A body that was JSON but carried no `errors` key raised `AuthenticationError` with its generic default message, dropping the status the server sent. Code that catches those types around `object_store`, `file_handler`, or a client request should catch `AuthenticationError` instead.

  `from infrahub_sdk.exceptions import *` now yields exactly the exception classes. It previously also carried whatever the module imported for its own annotations, such as `Mapping` and `Any`. Every exception class keeps its name and its import path.
- Changed `number_pool_id` in the parameters of a NumberPool attribute to a read-only field: schema validation now warns that the value is ignored instead of accepting it.
- Generated protocols are now ordered by the class name they render rather than by the schema name without its namespace, so `BuiltinIPPrefix` no longer sorts under `IPPrefix`. Regenerating with `infrahubctl protocols` reorders the classes in your file and changes nothing else. The ordering is also total now. Kinds that the old key compared equal, two sharing a name and differing only in namespace, or two whose names differ only in case, previously fell back to whatever order the schema was supplied in, which could make the same schema render differently from one run to the next.
- Raised the `rich` requirement from `>=12` to `>=12.6`, the first release that honours `FORCE_COLOR`. Earlier releases ignore the variable, so the test suite's rendering guard could not describe them; nothing in the SDK itself changes.
- The `rich` requirement is now `>=12.6` with no upper bound, so the SDK can be installed alongside rich 14 and later.

  The previous `<14` cap would otherwise have applied to every install rather than only those using the `infrahubctl` CLI, and would have conflicted with any project already on a newer rich. The SDK's unit tests pass against rich 13, 14 and 15.
- The protocols shipped in `infrahub_sdk.protocols` now carry the peer type of every relationship, so `node.rel.peer` and `node.many_rel.peers[0].peer` resolve to the peer's protocol instead of a bare `InfrahubNode`, and a cardinality-one relationship can be assigned an id, an HFID, a peer node or `None`. They are generated by the same renderer as `infrahubctl protocols` rather than by a separate template, which also adds the relationships the API exposes implicitly (`member_of_groups`, `subscriber_of_groups`, `profiles`) and the `ProfileBuiltinIPAddress`, `ProfileBuiltinIPPrefix`, `ProfileBuiltinTag` and `ProfileIpamNamespace` kinds. Attributes that always hold a value are no longer typed as optional, and each attribute now follows its schema kind, so `CoreGlobalPermission.decision` and `CoreObjectPermission.decision` are `Integer` rather than `Enum`. Two relationships that the API never exposed, `CoreGenericAccount.tokens` and `CoreGenericAccount.external_identities`, are gone. Protocols generated for your own schema now import the four `Profile*` kinds above instead of redefining them.
- Two extras now cover testing, replacing the `tests` extra.

  `pip install 'infrahub-sdk[testing]'` installs pytest and enables the bundled `pytest-infrahub` plugin, which is what you want to test your own Transforms, Queries and Checks. `pip install 'infrahub-sdk[testcontainers]'` additionally provides `infrahub_sdk.testing.docker`, which starts a real Infrahub in containers so your tests can run against a live instance instead of mocked responses.

  They are kept apart because the container tooling is a much heavier install. `[testing]` adds four packages on top of a plain install; `[testcontainers]` adds around sixty, among them Docker, FastAPI and Prefect client libraries. Previously you would have had to take all of it to get either.

  The `tests` extra is gone. It stopped installing anything in 1.16.0 while the documentation carried on advertising it, so since then `pip install 'infrahub-sdk[tests]'` has warned about an unknown extra and installed only the base package. If you are coming from 1.15.2 or earlier, `[testing]` is the direct replacement for what `[tests]` gave you.
- `NodeNotFoundError.identifier` is now annotated `Mapping[str, list[str]] | str`. The SDK already raised it with a plain string to name a missing file, so this documents behaviour that was always there; no runtime behaviour changes and no existing caller needs updating.
- `NodeNotFoundError`, `BranchNotFoundError`, and `SchemaNotFoundError` now descend from `GraphQLError`, so that one class covers a lookup miss however it arose: reported by the server, decided by the SDK, or turned from a REST 404.

  An `except GraphQLError` clause therefore also catches lookup misses that involved no GraphQL request at all. Code that relied on those escaping such a clause should catch the specific class ahead of it, as an ordered `except` ladder already must. Each class keeps its name, its constructor, and the message it produces when no server reported the failure, and `errors`, `query`, and `variables` are now readable on every one of them rather than missing on a client-side raise.

  `NodeInvalidError` inherits the re-rooting but not the adopted code: it means a node of the wrong kind rather than a lookup miss, so `NodeInvalidError.CODE` is `None` where `NodeNotFoundError.CODE` is `NODE_NOT_FOUND`.
- `ObjectFile.validate_content()` and `MenuFile.validate_content()`, their `spec` properties, and `InfrahubFile.validate_content()` now raise `infrahub_sdk.exceptions.ValidationError` when a file has one of these problems:

  - a `kind` of the other file type, such as `kind: Menu` in an object file, which previously raised `ValueError`
  - an unknown `kind` or `apiVersion`, or a missing `spec`, which previously raised a pydantic `ValidationError`
  - a `spec` that does not match the object or menu format, which previously raised a pydantic `ValidationError` for menu files

  The exception's `identifier` is the file location. `messages` holds one line per problem, such as `kind | Input should be 'Menu' or 'Object', received 'Schema' (enum)`. The line names the field and includes the wrong value when that value is a single string, number or boolean. `infrahubctl object load`, `object validate`, `menu load` and `menu validate` therefore report these problems as a validation error for the file instead of stopping with a Python traceback. `infrahubctl` also no longer drops text in square brackets from these messages.

  The SDK `ValidationError` does not subclass `ValueError` or the pydantic `ValidationError`. Code that catches either of those around these methods should catch `infrahub_sdk.exceptions.ValidationError` instead.
- `add()`, `extend()` and `remove()` on the `ranges` relationship of a `CoreNumberPool` now raise `FeatureNotSupportedError`, and `infrahubctl object update --set ranges=...` reports the same refusal before it changes anything. Before, `add()` and `extend()` dropped the range without an error, and `remove()` sent the remaining ranges as references, which Infrahub refused with a GraphQL error. To set the ranges of an existing pool, pass the complete list of ranges to `client.create()` and save the pool with `allow_upsert=True`, or declare them in an object file. To add, change or delete a single range, create, update or delete its `CoreNumberPoolRange` node.
- `infrahub-sdk` now requires `pydantic>=2.0.3`, up from `>=2.0.0`.

  If you pin `pydantic` to 2.0, 2.0.1 or 2.0.2, installing the SDK now fails while resolving dependencies. Those versions never actually worked: `import infrahub_sdk` raised a `SchemaError` on them, because their regex engine rejects a pattern used by the schema models. Pin `pydantic>=2.0.3` to resolve it.

  `anyio` and `typing-extensions` are now installed as direct requirements of the SDK itself. It has always imported them but relied on other packages to pull them in, so a minimal or heavily constrained environment could end up with the SDK installed and unusable. No action is needed, installs simply become reliable.

  `packaging` is now a direct requirement of the `testcontainers` extra, which is where the `infrahub_sdk.testing.docker` helper that imports it lives. A plain `pip install infrahub-sdk` does not install it.

### Fixed

- Tracking groups now reconcile correctly when a run saves no nodes at all. Previously `update_group()` returned early on an empty member list, so a generator that produced nothing (a decommissioning run) or a repository whose last object file was removed left every previously tracked node behind as an orphan, still listed in the group. With `delete_unused_nodes=True`, as generators and repository imports use it, a run that tracks nothing but has an existing group now prunes it; a run that tracks nothing and has no group still creates none. With `delete_unused_nodes=False` the existing group is not read, so a run that tracks nothing still leaves it unchanged.

  The cleanup now deletes unused members on the branch the tracking context targets. It previously deleted them on the client's default branch, so on any other branch it removed the wrong node or found nothing to remove.

  Cleanup is also no longer aborted by a single refused delete. `delete_unused()` attempts every unused member and reports the refusals together as `TrackingGroupCleanupError` instead of propagating the first one and silently skipping the rest. Members that could not be deleted are kept in the tracking group so a later run retries them. A refusal that persists, such as a node outside the run that still points at the member through a mandatory relationship, is raised again on every run until whatever blocks the deletion is removed; previously the member dropped out of the group after the first failure and stayed behind unnoticed.

  A failure that is about the request rather than the member being deleted, such as a timeout, an expired token, or a branch that is gone or locked by a merge, stops the cleanup and is raised as itself rather than recorded against every remaining member in turn. The tracking group write is still attempted before that failure surfaces, listing the members the cleanup never reached along with the nodes the run created, so an interrupted cleanup no longer leaves those nodes in no group at all whenever the server can still accept the write. The member whose delete was interrupted stays in the group when the server answered, since a rejected delete removed nothing. When no answer came back, such as on a timeout, the delete may have gone through, so that member is left out of the group; if the delete in fact did not happen, it stays behind as before. When the write fails as well, usually for the same reason, the failure that stopped the cleanup is the one raised, with the write's failure as its cause.

  `infrahubctl` renders `TrackingGroupCleanupError` as a table of each member and the server's reason instead of a traceback, and the exception can be serialized so it survives a task orchestrator's failure handling. ([#572](https://github.com/opsmill/infrahub-sdk-python/issues/572))
- Sync protocols generated by `infrahubctl protocols` now inherit the `*Sync` variant of every base class that has one, instead of only `CoreNode`, `CoreProfile` and `CoreObjectTemplate`. A class inheriting another core kind (for example `BuiltinIPAddress` or `LineageSource`) previously kept the async base in its sync output, so its `save`, `delete` and `create` methods were typed as async and a correct sync call was reported as a missing `await`. Regenerate with `infrahubctl protocols`: sync classes that inherited an async base will now expose the sync methods, which may surface new type errors in code that relied on the old async signatures. ([#1276](https://github.com/opsmill/infrahub-sdk-python/issues/1276))
- Fixed `infrahubctl generator`, which exited with `The node doesn't have an attribute for name` instead of running when the target group contained members of a kind without a `name` attribute. The generator definition parameters are now resolved the same way Infrahub resolves them when it runs a generator, so those targets work and every declared parameter reaches the query instead of only the first one. ([#1289](https://github.com/opsmill/infrahub-sdk-python/issues/1289))
- Fixed `infrahubctl generator`, `transform` and `check` failing with `BranchNotFoundError` when run without `--branch` while the active local Git branch did not exist in Infrahub. ([#1290](https://github.com/opsmill/infrahub-sdk-python/issues/1290))
- Fixed a requested branch being replaced by the local Git branch when `default_branch_from_git` is enabled. This affected `client.clone(branch=...)`, generators and transforms created with `branch=...`, and the `--branch` option of `infrahubctl`. Calls that did not pass a branch went to the Git branch, so a generator run with `--branch` could read from the requested branch and create or update nodes on the Git branch. ([#1295](https://github.com/opsmill/infrahub-sdk-python/issues/1295))
- Corrected the return type annotations of `rebase()` and `validate()` on both `InfrahubClient.branch` and `InfrahubClientSync.branch`. They were declared as `-> BranchData` but have always returned the mutation's `ok` boolean, so the annotations now read `-> bool` to match the actual behaviour and align with `merge()`. ([#1308](https://github.com/opsmill/infrahub-sdk-python/issues/1308))
- Fixed `get_diff_summary()` reporting its request under the GraphQL `operationName` `GetDiffTree`, the same name used by `get_diff_tree()`. The summary query now sends `GetDiffSummary`, so the two methods are distinguishable in server-side query logs, traces, and observability tooling keyed on `operationName`. ([#1313](https://github.com/opsmill/infrahub-sdk-python/issues/1313))
- Fixed `fetch()` raising `ValueError` on the `ancestors` and `descendants` of a node that was retrieved without them, on both the async and the sync client. ([#1425](https://github.com/opsmill/infrahub-sdk-python/issues/1425))
- A `from_pool` request is sent once: after a successful save, the next update no longer sends it again.
- A client authenticating with an API token no longer replays a request after a 401 that reports an expired token. Only a client configured with a username and password can obtain a new token, so on the request paths that retry automatically the retry sent the same rejected token a second time, doubling the cost of the failure. Streaming downloads never retried and are unaffected.
- A file download answered with HTTP 404 now raises `NodeNotFoundError` whatever the response body contains. Previously a body that was not a JSON object - an HTML error page from an intermediary, an empty body, or a JSON array - escaped as a raw `json.JSONDecodeError` or `AttributeError` instead.
- An attribute created with both `value` and `from_pool` now sends both, so the number pool tracks the given number instead of allocating a new one.
- Fixed `fetch()` on a cardinality-many relationship that was not loaded, such as `children`, replacing the node in the client store with a copy that has no attribute values, on both the async and the sync client. `fetch()` on a node that has not been saved now raises `UninitializedError` instead of `ValueError: At least one filter must be provided to get()`; code that catches `ValueError` for this case must catch `UninitializedError` instead.
- Fixed an `AttributeError` escaping the client when a 401 response carried a body that was valid JSON but not an object, such as the bare array or string a proxy or gateway may return. The silent token refresh now treats any body it cannot read as an envelope as carrying no refresh signal, and the request surfaces `AuthenticationError` as it does for every other unreadable 401.
- Fixed peers given as `RelatedNode` objects, such as a peer taken from another node's relationship, being stored with the `RelatedNode` object as their ID, which made the save request invalid and made `remove()` remove nothing. This affected lists of peers for a cardinality-many relationship, `add()` and `remove()` on a cardinality-many relationship, and assignment to a cardinality-one relationship.
- Parts of the SDK no longer fail to import on a plain `pip install infrahub-sdk`.

  `infrahub_sdk.template`, `infrahub_sdk.yaml`, `infrahub_sdk.spec`, `infrahub_sdk.transfer` and `infrahub_sdk.protocols_generator` import Jinja2, PyYAML and rich, but those three were only installed by the `ctl` extra. Using any of them without that extra raised `ModuleNotFoundError`, even though none of it is CLI-specific: `template` renders your Transforms, and rich supplies the traceback types carried in Jinja error reporting.

  All three are now installed with the SDK itself, so a plain install grows from 19 to 26 packages. The `ctl` extra is correspondingly smaller and now covers only what `infrahubctl` genuinely needs.
- Protocols generated for a hierarchical kind no longer declare `parent` and `children` twice. When the schema already exposes them as relationships, which is the case for any schema read from the API, they were emitted once from the relationship list and once more from the hierarchy, and the second pair overrode the first. Regenerate with `infrahubctl protocols` to drop the duplicates.
- Two declared lower bounds were wrong and have been corrected.

  `typer` now requires `>=0.16.0`, up from `>=0.15.0`. Combined with the `click>=8.3` the SDK already required, typer 0.15 crashed on any `infrahubctl --help` with `TypeError: Parameter.make_metavar() missing 1 required positional argument`, because click 8.3 changed that signature and typer only adapted in 0.16. The old floor advertised a combination that could not work.

  `Jinja2` now requires `>=3.1.5`, up from `>=3`. On 3.1.4 and earlier, template error reporting points at the wrong template when a nested template uses an undefined variable, and omits the source path when an imported template is missing.

  If you pin either package below its new floor, installing the SDK now fails while resolving instead of breaking once you run it.
- `GraphQLError` and every exception under it now survive `pickle` and `copy.deepcopy` intact. An exception that crosses a process boundary - a task queue, a parallel test runner, a process pool - previously came back wrong in one of two ways, because Python rebuilds an exception by calling its class with the message as a lone positional argument.

  `GraphQLError` takes the server's error list first, so that call filed the message under `errors` and the message a caller read came back as the placeholder built from it: `An error occurred while executing the GraphQL Query None, UNIQUENESS_VIOLATION: ...` in place of the real one. The per-code classes take their payload fields as required keyword arguments, so the same call raised `TypeError: __init__() takes 1 positional argument but 2 were given` and the original failure was lost entirely.

  Both are fixed at the root of the GraphQL branch, so the type, the message, the payload attributes, `code`, `http_status`, `extensions`, `errors`, `query` and `variables` all come back as they went in, and an `except` clause still catches a restored exception by its own class.

  `NodeNotFoundError`, `BranchNotFoundError` and `SchemaNotFoundError` were affected more quietly: their attributes and `str()` came back correct, but `exc.args` was rebuilt as the class's own default sentence rather than the message the exception was raised with. `AuthenticationError`, whose constructor takes the message first, was the only one unaffected.
- `infrahubctl` no longer deletes bracketed text from an error message. A message such as `The requested branch was not found on the server [main]` was printed without the branch name, because rich read the brackets as a style tag. Everything the shared error handler prints is now escaped, including the traceback the fallback branch emits. Affects branch, schema, and node lookup misses, authentication failures, HTTP transport failures, and the fallback handler.
- `infrahubctl` no longer exits non-zero with no output when a GraphQL failure arrives in a shape the SDK cannot read as an error envelope. `infrahubctl run`, `infrahubctl validate graphql-query`, and every command wrapped by the shared error handler now fall back to printing the exception's message, which keeps the server's payload verbatim.

### Housekeeping

- Added two CI jobs covering the declared dependency ranges, which the existing test matrix never exercised because it installs exactly what `uv.lock` pins. One re-resolves at the declared lower bounds and runs the unit tests; the other builds the wheel and confirms it installs, imports and runs the CLI on every supported Python with a fresh resolution. Upper bounds are tracked separately, since any upstream release could otherwise turn an unrelated pull request red.
- Added unit tests over the packaging metadata so the declared dependencies stay honest. They check that every requirement has a lower bound, that the `all` extra keeps covering the other extras, and that the packages the SDK imports and the packages it declares match each other.
- Pinned Rich's colour and width for the test suite from `pytest_configure`, so CLI-output assertions render identically regardless of the developer's `FORCE_COLOR`/`COLUMNS` environment.
- Routed the two remaining `existing_group.members.peer_ids` accesses in `infrahub_sdk/query_groups.py` through the typed `_get_relationship_many(name="members")` accessor, removing the last two `# type: ignore[union-attr]` suppressions in that module. Internal typing hygiene with no behavioural change.

## [1.23.2](https://github.com/opsmill/infrahub-sdk-python/tree/v1.23.2) - 2026-09-08

### Added

- With `retry_on_failure` enabled, the client now retries every transient failure, not only connection errors: dropped or timed-out connections, HTTP `500`/`502`/`503`/`504` responses, and GraphQL errors the server flags with one of those statuses, on every request path. Retries use exponential backoff with jitter (`retry_delay` up to the new `retry_max_delay`), `retry_status_codes` tunes what counts as transient, and `max_retry_duration=0` retries indefinitely.

## [1.23.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.23.1) - 2026-08-28

### Fixed

- Fixed `client.branch.validate()` and `infrahubctl branch validate`, which raised a `GraphQLError` against every supported Infrahub server because the mutation requested a `messages` field that was removed from `BranchValidate` in Infrahub 1.1.0. ([#1263](https://github.com/opsmill/infrahub-sdk-python/issues/1263))
- The queries generated by `all()`, `filters()`, `get()` and relationship `fetch()` no longer request `count` on cardinality-many relationships. The SDK never read that value, and Infrahub resolved it with one extra database query per returned node and per relationship, on top of preventing the peer reads of those nodes from being batched into a single query.

## [1.23.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.23.0) - 2026-08-19

### Removed

- Removed `client.branch.diff_data()` from both the async and sync clients. The method relied on a `GET /api/diff/data` REST endpoint that does not exist in Infrahub, so every call returned a 404. Use `client.get_diff_tree()` to retrieve the full diff of a branch against its base branch, or `client.get_diff_summary()` for the list of changed nodes; both use the `DiffTree` GraphQL query. ([#325](https://github.com/opsmill/infrahub-sdk-python/issues/325))

### Added

- Added the Infrahub deployment ID to the `infrahubctl info` command output and a `get_server_information()` method (returning the server version and deployment ID) on the async and sync clients. ([#1017](https://github.com/opsmill/infrahub-sdk-python/issues/1017))
- Added transparent retry of HTTP 429 (rate-limited) responses on both `InfrahubClient` and `InfrahubClientSync`. Retries use jittered exponential backoff and honour a server-provided `Retry-After` header (delta-seconds or HTTP-date). The behaviour is tunable through four new `Config` fields (`rate_limit_retry_enabled`, `rate_limit_max_retries`, `rate_limit_backoff_base`, `rate_limit_backoff_max`), and a new `RateLimitError` exception is raised when retries are exhausted. ([#1124](https://github.com/opsmill/infrahub-sdk-python/issues/1124))
- Added support for tagging SDK requests with a priority via a new `X-Priority` header. A `Priority` enum (`high`, `medium`, `low`) is available from `infrahub_sdk.constants`; set `Config.priority` (env var `INFRAHUB_PRIORITY`) for a client-wide default emitted on every request, or pass `priority=` to individual operations to override it per request. When unset, no header is sent. Works identically on `InfrahubClient` and `InfrahubClientSync`. ([#1151](https://github.com/opsmill/infrahub-sdk-python/issues/1151))
- Add `infrahubctl schema format` command, an opinionated offline formatter that normalises the key ordering of schema files. Optional flags can also strip redundant default values (`--strip-defaults`), sort attributes/relationships by `order_weight` (`--sort-by-order-weight`), and backfill a missing `order_weight` (`--backfill-order-weight`).
- Added `retry()` and `cancel()` methods to the task manager. The `Task` model now exposes `available_actions` along with `can_retry` / `can_cancel` helpers.
- Added an opt-in `include_diagnostics` flag to the task manager's `all()`, `filter()`, and `get()` methods. When enabled, tasks expose an `error` field, and `webhook-send` tasks are returned as `WebhookDeliveryTask` instances carrying `http_request` / `http_response` delivery details.
- Added support for the new `IPAddress` attribute kind. Values are exposed as bare `ipaddress.IPv4Address`/`IPv6Address` objects (no prefix) and serialized to a bare-address string when writing, alongside the existing `IPHost` and `IPNetwork` kinds.
- The JSON schema generated for `.infrahub.yml` now warns when a definition has not said what it depends on, so YAML language servers flag it while the file is being edited. A Python transform or generator definition with no `watch` block is flagged, and so is a `watch` value that is not a mapping, including the bare `watch:` that parses as null and records nothing. Both warnings are advisory only: the models still accept every one of those forms. An empty `watch: {}` or `files: []` stays clean, since either one records that the author checked and nothing beyond what Infrahub detects needs watching. The generated schema also picks up the `watch` block on generator definitions, which it was previously rejecting as an unknown property.
- The request priority (`X-Priority` header) can now be carried on the client's `RequestContext` via a new `priority` field, alongside the existing client-wide `Config.priority` default and per-call `priority=` override. Resolution precedence is per-call `priority=` > `request_context.priority` > `Config.priority` > no header. The priority is emitted as a header only and is never included in the mutation body. Works identically on `InfrahubClient` and `InfrahubClientSync`.
- Import `pyarrow` lazily in the line-delimited JSON importer so that `infrahubctl` commands other than `object load` no longer require the `ctl` extra (and its heavy `pyarrow` dependency) to be installed.

### Changed

- Paginated queries generated by `all()`, `filters()`, `get()` and resource pool allocation lookups now pass `offset` and `limit` as GraphQL variables instead of inlining them in the query text. The query document stays identical across pages, allowing the Infrahub server to reuse its cached query analysis, and the query is now rendered once per call instead of once per page. `generate_query_data` also accepts variable placeholder strings (for example `"$offset"`) for its `offset` and `limit` arguments.
- Raised the default `Config.rate_limit_max_retries` from 5 to 10, so a request shed with HTTP 429 keeps retrying (honouring `Retry-After`) for longer before raising `RateLimitError`. This lets background work ride out a longer burst of server-side backpressure. Callers that prefer to give up sooner can lower the value.
- The hand-maintained schema models in `infrahub_sdk.schema` are now backed by the generated write/read contract (`infrahub_sdk.schema.generated`). Public names, import paths, and behavior methods are unchanged, but a few defaults and constraints now match the server contract:

  - `AttributeKind.STRING` has been removed. It was deprecated and `kind="String"` was already rejected server-side; use `AttributeKind.TEXT` instead.
  - Write and read models drop unknown fields silently (`extra="ignore"`). A submitted field that is not part of the write contract — read-level, internal, or a typo — is dropped rather than rejected, and a read model tolerates additional fields returned by a newer server.
  - Write-model defaults now match the server contract: relationship `min_count`/`max_count` default to `0` (was `None`), node `branch` defaults to `"aware"`, `generate_profile` defaults to `True`, and `generate_template` defaults to `False`. This changes the round-trip output of programmatically-built schemas.

  Constructing `AttributeSchema(name=..., kind=AttributeKind.TEXT, ...)`, `NodeSchema`, `GenericSchema`, `RelationshipSchema`, `SchemaRoot`, and the read-side `*API` models continues to work unchanged.

## [1.22.3](https://github.com/opsmill/infrahub-sdk-python/tree/v1.22.3) - 2026-08-19

### Fixed

- Register the `infrahub_integration` pytest marker under its real name. It was registered as `infrahub_integraton`, so integration tests raised a `PytestUnknownMarkWarning` on every run and failed to collect under `--strict-markers`. ([#1231](https://github.com/opsmill/infrahub-sdk-python/issues/1231))
- Fixed the `load` and `check` command descriptions in the `infrahubctl schema` help output and generated docs, which were cut off mid-sentence.

## [1.22.2](https://github.com/opsmill/infrahub-sdk-python/tree/v1.22.2) - 2026-07-27

### Added

- Added a `--dependencies` flag to `infrahubctl marketplace get`. When downloading a schema or a collection, it now also resolves and downloads the schemas they depend on, via the marketplace API. Dependencies are grouped by the collection they belong to: prerequisite collections (and, for a single schema, dependencies that are members of a collection) are placed in their own `<collection>/` directory, while dependencies that belong to no collection land in the output root. Referenced kinds the marketplace cannot resolve are reported as unresolved dependencies. A schema that already exists in the output directory is reconciled to a single file rather than duplicated across directories — kept by default, or overwritten with the new `-y`/`--yes` flag. ([#1117](https://github.com/opsmill/infrahub-sdk-python/issues/1117))
- Added `infrahubctl marketplace list`, `search`, and `show` commands for browsing schemas and collections on the Infrahub Marketplace.

### Fixed

- Branch names containing URL-significant characters (such as `#` or `/`) are now percent-encoded in the GraphQL URL, so requests against those branches resolve correctly instead of returning a 404. ([#1209](https://github.com/opsmill/infrahub-sdk-python/issues/1209))
- Fixed several cases where `InfrahubClientSync` had drifted from `InfrahubClient`: sync `branch.merge` now applies the same 120-second minimum timeout floor as the async client, and sync `create(allow_upsert=True)` now excludes the `hfid` from the mutation payload to avoid server-side upsert overhead. Also corrected an incorrect "feature not supported" message on async artifact fetch and a resource-pool error message typo.

### Housekeeping

- Replaced `markdownlint-cli2` with [rumdl](https://github.com/rvben/rumdl) for markdown linting. This removes the Node.js/npm dependency for the markdown check, speeds up linting, and consolidates the configuration into `pyproject.toml` under `[tool.rumdl]`. ([#1138](https://github.com/opsmill/infrahub-sdk-python/issues/1138))

## [1.22.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.22.1) - 2026-07-03

### Added

- Added a `shortest_paths_only` parameter to `InfrahubClient.traverse_paths()` and its sync equivalent (default `None`, deferring to the server). Set it to `False` to return all loopless paths up to `max_paths` instead of only the shortest one(s); previously path traversal always returned the shortest path(s) because the flag could not be set. `PathTraversalResult` now also parses `truncated_at_depth`, which is set when the search stopped at `max_depth` before exhausting the graph and `None` when it completed within budget. ([#1119](https://github.com/opsmill/infrahub-sdk-python/issues/1119))

### Fixed

- Clarified the `ValidationError` raised when calling `save(allow_upsert=True)` on a node whose human-friendly identifier includes a `CoreNumberPool`-sourced attribute. The message now explains that the pool assigns a new value on every creation, so the HFID is never stable and the upsert would silently create a duplicate on each run, and points to the idempotent alternatives (look the node up by a stable field and reuse it, or set an explicit id). The resource manager guide was updated to match.

## [1.22.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.22.0) - 2026-06-23

### Added

- Added `query_name` parameter to `all()`, `filters()`, `count()` and `get()` methods in `InfrahubClient` and `InfrahubClientSync` to be used as meaningful GraphQL operation name for observability ([#923](https://github.com/opsmill/infrahub-sdk-python/issues/923))
- Add `infrahubctl graphql query-report` to analyze a GraphQL query and report whether it targets unique nodes, which controls whether Infrahub limits artifact regeneration to changed nodes or regenerates all artifacts on any relevant node change. Supports `--online` to fetch the query from the server by name.
- Added `OrderByEntry` and an `Order.by` field so query results can be ordered by attributes, related-node attributes, or node metadata, e.g. `Order(by=[OrderByEntry(field="name__value", direction=OrderDirection.DESC)])`. The `Order.node_metadata` field is deprecated; use `by` with the `node_metadata__created_at` / `node_metadata__updated_at` fields instead.
- Added graph traversal support for Infrahub 1.10: `InfrahubClient.traverse_paths()` (shortest path(s) between two nodes), `InfrahubClient.reachable_nodes()` (nodes of given kinds reachable from a source), and `InfrahubClient.path_exists()` (boolean convenience for checks) — all with sync equivalents. Source and destination accept either a node id or an `InfrahubNode`; kind filters accept kind strings or protocol classes; each `PathNode` in the result exposes `.fetch()` to resolve the full node (store-backed). Calling these against a pre-1.10 server raises a clear `VersionNotSupportedError`.

### Fixed

- Calling `.save(allow_upsert=True)` on a node whose human-friendly identifier contains a CoreNumberPool-sourced attribute now raises a clear `ValidationError` instead of crashing with an opaque backend error. ([#339](https://github.com/opsmill/infrahub-sdk-python/issues/339))
- `RelatedNode`, `RelatedNodeSync`, `RelationshipManager` and `RelationshipManagerSync` are now generic over their peer type, and `infrahubctl protocols` parameterises generated relationships accordingly (e.g. `device: RelatedNode[NetworkDevice]`, `interfaces: RelationshipManager[NetworkInterface]`).

  Traversing a relationship via `.peer`, `.peers` or indexing now preserves the peer's type instead of collapsing to the dynamic `InfrahubNode`, so chains such as `device.rack.peer.name.value` type-check under mypy/ty without casts. Existing un-parameterised `RelatedNode` / `RelationshipManager` usage is unaffected — the peer type defaults to `InfrahubNode` / `InfrahubNodeSync`, preserving current behaviour. ([#1063](https://github.com/opsmill/infrahub-sdk-python/issues/1063)) ([#1063](https://github.com/opsmill/infrahub-sdk-python/issues/1063))
- Cardinality-one relationships in generated protocols are now typed with a `RelationshipAttribute[...]` descriptor. It still reads back as a typed `RelatedNode[Peer]` (so `.peer` keeps the peer type), but it accepts assignment of an id string, an HFID, a peer node, or `None` — mirroring the runtime `InfrahubNode.__setattr__`, which wraps the assigned value in a `RelatedNode`.

  Previously relationships were typed read-only as `RelatedNode`, so the documented way of setting a relationship (`node.rel = "<id>"` or `node.rel = peer_node`) failed under mypy/ty with an `assignment` error. The descriptor only appears in generated protocols and is never instantiated at runtime.

  Because the new typing lives in the generated protocols, existing projects must regenerate them with `infrahubctl protocols` to pick up the change — it does not take effect for already-generated protocol files. ([#1064](https://github.com/opsmill/infrahub-sdk-python/issues/1064)) ([#1064](https://github.com/opsmill/infrahub-sdk-python/issues/1064))
- Calling `.save(allow_upsert=True)` on a node hydrated by `from_graphql` no longer silently clears optional one-cardinality relationships that the GraphQL response didn't fetch. Explicitly assigning `node.rel = None` still clears the relationship. ([#1080](https://github.com/opsmill/infrahub-sdk-python/issues/1080))
- Send the GraphQL operation name as `operationName` in the request payload so tracing and observability tools can identify each query.

## [1.21.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.21.1) - 2026-06-05

### Changed

- `infrahubctl marketplace get --collection` now downloads each member schema individually into a `<output_dir>/<collection name>/<schema name>.yml` layout (for example `schemas/base-schemas/dcim.yml`), instead of dumping version-suffixed files flat into the output directory. Filenames no longer carry the version, matching single-schema downloads, so re-downloading a collection overwrites cleanly rather than accumulating stale versions. If two members share a schema name across namespaces, those members are written to `<output_dir>/<collection name>/<namespace>/<schema name>.yml` instead of overwriting each other. ([#1057](https://github.com/opsmill/infrahub-sdk-python/issues/1057))

### Fixed

- Fix `infrahubctl` printing a spurious `Error: 1` and Python traceback after the human-readable error message when a command exits with `typer.Exit`. The CLI now exits cleanly with only the intended error output. ([#1047](https://github.com/opsmill/infrahub-sdk-python/issues/1047))

## [1.21.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.21.0) - 2026-05-29

### Added

- Add `infrahubctl marketplace get` for fetching schemas and collections from the Infrahub Marketplace. Auto-detects schemas vs collections by namespace/name, supports `--version` for pinning, `--collection` to force the collection path, `--stdout` to stream content for piping (status messages on stderr), and `--marketplace-url` / `INFRAHUB_MARKETPLACE_URL` to point at staging or local instances. ([#952](https://github.com/opsmill/infrahub-sdk-python/issues/952))

### Changed

- Change default value of `sync_with_git` parameter in `branch.create()` from `True` to `False` to match UI behavior. ([#224](https://github.com/opsmill/infrahub-sdk-python/issues/224))

### Fixed

- Improve error message when a single node is passed to a cardinality-many relationship. ([#174](https://github.com/opsmill/infrahub-sdk-python/issues/174))

## [1.20.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.20.1) - 2026-05-20

### Added

- Added SHA-1 idempotency primitives for `CoreFileObject` nodes:

  - `InfrahubNode.matches_local_checksum(source)` / sync variant — compare a local `bytes | Path | BinaryIO` source against the node's server-stored checksum without invoking a transfer.
  - `InfrahubNode.upload_if_changed(source, name=None)` / sync variant — stage + save only when the local source differs from the server, returning an `UploadResult(was_uploaded, checksum)` dataclass.
  - `download_file(..., skip_if_unchanged=True)` — short-circuit the download when `dest` already exists on disk with a matching SHA-1. Returns `0` bytes written when skipped.

  A shared `sha1_of_source` helper (streaming, 64 KiB chunks) centralises the hashing convention in `infrahub_sdk.file_handler`.

### Fixed

- Skip mandatory field validation during object loading when `object_profile` is specified. ([#908](https://github.com/opsmill/infrahub-sdk-python/issues/908))
- Render schema rejections originating in an `extensions:` block as a readable one-line message in `infrahubctl schema load`, instead of crashing with `ValueError: invalid literal for int()`. ([#1007](https://github.com/opsmill/infrahub-sdk-python/issues/1007))
- Add `MERGING` branch status so that a merging branch can still be correctly retrieved. ([#1037](https://github.com/opsmill/infrahub-sdk-python/issues/1037))

## [1.20.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.20.0) - 2026-04-24

### Removed

- Removed the deprecated `raise_for_error` argument from `execute_graphql`, `query_gql_query`, `get_diff_summary`, `allocate_next_ip_address`, and `allocate_next_ip_prefix` client methods. HTTP errors are now always raised via `resp.raise_for_status()`.

### Added

- Add `infrahubctl schema export` command to export schemas from Infrahub. ([#151](https://github.com/opsmill/infrahub-sdk-python/issues/151))
- Add `artifact_content`, `file_object_content`, `from_json`, and `from_yaml` Jinja2 filters for artifact content composition in templates.

### Changed

- Replace `FilterDefinition.trusted: bool` with flag-based `ExecutionContext` model (`CORE`, `WORKER`, `LOCAL`) for context-aware template validation. `validate()` now accepts an optional `context` parameter. Backward compatible.

### Fixed

- Allow direct assignment of authentication method to the configuration to override settings from environment variables. ([#654](https://github.com/opsmill/infrahub-sdk-python/issues/654))
- Corrected protocol typing for IPHost.value IPAddress -> IPInterface ([#891](https://github.com/opsmill/infrahub-sdk-python/issues/891))
- Generate protocols so that optional attributes with a default value are rendered as required (not nullable). ([#894](https://github.com/opsmill/infrahub-sdk-python/issues/894))
- Fixed `ObjectStore.get()` and `ObjectStore.upload()` silently swallowing non-2xx HTTP errors instead of raising them. ([#958](https://github.com/opsmill/infrahub-sdk-python/issues/958))
- Skip mandatory field validation during object loading when `object_template` is specified.

## [1.19.0](https://github.com/opsmill/infrahub-sdk-python/tree/v1.19.0) - 2026-03-16

### Added

- Added support for FileObject nodes with file upload and download capabilities. New methods `upload_from_path(path)` and `upload_from_bytes(content, name)` allow setting file content before saving, while `download_file(dest)` enables downloading files to memory or streaming to disk for large files. ([#ihs193](https://github.com/opsmill/infrahub-sdk-python/issues/ihs193))
- Python SDK API documentation is now generated directly from the docstrings of the classes, functions, and methods contained in the code. ([#201](https://github.com/opsmill/infrahub-sdk-python/issues/201))
- Added a 'py.typed' file to the project. This is to enable type checking when the Infrahub SDK is imported from other projects. The addition of this file could cause new typing issues in external projects until all typing issues have been resolved. Adding it to the project now to better highlight remaining issues.

### Changed

- Updated branch report command to use node metadata for proposed change creator information instead of the deprecated relationship-based approach. Requires Infrahub 1.7 or above.

### Fixed

- Allow SDK tracking feature to continue after encountering delete errors due to impacted nodes having already been deleted by cascade delete. ([#265](https://github.com/opsmill/infrahub-sdk-python/issues/265))
- Fixed Python SDK query generation regarding from_pool generated attribute value ([#497](https://github.com/opsmill/infrahub-sdk-python/issues/497))

## [1.18.1](https://github.com/opsmill/infrahub-sdk-python/tree/v1.18.1) - 2026-01-08

### Fixed

- Reverted #723 (Fix code for HFID casting of strings that aren't UUIDs)

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
