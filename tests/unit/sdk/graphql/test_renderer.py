from typing import Any

from infrahub_sdk.graphql.renderers import convert_to_graphql_as_string, render_input_block, render_query_block


def test_render_query_block(query_data_no_filter: dict[str, Any]) -> None:
    lines = render_query_block(data=query_data_no_filter)

    expected_lines = [
        "    device {",
        "        name {",
        "            value",
        "        }",
        "        description {",
        "            value",
        "        }",
        "        interfaces {",
        "            name {",
        "                value",
        "            }",
        "        }",
        "    }",
    ]

    assert lines == expected_lines

    # Render the query block with an indentation of 2
    lines = render_query_block(data=query_data_no_filter, offset=2, indentation=2)

    expected_lines = [
        "  device {",
        "    name {",
        "      value",
        "    }",
        "    description {",
        "      value",
        "    }",
        "    interfaces {",
        "      name {",
        "        value",
        "      }",
        "    }",
        "  }",
    ]

    assert lines == expected_lines


def test_render_query_block_alias(query_data_alias: dict[str, Any]) -> None:
    lines = render_query_block(data=query_data_alias)

    expected_lines = [
        "    device {",
        "        new_name: name {",
        "            value",
        "        }",
        "        description {",
        "            myvalue: value",
        "        }",
        "        myinterfaces: interfaces {",
        "            name {",
        "                value",
        "            }",
        "        }",
        "    }",
    ]

    assert lines == expected_lines


def test_render_query_block_fragment(query_data_fragment: dict[str, Any]) -> None:
    lines = render_query_block(data=query_data_fragment)

    expected_lines = [
        "    device {",
        "        name {",
        "            value",
        "        }",
        "        ...on Builtin {",
        "            description {",
        "                value",
        "            }",
        "            interfaces {",
        "                name {",
        "                    value",
        "                }",
        "            }",
        "        }",
        "    }",
    ]

    assert lines == expected_lines


def test_render_input_block(input_data_01: dict[str, Any]) -> None:
    lines = render_input_block(data=input_data_01)

    expected_lines = [
        "    data: {",
        "        name: {",
        "            value: $name",
        "        }",
        "        some_number: {",
        "            value: 88",
        "        }",
        "        some_bool: {",
        "            value: true",
        "        }",
        "        some_list: {",
        "            value: [",
        '                "value1",',
        "                33,",
        "            ]",
        "        }",
        "        query: {",
        '            value: "my_query"',
        "        }",
        "    }",
    ]
    assert lines == expected_lines

    # Render the input block with an indentation of 2
    lines = render_input_block(data=input_data_01, offset=2, indentation=2)

    expected_lines = [
        "  data: {",
        "    name: {",
        "      value: $name",
        "    }",
        "    some_number: {",
        "      value: 88",
        "    }",
        "    some_bool: {",
        "      value: true",
        "    }",
        "    some_list: {",
        "      value: [",
        '        "value1",',
        "        33,",
        "      ]",
        "    }",
        "    query: {",
        '      value: "my_query"',
        "    }",
        "  }",
    ]
    assert lines == expected_lines


class RelatedNodeLikeObject:
    """Mock object that looks like a RelatedNode (has _generate_input_data and id)."""

    def __init__(self, node_id: str) -> None:
        self._id = node_id

    @property
    def id(self) -> str:
        return self._id

    def _generate_input_data(self) -> dict[str, Any]:
        return {"id": self._id}


def test_convert_to_graphql_as_string_handles_related_node_like_object() -> None:
    """Test that convert_to_graphql_as_string handles objects with _generate_input_data and id."""
    # This tests the defensive check added to handle cases where a RelatedNode-like
    # object somehow gets passed to convert_to_graphql_as_string without being
    # converted to a dict first
    related_node_like = RelatedNodeLikeObject("test-uuid-789")

    result = convert_to_graphql_as_string(related_node_like)

    # Should extract the id and convert it properly, not produce the object repr
    assert result == '"test-uuid-789"'
    assert "RelatedNodeLikeObject" not in result
