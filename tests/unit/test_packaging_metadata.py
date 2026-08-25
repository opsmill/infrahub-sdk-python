"""Checks that keep the declared dependency surface in `pyproject.toml` honest.

The version matrix in CI installs whatever `uv.lock` pins, so it never exercises the ranges
declared in `pyproject.toml`. These checks cover the part of that gap that costs no extra CI
time: that every requirement is bounded, that the extras aggregate correctly, and that the
declared dependencies and the imports in the shipped package agree with each other.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

# Distributions declared on purpose without being imported, with the reason why.
DECLARED_WITHOUT_IMPORT = {
    "click": "Constrains the `click` version that `typer` resolves to; never imported directly.",
}


def _normalize(name: str) -> str:
    """Normalise a distribution name per PEP 503 so `ruamel.yaml` and `Jinja2` compare cleanly."""
    return "".join("-" if character in "-_." else character for character in name.lower())


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
    requirement: str


def _requirement_cases() -> list[RequirementCase]:
    """Every requirement a user can install, labelled with the section that declares it."""
    project = _pyproject()
    sections = {"project.dependencies": project["dependencies"], **project["optional-dependencies"]}
    return [
        RequirementCase(name=f"{section}-{Requirement(requirement).name}", requirement=requirement)
        for section, requirements in sections.items()
        for requirement in requirements
    ]


def _declared_distributions() -> set[str]:
    """Every distribution a user can install, across the core dependencies and all extras."""
    parsed = (Requirement(case.requirement) for case in _requirement_cases())
    return {_normalize(requirement.name) for requirement in parsed if not _is_self_reference(requirement)}


def _imported_distributions() -> dict[str, Path]:
    """Map each third-party distribution imported under the package to a file that imports it."""
    imported: dict[str, Path] = {}
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                top_level = module.split(".")[0]
                if top_level in sys.stdlib_module_names or top_level == PACKAGE_DIR.name:
                    continue
                distribution = _normalize(IMPORT_NAME_TO_DISTRIBUTION.get(top_level, top_level))
                imported.setdefault(distribution, path.relative_to(REPO_ROOT))
    return imported


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


def test_imports_in_shipped_package_are_declared() -> None:
    """Anything the wheel imports must be installable, not left to arrive as a transitive dependency."""
    declared = _declared_distributions()
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
        for distribution in _declared_distributions()
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
