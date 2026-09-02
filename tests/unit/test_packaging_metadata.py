"""Checks that keep the declared dependency surface in `pyproject.toml` honest.

The version matrix in CI installs whatever `uv.lock` pins, so it never exercises the ranges
declared in `pyproject.toml`. These checks cover the part of that gap that costs no extra CI
time: that every requirement is bounded, that the extras aggregate correctly, and that the
declared dependencies and the imports in the shipped package agree with each other.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Container, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeGuard

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from tests.constants import PACKAGE_DIR, PYPROJECT_FILE, REPO_ROOT

if sys.version_info >= (3, 11):
    import tomllib
else:
    # Drop this branch, and the suppression, once Python 3.10 support ends.
    import tomli as tomllib  # type: ignore[import-not-found]

PROJECT_NAME = "infrahub-sdk"
BASE_SECTION = "project.dependencies"

# Modules that ship in the wheel but are allowed to need an extra, mapped to the extra that
# supplies them. `ctl/` is the CLI; `async_typer` and `graphql/plugin.py` sit outside it but are
# only reachable from it. Everything else must import on a plain install.
EXTRA_ONLY_MODULES = {
    "ctl": ("ctl/", "async_typer.py", "graphql/plugin.py"),
    "tests": ("pytest_plugin/", "testing/"),
}

# Operators that establish a floor. A requirement without one of these lets a resolver reach back
# to the first release ever published, which is never a version we have tested against.
LOWER_BOUND_OPERATORS = frozenset({">=", ">", "==", "~="})

# Only modules whose import name differs from their distribution name in a way PEP 503
# normalisation cannot recover. Everything else maps by normalising the module name.
IMPORT_NAME_TO_DISTRIBUTION = {
    "graphql": "graphql-core",
    "ruamel": "ruamel.yaml",
    "yaml": "pyyaml",
}

# Standard library on a Python newer than the interpreter running these checks, so absent from
# this interpreter's `sys.stdlib_module_names`. They are imported behind a `sys.version_info`
# guard alongside a declared backport, and must not be mistaken for undeclared packages on the
# older interpreters in the test matrix.
STDLIB_ON_NEWER_PYTHON = frozenset({"tomllib"})

# Distributions declared on purpose without being imported, with the reason why.
DECLARED_WITHOUT_IMPORT = {
    "click": "Constrains the `click` version that `typer` resolves to; never imported directly.",
}


def _normalize(name: str) -> str:
    """Normalise a distribution name per PEP 503 so `ruamel.yaml` and `Jinja2` compare cleanly."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _pyproject() -> dict[str, Any]:
    with PYPROJECT_FILE.open("rb") as handle:
        return tomllib.load(handle)["project"]


def _optional_dependencies() -> dict[str, list[str]]:
    return _pyproject()["optional-dependencies"]


def _is_self_reference(requirement: Requirement) -> bool:
    return _normalize(requirement.name) == _normalize(PROJECT_NAME)


@dataclass
class RequirementCase:
    name: str
    section: str
    requirement: str


@dataclass
class ImportCase:
    name: str
    source: str
    runs_on_import: bool


IMPORT_CLASSIFICATION_CASES = [
    ImportCase(name="module-level", source="import pyarrow\n", runs_on_import=True),
    ImportCase(
        name="module-level-try",
        source="try:\n    import pyarrow\nexcept ImportError:\n    pyarrow = None\n",
        runs_on_import=True,
    ),
    ImportCase(
        name="inside-function",
        source="def load():\n    import pyarrow\n    return pyarrow\n",
        runs_on_import=False,
    ),
    ImportCase(
        name="type-checking-guard",
        source="from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import pyarrow\n",
        runs_on_import=False,
    ),
    ImportCase(
        name="qualified-type-checking-guard",
        source="import typing\nif typing.TYPE_CHECKING:\n    import pyarrow\n",
        runs_on_import=False,
    ),
    ImportCase(
        name="runtime-fallback-of-type-checking-guard",
        source="from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    pass\nelse:\n    import pyarrow\n",
        runs_on_import=True,
    ),
]


def _requirement_cases() -> list[RequirementCase]:
    """Every requirement a user can install, labelled with the section that declares it."""
    project = _pyproject()
    sections = {BASE_SECTION: project["dependencies"], **project["optional-dependencies"]}
    return [
        RequirementCase(name=f"{section}-{Requirement(requirement).name}", section=section, requirement=requirement)
        for section, requirements in sections.items()
        for requirement in requirements
    ]


def _declared_in(sections: Container[str]) -> set[str]:
    """The distributions installed by the given sections of `pyproject.toml`."""
    return {
        _normalize(requirement.name)
        for requirement in (Requirement(case.requirement) for case in _requirement_cases() if case.section in sections)
        if not _is_self_reference(requirement)
    }


def _surface_of(relative_path: Path) -> str | None:
    """The extra a shipped module may rely on, or None when it has to work on a base install."""
    posix = relative_path.as_posix()
    for extra, prefixes in EXTRA_ONLY_MODULES.items():
        if any(posix.startswith(prefix) for prefix in prefixes):
            return extra
    return None


