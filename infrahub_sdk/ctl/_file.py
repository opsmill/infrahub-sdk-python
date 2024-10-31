from pathlib import Path

from .exceptions import FileNotValidError


def read_file(file_name: Path) -> str:
    if not file_name.is_file():
        raise FileNotValidError(name=str(file_name), message=f"{file_name} is not a valid file")
    try:
        with Path.open(file_name, encoding="utf-8") as fobj:
            return fobj.read()
    except UnicodeDecodeError as exc:
        raise FileNotValidError(name=str(file_name), message=f"Unable to read {file_name} with utf-8 encoding") from exc
