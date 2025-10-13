import ast


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
