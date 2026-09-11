"""The exceptions package is strictly layered, and imports may only point downward or outside the SDK.

Parsed rather than imported, so the property is checked against the source of every module in the
package and cannot decay silently.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import infrahub_sdk.exceptions as exceptions_package

ROOT = "infrahub_sdk"
PACKAGE = f"{ROOT}.exceptions"
PACKAGE_DIR = Path(exceptions_package.__file__).parent

# base.py sits at the bottom, which is what keeps the hand-written hierarchy independent of anything
# built on top of it. Each layer above may import only from below it.
LAYERS = {
    "base": 0,
    "factory": 1,
    "__init__": 2,
}


def module_paths() -> list[Path]:
    return sorted(PACKAGE_DIR.glob("*.py"))


def _submodule_of(dotted: str) -> str | None:
    """The package submodule an absolute dotted path names, or None if it points outside."""
    prefix = f"{PACKAGE}."
    if not dotted.startswith(prefix):
        return None
    return dotted[len(prefix) :].split(".", maxsplit=1)[0]


def intra_package_targets(tree: ast.AST, own_module: str) -> list[tuple[str, int]]:
    """Return (module, lineno) for every import that resolves inside the exceptions package.

    Both the relative and the absolute spelling are recognised, so neither form can be used to slip
    past the ordering. Walks the whole tree, so an import inside a function body or a TYPE_CHECKING
    block is caught exactly like a module-level one.
    """
    module_names = {path.stem for path in module_paths()}
    targets: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 1 and node.module:
                # `from .factory import x`
                targets.append((node.module.split(".")[0], node.lineno))
            elif (node.level == 1 and not node.module) or node.module == PACKAGE:
                # `from . import factory`, or the same written out in full. The names here are a mix
                # of submodules and of the classes the facade re-exports, so only the former count.
                targets.extend((alias.name, node.lineno) for alias in node.names if alias.name in module_names)
            elif node.level == 0 and node.module:
                # `from infrahub_sdk.exceptions.factory import x`
                submodule = _submodule_of(node.module)
                if submodule:
                    targets.append((submodule, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                submodule = _submodule_of(alias.name)
                if submodule:
                    targets.append((submodule, node.lineno))

    return [(module, lineno) for module, lineno in targets if module != own_module]


def _points_outside_package(dotted: str) -> bool:
    """Whether a dotted name reaches the SDK outside this package.

    The root itself counts: `import infrahub_sdk` and `from infrahub_sdk import utils` pull in the
    façade, which imports the client, so they are dependencies like any other.
    """
    if dotted != ROOT and not dotted.startswith(f"{ROOT}."):
        return False
    return dotted != PACKAGE and not dotted.startswith(f"{PACKAGE}.")


def outward_targets(tree: ast.AST) -> list[tuple[str, int]]:
    """Return (module, lineno) for every import reaching another part of the SDK.

    A relative import climbing out of the package counts, and so does the absolute spelling of the
    same module. Imports of the standard library and of third-party packages do not: the package may
    depend on those freely.
    """
    targets: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level >= 2:
                # `from ..utils import x` — one level up is the package itself, two is out of it.
                targets.append((f"{'.' * node.level}{node.module or ''}", node.lineno))
            elif node.level == 0 and node.module and _points_outside_package(node.module):
                targets.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            targets.extend((alias.name, node.lineno) for alias in node.names if _points_outside_package(alias.name))

    return targets


@pytest.mark.parametrize("path", module_paths(), ids=lambda p: p.name)
def test_the_package_depends_on_no_other_part_of_the_sdk(path: Path) -> None:
    """Nothing in the SDK may sit below the exceptions package.

    Every other module is free to raise, so a dependency in this direction is a cycle waiting to be
    discovered — and the workaround for one is a deferred import inside a function body, which the
    walk below catches exactly like a module-level one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    assert outward_targets(tree=tree) == [], (
        f"{path.name} imports from elsewhere in the SDK; keep the package self-contained instead"
    )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("from ..utils import decode_json", id="relative-parent"),
        pytest.param("from ...infrahub_sdk import utils", id="relative-grandparent"),
        pytest.param("from infrahub_sdk.utils import decode_json", id="absolute-from"),
        pytest.param("import infrahub_sdk.utils", id="absolute-import"),
        pytest.param("from infrahub_sdk import utils", id="root-from"),
        pytest.param("import infrahub_sdk", id="root-import"),
    ],
)
def test_an_outward_import_is_detected_however_it_is_spelled(source: str) -> None:
    assert outward_targets(tree=ast.parse(source)) != []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("from .base import Error", id="intra-package-relative"),
        pytest.param("from infrahub_sdk.exceptions.base import Error", id="intra-package-absolute"),
        pytest.param("from infrahub_sdk.exceptions import Error", id="package-facade"),
        pytest.param("import httpx", id="third-party"),
        pytest.param("from collections.abc import Mapping", id="standard-library"),
    ],
)
def test_an_allowed_import_is_not_mistaken_for_an_outward_one(source: str) -> None:
    assert outward_targets(tree=ast.parse(source)) == []


@pytest.mark.parametrize("path", module_paths(), ids=lambda p: p.name)
def test_imports_point_strictly_downward(path: Path) -> None:
    own_module = path.stem
    assert own_module in LAYERS, f"{path.name} is not assigned a layer in this test"
    own_layer = LAYERS[own_module]

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for module, lineno in intra_package_targets(tree=tree, own_module=own_module):
        assert module in LAYERS, f"{path.name}:{lineno} imports unknown package module '{module}'"
        assert LAYERS[module] < own_layer, (
            f"{path.name}:{lineno} imports '{module}' (layer {LAYERS[module]}) "
            f"from layer {own_layer}; imports must point strictly downward"
        )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("from .factory import graphql_error_from_response", id="relative-from"),
        pytest.param("from . import factory", id="relative-package"),
        pytest.param("from infrahub_sdk.exceptions.factory import graphql_error_from_response", id="absolute-from"),
        pytest.param("from infrahub_sdk.exceptions import factory", id="absolute-package"),
        pytest.param("import infrahub_sdk.exceptions.factory", id="absolute-import"),
    ],
)
def test_every_spelling_of_an_intra_package_import_is_detected(source: str) -> None:
    """The check is only worth having if it cannot be sidestepped by rewording the import."""
    targets = intra_package_targets(tree=ast.parse(source), own_module="base")

    assert targets == [("factory", 1)]


def test_re_exported_class_names_are_not_mistaken_for_modules() -> None:
    source = "from infrahub_sdk.exceptions import AuthenticationError"

    assert intra_package_targets(tree=ast.parse(source), own_module="base") == []
