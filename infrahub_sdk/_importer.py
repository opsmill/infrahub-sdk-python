from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .exceptions import ModuleImportError

if TYPE_CHECKING:
    from types import ModuleType

module_mtime_cache: dict[str, float] = {}


def import_module(
    module_path: Path, import_root: Optional[str] = None, relative_path: Optional[str] = None
) -> ModuleType:
    import_root = import_root or str(module_path.parent)

    file_on_disk = module_path
    if import_root and relative_path:
        file_on_disk = Path(import_root, relative_path, module_path.name)

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
