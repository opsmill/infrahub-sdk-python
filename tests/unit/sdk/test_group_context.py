import inspect
from collections.abc import Callable

import pytest

from infrahub_sdk.query_groups import InfrahubGroupContext, InfrahubGroupContextBase, InfrahubGroupContextSync
from infrahub_sdk.schema import NodeSchemaAPI

async_methods = [method for method in dir(InfrahubGroupContext) if not method.startswith("_")]
sync_methods = [method for method in dir(InfrahubGroupContextSync) if not method.startswith("_")]

client_types = ["standard", "sync"]


async def test_method_sanity() -> None:
    """Validate that there is at least one public method and that both clients look the same."""
    assert async_methods
    assert async_methods == sync_methods


@pytest.mark.parametrize("method", async_methods)
async def test_validate_method_signature(
    method: str,
    replace_sync_return_annotation: Callable[[str], str],
    replace_async_return_annotation: Callable[[str], str],
) -> None:
    async_method = getattr(InfrahubGroupContext, method)
    sync_method = getattr(InfrahubGroupContextSync, method)
    async_sig = inspect.signature(async_method)
    sync_sig = inspect.signature(sync_method)
    assert async_sig.parameters == sync_sig.parameters
    assert async_sig.return_annotation == replace_sync_return_annotation(sync_sig.return_annotation)
    assert replace_async_return_annotation(async_sig.return_annotation) == sync_sig.return_annotation


def test_set_properties() -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert context.identifier == "MYID"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"}, delete_unused_nodes=True)
    assert context.identifier == "MYID"
    assert context.params == {"one": 1, "two": "two"}
    assert context.delete_unused_nodes is True


def test_get_params_as_str() -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._get_params_as_str() == "one: 1, two: two"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert not context._get_params_as_str()


def test_generate_group_name() -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert context._generate_group_name() == "MYID"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._generate_group_name() == "MYID-11aaec5206c3dca37cbbcaaabf121550"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._generate_group_name(suffix="xxx") == "MYID-xxx-11aaec5206c3dca37cbbcaaabf121550"


def test_generate_group_description(std_group_schema: NodeSchemaAPI) -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert not context._generate_group_description(schema=std_group_schema)

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._generate_group_description(schema=std_group_schema) == "one: 1, two: two"

    assert std_group_schema.attributes[1].name == "description"
    std_group_schema.attributes[1].max_length = 20
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": "xxxxxxxxxxx", "two": "yyyyyyyyyyy"})
    assert context._generate_group_description(schema=std_group_schema) == "one: xxxxxxxxxx..."
