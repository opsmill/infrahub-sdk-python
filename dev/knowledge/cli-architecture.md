# CLI Architecture

The `infrahubctl` CLI is built with [Typer](https://typer.tiangolo.com/) via a custom `AsyncTyper` subclass that supports async command functions.

## Entry point

The main Typer app lives in `infrahub_sdk/ctl/cli_commands.py`. It is re-exported through `infrahub_sdk/ctl/cli.py` which adds the `infrahubctl` entry point name.

## Command hierarchy

Commands are organized in two tiers:

- **Root commands** are registered directly on the main app with `app.command()`. These are standalone operations that don't belong to a logical group (e.g. `dump`, `load`, `check`, `render`, `run`, `transform`, `protocols`, `version`, `info`).
- **Subcommand groups** are separate `AsyncTyper()` instances registered with `app.add_typer(sub_app, name="group")`. Each group lives in its own module under `infrahub_sdk/ctl/`. Current groups: `branch`, `schema`, `validate`, `repository`, `menu`, `object`, `graphql`, `task`.

## Adding a new command

For a **root command**, define the function in the appropriate module and register it in `cli_commands.py`:

```python
app.command(name="mycommand")(my_function)
```

For a **subcommand**, add it to the relevant group's module. For example, object subcommands go in `infrahub_sdk/ctl/object.py` or in dedicated files under `infrahub_sdk/ctl/commands/` and are registered on the object app.

## The `commands/` directory

`infrahub_sdk/ctl/commands/` contains modular command implementations that are imported and registered on a group app. This keeps individual command logic separated from the group wiring. Shared utilities live in `commands/utils.py`.

## Decorators

- `@catch_exception(console=console)` wraps commands for consistent error handling via Rich.
- Async commands work natively thanks to `AsyncTyper`.

## Design rules

**Always check if a new command belongs in an existing group before adding it at the root.** A command that operates on a specific resource type (objects, branches, schemas, etc.) should go under the matching subgroup, not at the top level. Root-level commands are reserved for cross-cutting or standalone operations (e.g. `run`, `version`, `info`).

When in doubt, look at what the command acts on and find the group that matches. For example, anything that creates, reads, updates, or deletes Infrahub objects belongs under `object`, not at the root.
