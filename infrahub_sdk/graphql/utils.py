import ast

from graphql import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InlineFragmentNode,
    OperationDefinitionNode,
    SelectionNode,
    SelectionSetNode,
)


def strip_typename_from_selection_set(selection_set: SelectionSetNode | None) -> SelectionSetNode | None:
    """Recursively strip __typename fields from a SelectionSetNode.

    The __typename meta-field is an introspection field that is not part of the schema's
    type definitions. When code generation tools like ariadne-codegen try to look up
    __typename in the schema, they fail because it's a reserved introspection field.

    This function removes all __typename fields from the selection set, allowing
    code generation to proceed without errors.
    """
    if selection_set is None:
        return None

    new_selections: list[SelectionNode] = []
    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            # Skip __typename fields
            if selection.name.value == "__typename":
                continue
            # Recursively process nested selection sets
            new_field = FieldNode(
                alias=selection.alias,
                name=selection.name,
                arguments=selection.arguments,
                directives=selection.directives,
                selection_set=strip_typename_from_selection_set(selection.selection_set),
            )
            new_selections.append(new_field)
        elif isinstance(selection, InlineFragmentNode):
            # Process inline fragments
            new_inline = InlineFragmentNode(
                type_condition=selection.type_condition,
                directives=selection.directives,
                selection_set=strip_typename_from_selection_set(selection.selection_set),
            )
            new_selections.append(new_inline)
        elif isinstance(selection, FragmentSpreadNode):
            # FragmentSpread references a named fragment - keep as-is
            new_selections.append(selection)
        else:
            raise TypeError(f"Unexpected GraphQL selection node type '{type(selection).__name__}'.")

    return SelectionSetNode(selections=tuple(new_selections))


def strip_typename_from_operation(operation: OperationDefinitionNode) -> OperationDefinitionNode:
    """Strip __typename fields from an operation definition.

    Returns a new OperationDefinitionNode with all __typename fields removed
    from its selection set and any nested selection sets.
    """
    return OperationDefinitionNode(
        operation=operation.operation,
        name=operation.name,
        variable_definitions=operation.variable_definitions,
        directives=operation.directives,
        selection_set=strip_typename_from_selection_set(operation.selection_set),
    )


def strip_typename_from_fragment(fragment: FragmentDefinitionNode) -> FragmentDefinitionNode:
    """Strip __typename fields from a fragment definition.

    Returns a new FragmentDefinitionNode with all __typename fields removed
    from its selection set and any nested selection sets.
    """
    return FragmentDefinitionNode(
        name=fragment.name,
        type_condition=fragment.type_condition,
        variable_definitions=fragment.variable_definitions,
        directives=fragment.directives,
        selection_set=strip_typename_from_selection_set(fragment.selection_set),
    )


def get_class_def_index(module: ast.Module) -> int:
    """Get the index of the first class definition in the module.
    It's useful to insert other classes before the first class definition."""
    for idx, item in enumerate(module.body):
        if isinstance(item, ast.ClassDef):
            return idx
    return -1


def insert_fragments_inline(module: ast.Module, fragment: ast.Module) -> ast.Module:
    """Insert the Pydantic classes for the fragments inline into the module.

    If no class definitions exist in module, fragments are appended to the end.
    """
    module_class_def_index = get_class_def_index(module)

    fragment_classes: list[ast.ClassDef] = [item for item in fragment.body if isinstance(item, ast.ClassDef)]

    # Handle edge case when no class definitions exist
    if module_class_def_index == -1:
        # Append fragments to the end of the module
        module.body.extend(fragment_classes)
    else:
        # Insert fragments before the first class definition
        for idx, item in enumerate(fragment_classes):
            module.body.insert(module_class_def_index + idx, item)

    return module


def remove_fragment_import(module: ast.Module) -> ast.Module:
    """Remove the fragment import from the module."""
    for item in module.body:
        if isinstance(item, ast.ImportFrom) and item.module == "fragments":
            module.body.remove(item)
            return module
    return module
