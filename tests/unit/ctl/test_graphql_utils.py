from graphql import parse, print_ast

from infrahub_sdk.graphql.utils import (
    strip_typename_from_fragment,
    strip_typename_from_operation,
    strip_typename_from_selection_set,
)


class TestStripTypename:
    def test_strip_typename_from_simple_query(self) -> None:
        query = """
        query Test {
            BuiltinTag {
                __typename
                name
            }
        }
        """
        doc = parse(query)
        operation = doc.definitions[0]
        result = strip_typename_from_operation(operation)

        result_str = print_ast(result)
        assert "__typename" not in result_str
        assert "name" in result_str
        assert "BuiltinTag" in result_str

    def test_strip_typename_from_nested_query(self) -> None:
        query = """
        query Test {
            BuiltinTag {
                edges {
                    node {
                        __typename
                        name {
                            value
                        }
                    }
                }
            }
        }
        """
        doc = parse(query)
        operation = doc.definitions[0]
        result = strip_typename_from_operation(operation)

        result_str = print_ast(result)
        assert "__typename" not in result_str
        assert "name" in result_str
        assert "value" in result_str
        assert "edges" in result_str
        assert "node" in result_str

    def test_strip_typename_from_inline_fragment(self) -> None:
        query = """
        query Test {
            BuiltinTag {
                edges {
                    node {
                        __typename
                        ... on Tag {
                            __typename
                            name {
                                value
                            }
                        }
                    }
                }
            }
        }
        """
        doc = parse(query)
        operation = doc.definitions[0]
        result = strip_typename_from_operation(operation)

        result_str = print_ast(result)
        assert "__typename" not in result_str
        assert "... on Tag" in result_str
        assert "name" in result_str

    def test_strip_typename_from_fragment_definition(self) -> None:
        query = """
        fragment TagFields on Tag {
            __typename
            name {
                value
            }
            description {
                value
            }
        }
        """
        doc = parse(query)
        fragment = doc.definitions[0]
        result = strip_typename_from_fragment(fragment)

        result_str = print_ast(result)
        assert "__typename" not in result_str
        assert "name" in result_str
        assert "description" in result_str
        assert "TagFields" in result_str

    def test_strip_typename_preserves_fragment_spread(self) -> None:
        query = """
        query Test {
            BuiltinTag {
                ...TagFields
                __typename
            }
        }
        """
        doc = parse(query)
        operation = doc.definitions[0]
        result = strip_typename_from_operation(operation)

        result_str = print_ast(result)
        assert "__typename" not in result_str
        assert "...TagFields" in result_str

    def test_strip_typename_from_empty_selection_set(self) -> None:
        result = strip_typename_from_selection_set(None)
        assert result is None

    def test_strip_typename_multiple_occurrences(self) -> None:
        query = """
        query Test {
            __typename
            BuiltinTag {
                __typename
                edges {
                    __typename
                    node {
                        __typename
                        name {
                            __typename
                            value
                        }
                    }
                }
            }
        }
        """
        doc = parse(query)
        operation = doc.definitions[0]
        result = strip_typename_from_operation(operation)

        result_str = print_ast(result)
        assert "__typename" not in result_str
        # Should still have the actual fields
        assert "BuiltinTag" in result_str
        assert "edges" in result_str
        assert "node" in result_str
        assert "name" in result_str
        assert "value" in result_str

    def test_strip_typename_preserves_aliases(self) -> None:
        query = """
        query Test {
            tags: BuiltinTag {
                __typename
                tagName: name {
                    value
                }
            }
        }
        """
        doc = parse(query)
        operation = doc.definitions[0]
        result = strip_typename_from_operation(operation)

        result_str = print_ast(result)
        assert "__typename" not in result_str
        assert "tags: BuiltinTag" in result_str
        assert "tagName: name" in result_str

    def test_strip_typename_preserves_arguments(self) -> None:
        query = """
        query Test {
            BuiltinTag(first: 10, name__value: "test") {
                __typename
                edges {
                    node {
                        name {
                            value
                        }
                    }
                }
            }
        }
        """
        doc = parse(query)
        operation = doc.definitions[0]
        result = strip_typename_from_operation(operation)

        result_str = print_ast(result)
        assert "__typename" not in result_str
        assert "first: 10" in result_str
        assert 'name__value: "test"' in result_str

    def test_strip_typename_preserves_directives(self) -> None:
        query = """
        query Test {
            BuiltinTag @include(if: true) {
                __typename
                name {
                    value
                }
            }
        }
        """
        doc = parse(query)
        operation = doc.definitions[0]
        result = strip_typename_from_operation(operation)

        result_str = print_ast(result)
        assert "__typename" not in result_str
        assert "@include(if: true)" in result_str

    def test_query_without_typename_unchanged(self) -> None:
        query = """
        query Test {
            BuiltinTag {
                edges {
                    node {
                        name {
                            value
                        }
                    }
                }
            }
        }
        """
        doc = parse(query)
        operation = doc.definitions[0]
        result = strip_typename_from_operation(operation)

        # The structure should be effectively the same (modulo formatting)
        original_str = print_ast(operation)
        result_str = print_ast(result)
        # Normalize whitespace for comparison
        assert original_str.split() == result_str.split()
