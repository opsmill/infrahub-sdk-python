"""GraphQL query rendering: fragment parsing, inlining, and loading from InfrahubRepositoryConfig."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from graphql import DocumentNode, FragmentDefinitionNode, FragmentSpreadNode, parse, print_ast
from graphql.error import GraphQLSyntaxError
from graphql.language.ast import Node as ASTNode

from ..exceptions import CircularFragmentError, DuplicateFragmentError, FragmentNotFoundError, QuerySyntaxError

if TYPE_CHECKING:
    from ..schema.repository import InfrahubRepositoryConfig


def _iter_nodes(node: ASTNode) -> Iterator[ASTNode]:
    """Yield node and every descendant in depth-first order."""
    stack: list[ASTNode] = [node]
    while stack:
        current = stack.pop()
        yield current
        for key in reversed(current.keys):
            child = getattr(current, key, None)
            if isinstance(child, ASTNode):
                stack.append(child)
            elif isinstance(child, tuple):
                stack.extend(item for item in reversed(child) if isinstance(item, ASTNode))


def _collect_spread_names(node: ASTNode) -> list[str]:
    """Return the names of all fragment spreads within node."""
    return [n.name.value for n in _iter_nodes(node) if isinstance(n, FragmentSpreadNode)]


def build_fragment_index(fragment_files: list[str]) -> dict[str, FragmentDefinitionNode]:
    """Parse all fragment file contents and return a mapping from fragment name to its AST node.

    Raises:
        QuerySyntaxError: A fragment file contains invalid GraphQL syntax.
        DuplicateFragmentError: The same fragment name appears more than once.

    """
    index: dict[str, FragmentDefinitionNode] = {}
    for content in fragment_files:
        try:
            doc = parse(content)
        except GraphQLSyntaxError as exc:
            raise QuerySyntaxError(syntax_error=str(exc)) from exc
        for definition in doc.definitions:
            if isinstance(definition, FragmentDefinitionNode):
                name = definition.name.value
                if name in index:
                    raise DuplicateFragmentError(fragment_name=name)
                index[name] = definition
    return index


def collect_required_fragments(
    query_doc: DocumentNode,
    fragment_index: dict[str, FragmentDefinitionNode],
) -> list[str]:
    """Walk query_doc and collect all fragment names required (transitively).

    Returns a topologically ordered list of unique fragment names.

    Raises:
        FragmentNotFoundError: An unresolved fragment name was referenced.
        CircularFragmentError: A cyclic dependency was detected among fragments.

    """
    # Collect spreads only from operation definitions — any fragment definitions already
    # present in the query document are self-contained and do not need external resolution.
    top_level_spreads = [
        node.name.value
        for definition in query_doc.definitions
        if not isinstance(definition, FragmentDefinitionNode)
        for node in _iter_nodes(definition)
        if isinstance(node, FragmentSpreadNode)
    ]

    local_fragments = {
        definition.name.value for definition in query_doc.definitions if isinstance(definition, FragmentDefinitionNode)
    }

    ordered: list[str] = []
    visited: set[str] = set()

    def resolve(name: str, stack: list[str]) -> None:
        if name in stack:
            cycle = [*stack[stack.index(name) :], name]
            raise CircularFragmentError(cycle=cycle)
        if name in visited:
            return
        if name in local_fragments:
            return
        if name not in fragment_index:
            raise FragmentNotFoundError(fragment_name=name)
        stack.append(name)
        for dep in _collect_spread_names(fragment_index[name]):
            resolve(dep, stack)
        stack.pop()
        visited.add(name)
        ordered.append(name)

    for spread_name in top_level_spreads:
        resolve(spread_name, [])

    return ordered


def render_query_with_fragments(query_str: str, fragment_files: list[str]) -> str:
    """Return a self-contained GraphQL document with required fragment definitions inlined.

    If the query contains no fragment spreads, query_str is returned unchanged.

    Raises:
        QuerySyntaxError: Query string or a fragment file contains invalid GraphQL syntax.
        DuplicateFragmentError: Same fragment name declared in multiple files.
        FragmentNotFoundError: Query references a fragment not found in any declared file.
        CircularFragmentError: Circular dependency detected among fragments.

    """
    try:
        query_doc = parse(query_str)
    except GraphQLSyntaxError as exc:
        raise QuerySyntaxError(syntax_error=str(exc)) from exc

    return _render_doc_with_fragments(query_doc, query_str, fragment_files)


def _render_doc_with_fragments(query_doc: DocumentNode, query_str: str, fragment_files: list[str]) -> str:
    """Inline fragments into an already-parsed query document.

    query_str is returned unchanged when the document contains no fragment spreads.
    """
    if not _has_fragment_spread(query_doc):
        return query_str

    fragment_index = build_fragment_index(fragment_files)
    required_names = collect_required_fragments(query_doc, fragment_index)

    query_definitions = list(query_doc.definitions)
    fragment_definitions = [fragment_index[name] for name in required_names]

    output_doc = DocumentNode(definitions=tuple(query_definitions + fragment_definitions))
    return print_ast(output_doc)


def _has_fragment_spread(doc: DocumentNode) -> bool:
    """Return True if the document contains any fragment spread in an operation definition."""
    return any(
        isinstance(node, FragmentSpreadNode)
        for definition in doc.definitions
        if not isinstance(definition, FragmentDefinitionNode)
        for node in _iter_nodes(definition)
    )


def render_query(name: str, config: InfrahubRepositoryConfig, relative_path: str = ".") -> str:
    """Return a self-contained GraphQL document for the named query, with fragment definitions inlined.

    Fragment files are only loaded from disk when the query actually uses fragment spreads.

    Raises:
        ResourceNotDefinedError: Query name not found in config.
        QuerySyntaxError: Query string contains invalid GraphQL syntax.
        FragmentFileNotFoundError: A declared fragment file path does not exist.
        DuplicateFragmentError: Same fragment name declared in multiple files.
        FragmentNotFoundError: Query references a fragment not found in any declared file.
        CircularFragmentError: Circular dependency detected among fragments.

    """
    raw = config.get_query(name).load_query(relative_path=relative_path)
    try:
        query_doc = parse(raw)
    except GraphQLSyntaxError as exc:
        raise QuerySyntaxError(syntax_error=str(exc)) from exc

    if not _has_fragment_spread(query_doc) or not config.graphql_fragments:
        return raw

    fragment_contents: list[str] = []
    for frag in config.graphql_fragments:
        fragment_contents.extend(frag.load_fragments(relative_path=relative_path))
    return _render_doc_with_fragments(query_doc, raw, fragment_contents)
