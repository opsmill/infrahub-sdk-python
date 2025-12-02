import builtins

from rich import inspect as rinspect
from rich import print as rprint

builtins.rprint = rprint  # type: ignore[attr-defined]
builtins.rinspect = rinspect  # type: ignore[attr-defined]
