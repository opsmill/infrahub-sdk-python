# Documentation Generation

CLI and SDK documentation is auto-generated from code. Always regenerate after changing commands, config, or public docstrings.

## How to run

```bash
uv run invoke docs-generate    # Generate all docs (CLI + SDK)
uv run invoke docs-validate    # Verify generated docs match committed versions
```

## CLI documentation

Defined in `tasks.py` (`_generate_infrahubctl_documentation`). The process:

1. Deletes all existing `infrahubctl-*.mdx` files in `docs/docs/infrahubctl/`.
2. Iterates `app.registered_commands` and creates a `TyperSingleCommand` for each.
3. Iterates `app.registered_groups` and creates a `TyperGroupCommand` for each.
4. Each command object generates an mdx file via `typer ... utils docs`.

### How it maps to files

- A **root command** named `foo` produces `infrahubctl-foo.mdx` using:
  `uv run typer --func foo infrahub_sdk.ctl.cli_commands utils docs --name "infrahubctl foo"`
- A **subcommand group** named `bar` produces `infrahubctl-bar.mdx` using:
  `uv run typer infrahub_sdk.ctl.bar utils docs --name "infrahubctl bar"`

The group variant documents all subcommands within that group automatically.

### Key implication

Moving a command from root to a group (or vice versa) changes which mdx files get generated. The old files are cleaned up automatically by the glob delete, but the new ones only appear after running `docs-generate`. Always regenerate and commit the result.

## SDK documentation

Other doc generators cover SDK config, compatibility matrix, templates, and API reference. These are independent of CLI structure and are also triggered by `docs-generate`.

## Validation in CI

`docs-validate` diffs the generated output against the committed files. If they don't match, CI fails. This ensures docs stay in sync with code.
