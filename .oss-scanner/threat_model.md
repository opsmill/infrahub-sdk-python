# Infrahub Python SDK threat model

## What the SDK does

The SDK is the Python library and command-line tool (`infrahubctl`) that people and programs use to read and write
data in an Infrahub server. Infrahub itself uses it in its task workers to run the transforms, checks and generators
stored in Git repositories, and to render Jinja2 templates. The Infrahub Ansible collection also uses it.

## Where untrusted input enters

- Responses from the Infrahub server (GraphQL results, files, artifacts), in particular when the SDK uses them to
  build file paths or write files (`infrahub_sdk/file_handler.py`, `infrahub_sdk/object_store.py`,
  `infrahub_sdk/transfer/`).
- Jinja2 templates passed as strings (`infrahub_sdk/template/`). Infrahub uses these for computed attributes and
  display labels written by accounts that can change the schema, and renders them in a sandboxed Jinja2 environment.
- Files that `infrahubctl` reads: `.infrahub.yml`, schema files, object files and export archives.
- The credentials the SDK holds (API token, username and password, from configuration or environment variables).

## What is trusted

- Python code in a Git repository (transforms, checks, generators) runs without restrictions. This is by design.
- Jinja2 template files in a Git repository are rendered without a sandbox. This is by design: repository content is
  trusted like code.

## Components in scope

- `infrahub_sdk/`, including `infrahub_sdk/ctl/` (`infrahubctl`) and `infrahub_sdk/pytest_plugin/`.

## Out of scope

- `tests/`, `docs/`, `dev/`, `specs/` and `tasks.py`.
- `infrahub_sdk/protocols.py`, which is generated.
- Vulnerabilities in third-party dependencies, unless the SDK uses the dependency in an unsafe way.

## How we rate severity

- **Critical:** code execution on the machine that runs the SDK, caused by data from the server.
- **High:** escaping the Jinja2 sandbox for string templates, sending credentials to a host other than the
  configured server or writing them to logs, and writing files outside the directory the caller chose.
- **Medium:** denial of service caused by a server response, and TLS certificate checks being skipped even though
  the configuration turns them on.
- **Low:** missing hardening without a demonstrated impact.

## How to exercise the SDK

- Unit tests: `uv run pytest tests/unit/`.
- The command-line tool: `infrahubctl --help`.
- The integration tests in `tests/integration/` start an Infrahub server in Docker, so they do not run in this image.

## How we would like reports and patches

- One report per root cause.
- Include a proof of concept as a unit test or a short Python script, using a mocked server response where a server
  is needed.
- Patches should be minimal, keep the async and sync clients consistent, and add a test under `tests/unit/` that
  fails without the fix.
