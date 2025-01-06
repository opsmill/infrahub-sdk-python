from __future__ import annotations

import difflib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import ujson

from ..exceptions import InvalidResourceConfigError
from ..models import InfrahubInputOutputTest

if TYPE_CHECKING:
    from ...schema.repository import InfrahubRepositoryConfigElement
    from ..models import InfrahubTest

_infrahub_config_path_attribute = "infrahub_config_path"


class InfrahubItem(pytest.Item):
    def __init__(
        self,
        *args: Any,
        resource_name: str,
        resource_config: InfrahubRepositoryConfigElement,
        test: InfrahubTest,
        **kwargs: dict[str, Any],
    ):
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.resource_name: str = resource_name
        self.resource_config: InfrahubRepositoryConfigElement = resource_config
        self.test: InfrahubTest = test

        # Smoke tests do not need this, hence this clause
        if isinstance(self.test.spec, InfrahubInputOutputTest):
            self.test.spec.update_paths(base_dir=self.path.parent)

    def validate_resource_config(self) -> None:
        """Make sure that a test resource config is properly defined."""
        if self.resource_config is None:
            raise InvalidResourceConfigError(self.resource_name)

    def get_result_differences(self, computed: Any) -> str | None:
        """Compute the differences between the computed result and the expected one.

        If the results are not JSON parsable, this method must be redefined to handle them.
        """
        # We cannot compute a diff if:
        # 1. Test is not an input/output one
        # 2. Expected output is not provided
        # 3. Output can't be computed
        if not isinstance(self.test.spec, InfrahubInputOutputTest) or not self.test.spec.output or computed is None:
            return None

        expected = self.test.spec.get_output_data()
        differences = difflib.unified_diff(
            ujson.dumps(expected, indent=4, sort_keys=True).splitlines(),
            ujson.dumps(computed, indent=4, sort_keys=True).splitlines(),
            fromfile="expected",
            tofile="rendered",
            lineterm="",
        )
        return "\n".join(differences)

    def runtest(self) -> None:
        """Run the test logic."""

    def repr_failure(self, excinfo: pytest.ExceptionInfo, style: str | None = None) -> str:  # noqa: ARG002
        return str(excinfo.value)

    def reportinfo(self) -> tuple[Path | str, int | None, str]:
        return self.path, 0, f"resource: {self.name}"

    @property
    def repository_base(self) -> str:
        """Return the path to the root of the repository

        This will be an absolute path if --infrahub-config-path is an absolut path as happens when
        tests are started from within Infrahub server.
        """
        config_path: Path = getattr(self.session, _infrahub_config_path_attribute)
        if config_path.is_absolute():
            return str(config_path.parent)

        return str(Path.cwd())
