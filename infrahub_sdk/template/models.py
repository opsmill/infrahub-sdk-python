from dataclasses import dataclass

from rich.syntax import Syntax
from rich.traceback import Frame


@dataclass
class UndefinedJinja2Error:
    frame: Frame
    syntax: Syntax
