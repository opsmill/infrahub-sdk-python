from pathlib import Path


def get_fixtures_dir() -> Path:
    """Get the directory which stores fixtures that are common to multiple unit/integration tests."""
    here = Path(__file__).parent.resolve()
    return here.parent / "fixtures"


def read_fixture(file_name: str, fixture_subdir: str = ".") -> str:
    """Read the contents of a fixture."""
    file_path = get_fixtures_dir() / fixture_subdir / file_name
    with file_path.open("r", encoding="utf-8") as fhd:
        return fhd.read()
