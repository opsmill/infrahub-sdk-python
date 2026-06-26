from dataclasses import dataclass

import pytest

from infrahub_sdk.enums import OrderDirection
from infrahub_sdk.graphql.renderers import convert_to_graphql_as_string
from infrahub_sdk.types import NodeMetaOrder, Order, OrderByEntry


@dataclass
class OrderRenderCase:
    name: str
    order: Order
    expected: str


ORDER_RENDER_CASES = [
    OrderRenderCase(
        name="disable",
        order=Order(disable=True),
        expected="{ disable: true }",
    ),
    OrderRenderCase(
        name="by-single-default-direction",
        order=Order(by=[OrderByEntry(field="name__value")]),
        expected='{ by: [{ field: "name__value", direction: ASC }] }',
    ),
    OrderRenderCase(
        name="by-single-desc",
        order=Order(by=[OrderByEntry(field="name__value", direction=OrderDirection.DESC)]),
        expected='{ by: [{ field: "name__value", direction: DESC }] }',
    ),
    OrderRenderCase(
        name="by-relationship-and-metadata",
        order=Order(
            by=[
                OrderByEntry(field="owner__name__value", direction=OrderDirection.ASC),
                OrderByEntry(field="node_metadata__created_at", direction=OrderDirection.DESC),
            ]
        ),
        expected=(
            '{ by: [{ field: "owner__name__value", direction: ASC }, '
            '{ field: "node_metadata__created_at", direction: DESC }] }'
        ),
    ),
    OrderRenderCase(
        name="deprecated-node-metadata-still-works",
        order=Order(node_metadata=NodeMetaOrder(created_at=OrderDirection.DESC)),
        expected="{ node_metadata: { created_at: DESC } }",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in ORDER_RENDER_CASES])
def test_order_renders_to_graphql(case: OrderRenderCase) -> None:
    assert convert_to_graphql_as_string(value=case.order) == case.expected


def test_order_by_and_node_metadata_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="'by' and 'node_metadata' are mutually exclusive"):
        Order(
            by=[OrderByEntry(field="name__value")],
            node_metadata=NodeMetaOrder(created_at=OrderDirection.ASC),
        )
