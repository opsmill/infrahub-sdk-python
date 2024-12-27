import importlib
from pathlib import Path
from typing import Optional, Union

from .exceptions import InfrahubCheckNotFoundError, InfrahubTransformNotFoundError
from .schema.repository import InfrahubCheckDefinitionConfig, InfrahubPythonTransformConfig


def get_check_or_transform_class(
    config: Union[InfrahubCheckDefinitionConfig, InfrahubPythonTransformConfig], search_path: Optional[Path] = None
) -> type:
    if config.file_path.is_absolute() or search_path is None:
        search_location = config.file_path
    else:
        search_location = search_path / config.file_path

    try:
        spec = importlib.util.spec_from_file_location(config.class_name, search_location)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]

        # Set base module for relative import. See https://github.com/opsmill/infrahub-sdk-python/issues/166.
        # NOTE 1: When pytest plugin runs through proposed change pipeline, it is invoked within infrahub folder,
        # ie outside of the imported repository. Thus, we cannot rely on `importlib.import_module` as other components,
        # so we need to use `importlib.util.spec_from_file_location` in order to import desired module.
        # NOTE 2: Using `__package__` logs a `DeprecationWarning: __package__ != __spec__.parent`
        module.__package__ = str(search_location.parent.name)

        spec.loader.exec_module(module)  # type: ignore[union-attr]

        # Get the specified class from the module
        return getattr(module, config.class_name)

    except (FileNotFoundError, AttributeError) as exc:
        if isinstance(config, InfrahubPythonTransformConfig):
            raise InfrahubTransformNotFoundError(name=config.name) from exc
        raise InfrahubCheckNotFoundError(name=config.name) from exc
