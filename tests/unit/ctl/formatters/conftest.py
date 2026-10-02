from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk import Config, InfrahubClient
from infrahub_sdk.node import InfrahubNode
from tests.unit.sdk.test_node_field_access import location_payload

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

    from infrahub_sdk.schema import NodeSchemaAPI


@pytest.fixture
def fetched_location(location_schema: NodeSchemaAPI) -> Callable[[Collection[str]], InfrahubNode]:
    """Return a builder of fetched locations whose payload lacks the given fields."""
    client = InfrahubClient(config=Config(address="http://mock"))

    def build(omit: Collection[str]) -> InfrahubNode:
        return InfrahubNode(client=client, schema=location_schema, data=location_payload(omit=omit))

    return build