def _is_type_checking_guard(node: ast.AST) -> TypeGuard[ast.If]:
    """Whether *node* is an `if TYPE_CHECKING:` (or `if typing.TYPE_CHECKING:`) statement."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    name = test.id if isinstance(test, ast.Name) else test.attr if isinstance(test, ast.Attribute) else None
    return name == "TYPE_CHECKING"


def _import_time_nodes(tree: ast.Module) -> Iterator[ast.AST]:
    """Walk the nodes that execute when the module is first loaded.

    Function bodies and `if TYPE_CHECKING:` blocks are both skipped, because neither runs on
    import: a deferred import is the sanctioned way to reach for an extra, as the JSON importer
    does for pyarrow, and a type-checking import never executes at all.

    Yields:
        Each node reachable at import time, including those nested in module-level `if` and `try`
        blocks and in class bodies.
    """
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _is_type_checking_guard(node):
            # The else branch of a type-checking guard is the runtime fallback, so it still counts.
            stack.extend(node.orelse)
            continue
        stack.extend(ast.iter_child_nodes(node))


def _imports_of(path: Path, *, include_deferred: bool) -> set[str]:
    """The third-party distributions a single module imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    distributions = set()
    for node in ast.walk(tree) if include_deferred else _import_time_nodes(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
        else:
            continue
        for module in modules:
            top_level = module.split(".")[0]
            if (
                top_level in sys.stdlib_module_names
                or top_level in STDLIB_ON_NEWER_PYTHON
                or top_level == PACKAGE_DIR.name
            ):
                continue
            distributions.add(_normalize(IMPORT_NAME_TO_DISTRIBUTION.get(top_level, top_level)))
    return distributions


def _imported_distributions() -> dict[str, Path]:
    """Map each third-party distribution imported under the package to a file that imports it."""
    imported: dict[str, Path] = {}
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        for distribution in sorted(_imports_of(path, include_deferred=True)):
            imported.setdefault(distribution, path.relative_to(REPO_ROOT))
    return imported


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in IMPORT_CLASSIFICATION_CASES])
def test_import_classification(case: ImportCase, tmp_path: Path) -> None:
    """Whether an import counts at import time decides what the surface check enforces."""
    module = tmp_path / "probe.py"
    module.write_text(case.source, encoding="utf-8")

    assert ("pyarrow" in _imports_of(module, include_deferred=False)) is case.runs_on_import
    assert "pyarrow" in _imports_of(module, include_deferred=True), (
        "every import should be found when deferred ones are included"
    )


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in _requirement_cases()])
def test_requirement_declares_a_lower_bound(case: RequirementCase) -> None:
    requirement = Requirement(case.requirement)
    if _is_self_reference(requirement):
        pytest.skip("self-referential extra, versioned by the project itself")

    operators = {specifier.operator for specifier in requirement.specifier}
    assert operators & LOWER_BOUND_OPERATORS, (
        f"{case.requirement!r} has no lower bound, so a resolver may select an ancient release we "
        f"have never tested against. Add a floor matching the oldest version known to work."
    )


def test_all_extra_aggregates_every_other_extra() -> None:
    """`all` must be defined by self-reference so it cannot drift out of sync with the other extras."""
    extras = _optional_dependencies()
    aggregated: set[str] = set()
    for raw in extras["all"]:
        requirement = Requirement(raw)
        assert _is_self_reference(requirement), (
            f"the 'all' extra must aggregate this project's own extras by self-reference, found {raw!r}"
        )
        aggregated |= {_normalize(extra) for extra in requirement.extras}

    assert aggregated == {_normalize(name) for name in extras if name != "all"}


def test_shipped_modules_only_import_what_their_install_provides() -> None:
    """Every shipped module must be importable with the install its own surface implies.

    Checking against the union of every extra would let a module that ships in the base wheel
    import a package only the `ctl` extra installs, which is how `infrahub_sdk.template` came to
    raise `ModuleNotFoundError` on a plain install.
    """
    base = _declared_in({BASE_SECTION})
    failures = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        extra = _surface_of(path.relative_to(PACKAGE_DIR))
        available = base if extra is None else base | _declared_in({extra})
        install = "a base install" if extra is None else f"the '{extra}' extra"
        failures += [
            f"{path.relative_to(REPO_ROOT)} imports {distribution}, which is not installed by {install}"
            for distribution in sorted(_imports_of(path, include_deferred=False) - available)
        ]

    assert not failures, "\n".join(failures)


def test_imports_in_shipped_package_are_declared() -> None:
    """Anything the wheel imports must be installable, not left to arrive as a transitive dependency."""
    declared = _declared_in({BASE_SECTION, *_optional_dependencies()})
    undeclared = {
        distribution: source
        for distribution, source in _imported_distributions().items()
        if distribution not in declared
    }
    assert not undeclared, "\n".join(
        f"{distribution} is imported by {source} but is declared nowhere in pyproject.toml"
        for distribution, source in sorted(undeclared.items())
    )


def test_declared_dependencies_are_imported() -> None:
    """A declared dependency nobody imports is either dead weight or belongs in a dependency group."""
    imported = _imported_distributions()
    unused = sorted(
        distribution
        for distribution in _declared_in({BASE_SECTION, *_optional_dependencies()})
        if distribution not in imported and distribution not in DECLARED_WITHOUT_IMPORT
    )
    assert not unused, (
        f"declared but never imported under {PACKAGE_DIR.name}/: {', '.join(unused)}. Move it to a "
        f"dependency group if it is only needed for development, or record the reason it is declared "
        f"in DECLARED_WITHOUT_IMPORT."
    )


def test_requires_python_matches_classifiers() -> None:
    project = _pyproject()
    supported = SpecifierSet(project["requires-python"])
    prefix = "Programming Language :: Python :: 3."

    from_classifiers = {c.removeprefix(prefix) for c in project["classifiers"] if c.startswith(prefix)}
    from_specifier = {str(minor) for minor in range(50) if Version(f"3.{minor}") in supported}

    assert from_classifiers == from_specifier, (
        f"requires-python allows 3.x for x in {sorted(from_specifier)} but the classifiers "
        f"advertise {sorted(from_classifiers)}"
    )
