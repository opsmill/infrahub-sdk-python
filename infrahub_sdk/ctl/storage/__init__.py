from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.ctl.storage.encrypt import encrypt_command

app = AsyncTyper()

app.command(name="encrypt")(encrypt_command)


@app.callback()
def callback() -> None:
    """Manage the files that an Infrahub server stores."""
