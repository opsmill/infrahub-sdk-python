from __future__ import annotations

import pytest

from infrahub_sdk.exceptions import NodeInvalidError, NodeNotFoundError


def test_node_not_found_error_default_message_format() -> None:
    error = NodeNotFoundError(
        branch_name="main",
        node_type="InfraDevice",
        identifier={"name__value": ["bad-device404"]},
    )

    rendered = str(error)
    assert "Unable to find the node in the database." in rendered
    assert "Branch: main" in rendered
    assert "Kind: InfraDevice" in rendered
    assert "Identifier: {'name__value': ['bad-device404']}" in rendered


def test_node_not_found_error_custom_message_format() -> None:
    error = NodeNotFoundError(
        branch_name="feature",
        node_type="InfraInterface",
        identifier={"id": ["abc123"]},
        message="Unable to find the node in the store.",
    )

    rendered = str(error)
    assert "Unable to find the node in the store." in rendered
    assert "Branch: feature | Kind: InfraInterface | Identifier: {'id': ['abc123']}" in rendered


def test_node_not_found_error_requires_keyword_arguments() -> None:
    with pytest.raises(TypeError, match="positional argument"):
        NodeNotFoundError("main", "InfraDevice", {"id": ["abc"]})  # type: ignore[misc]


def test_node_not_found_error_requires_all_fields() -> None:
    with pytest.raises(TypeError, match="branch_name"):
        NodeNotFoundError(node_type="InfraDevice", identifier={"id": ["abc"]})  # type: ignore[call-arg]

    with pytest.raises(TypeError, match="node_type"):
        NodeNotFoundError(branch_name="main", identifier={"id": ["abc"]})  # type: ignore[call-arg]

    with pytest.raises(TypeError, match="identifier"):
        NodeNotFoundError(branch_name="main", node_type="InfraDevice")  # type: ignore[call-arg]


def test_node_invalid_error_inherits_signature() -> None:
    error = NodeInvalidError(
        branch_name="main",
        node_type="InfraDevice",
        identifier={"id": ["abc"]},
        message="Found a node of a different kind",
    )

    assert isinstance(error, NodeNotFoundError)
    rendered = str(error)
    assert "Branch: main | Kind: InfraDevice | Identifier: {'id': ['abc']}" in rendered
    assert "Found a node of a different kind" in rendered
