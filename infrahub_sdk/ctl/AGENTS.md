# infrahub_sdk/ctl/AGENTS.md

CLI tool (`infrahubctl`) built with Typer/AsyncTyper.

## Command Pattern

```python
from rich.console import Console
from ..async_typer import AsyncTyper
from ..ctl.client import initialize_client
from ..ctl.utils import catch_exception
from .parameters import CONFIG_PARAM

console = Console()
app = AsyncTyper()

@app.command(name="my-command")
@catch_exception(console=console)
async def my_command(
    path: str = typer.Option(".", help="Path to file"),
    branch: Optional[str] = None,
    _: str = CONFIG_PARAM,  # Always include, even if unused
):
    client = initialize_client(branch=branch)
    # implementation using Rich for output
    console.print(Panel("Result", title="Success"))
```

## File Organization

```text
infrahub_sdk/ctl/
├── cli_commands.py    # Entry point, registers subcommands
├── client.py          # initialize_client(), initialize_client_sync()
├── utils.py           # catch_exception decorator, parse_cli_vars
├── parameters.py      # CONFIG_PARAM and shared parameters
├── branch.py          # Branch subcommands
├── schema.py          # Schema subcommands
└── object.py          # Object subcommands
```

## Registering Commands

```python
# In cli_commands.py
from ..ctl.branch import app as branch_app
app.add_typer(branch_app, name="branch")

# Or for top-level commands
from .exporter import dump
app.command(name="dump")(dump)
```

## Boundaries

✅ **Always**

- Use `@catch_exception(console=console)` decorator
- Include `CONFIG_PARAM` in all commands
- Use `initialize_client()` for client creation
- Use Rich for output (tables, panels, console.print)

🚫 **Never**

- Use plain `print()` statements
- Instantiate `InfrahubClient` directly (use `initialize_client`)
- Forget error handling decorator
