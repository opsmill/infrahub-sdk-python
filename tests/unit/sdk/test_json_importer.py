"""How `execute_batches` reports a failed task when it was told to keep going."""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from infrahub_sdk import InfrahubClient
from infrahub_sdk.batch import InfrahubBatch
from infrahub_sdk.exceptions import GraphQLError
from infrahub_sdk.transfer.importer.json import LineDelimitedJSONImporter
from infrahub_sdk.transfer.schema_sorter import InfrahubSchemaTopologicalSorter
from tests.helpers.cli import remove_ansi_color


def recording_console() -> Console:
    return Console(record=True, file=StringIO(), width=200)


def importer(console: Console) -> LineDelimitedJSONImporter:
    return LineDelimitedJSONImporter(
        client=InfrahubClient(),
        topological_sorter=InfrahubSchemaTopologicalSorter(),
        continue_on_error=True,
        console=console,
    )


def batch_raising(exc: Exception) -> InfrahubBatch:
    async def failing_task() -> None:
        raise exc

    batch = InfrahubBatch(return_exceptions=True)
    batch.add(task=failing_task)
    return batch


async def test_an_error_entry_without_a_message_does_not_stop_the_import() -> None:
    """The entry is rendered whole rather than raising a KeyError out of the keep-going branch."""
    console = recording_console()
    exc = GraphQLError(errors=[{"path": ["TestPersonCreate"], "extensions": {"code": "UNDEFINED_ERROR"}}])

    results = await importer(console=console).execute_batches([batch_raising(exc)])

    output = remove_ansi_color(console.file.getvalue())  # type: ignore[attr-defined]
    assert results == []
    assert "1 failures" in output
    assert "TestPersonCreate" in output, "the entry the server sent still reaches the user"


async def test_an_error_entry_with_a_message_is_reported_by_that_message() -> None:
    console = recording_console()
    exc = GraphQLError(errors=[{"message": "boom", "path": ["TestPersonCreate"]}])

    await importer(console=console).execute_batches([batch_raising(exc)])

    assert "boom" in remove_ansi_color(console.file.getvalue())  # type: ignore[attr-defined]


async def test_a_failure_still_raises_when_not_continuing_on_error() -> None:
    console = recording_console()
    importer_stopping = LineDelimitedJSONImporter(
        client=InfrahubClient(),
        topological_sorter=InfrahubSchemaTopologicalSorter(),
        continue_on_error=False,
        console=console,
    )
    exc = GraphQLError(errors=[{"path": ["TestPersonCreate"]}])

    with pytest.raises(GraphQLError, match="An error occurred while executing the GraphQL Query"):
        await importer_stopping.execute_batches([batch_raising(exc)])
