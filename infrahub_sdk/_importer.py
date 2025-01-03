from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .exceptions import ModuleImportError

if TYPE_CHECKING:
    from types import ModuleType

module_mtime_cache: dict[str, float] = {}


def import_module(module_path: Path, import_root: str | None = None, relative_path: str | None = None) -> ModuleType:
    """Imports a python module.

    Args:
        module_path (Path): Absolute path of the module to import.
        import_root (Optional[str]): Absolute string path to the current repository.
        relative_path (Optional[str]): Relative string path between module_path and import_root.
    """
    import_root = import_root or str(module_path.parent)

    file_on_disk = module_path
    if import_root and relative_path:
        file_on_disk = Path(import_root, relative_path, module_path.name)

    # This is a temporary workaround for to account for issues if "import_root" is a Path instead of a str
    # Later we should rework this so that import_root and relative_path are all Path objects. Here we must
    # ensure that anything we add to sys.path is a string and not a Path or PosixPath object.
    import_root = str(import_root)
    if import_root not in sys.path:
        sys.path.append(import_root)

    module_name = module_path.stem

    if relative_path:
        module_name = relative_path.replace("/", ".") + f".{module_name}"

    try:
        if module_name in sys.modules:
            module = sys.modules[module_name]
            current_mtime = file_on_disk.stat().st_mtime

            if module_name in module_mtime_cache:
                last_mtime = module_mtime_cache[module_name]
                if current_mtime == last_mtime:
                    return module

            module_mtime_cache[module_name] = current_mtime
            module = importlib.reload(module)
        else:
            module = importlib.import_module(module_name)
            module_mtime_cache[module_name] = file_on_disk.stat().st_mtime

    except ModuleNotFoundError as exc:
        raise ModuleImportError(message=f"{exc!s} ({module_path})") from exc
    except SyntaxError as exc:
        raise ModuleImportError(message=str(exc)) from exc

    return module
