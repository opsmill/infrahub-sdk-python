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

For a **subcommand**, add it to the relevant group's package or module. For example, object subcommands live in `infrahub_sdk/ctl/object/` and are registered on the object app in `__init__.py`.

## Group packages

When a subcommand group has multiple commands, it lives as a package (directory with `__init__.py`) rather than a single module file. The `object` group is the reference example:

```text
infrahub_sdk/ctl/object/
├── __init__.py    # App, callback, load/validate commands, registers CRUD
├── create.py      # create subcommand
├── delete.py      # delete subcommand
├── get.py         # get subcommand
├── update.py      # update subcommand
└── utils.py       # Shared utilities (resolve_node, etc.)
```

Each command file contains a single command function. Shared logic goes in `utils.py`. The `__init__.py` wires everything together by importing and registering commands on the group's `AsyncTyper` app. Other groups that grow beyond a single file should follow this same pattern.

## Decorators

- `@catch_exception(console=console)` wraps commands for consistent error handling via Rich.
- Async commands work natively thanks to `AsyncTyper`.

## Design rules

**Always check if a new command belongs in an existing group before adding it at the root.** A command that operates on a specific resource type (objects, branches, schemas, etc.) should go under the matching subgroup, not at the top level. Root-level commands are reserved for cross-cutting or standalone operations (e.g. `run`, `version`, `info`).

When in doubt, look at what the command acts on and find the group that matches. For example, anything that creates, reads, updates, or deletes Infrahub objects belongs under `object`, not at the root.
