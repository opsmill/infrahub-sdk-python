from dataclasses import dataclass
from pathlib import Path

import pytest

from infrahub_sdk.exceptions import FileNotValidError, ValidationError
from infrahub_sdk.utils import get_fixtures_dir
from infrahub_sdk.yaml import InfrahubFile, YamlFile

here = Path(__file__).parent.resolve()


@dataclass
class InvalidInfrahubFileCase:
    name: str
    content: dict
    message: str


INVALID_INFRAHUB_FILE_CASES = [
    InvalidInfrahubFileCase(
        name="unknown-kind",
        content={"apiVersion": "infrahub.app/v1", "kind": "Schema", "spec": {}},
        message="kind | Input should be 'Menu' or 'Object', received 'Schema' (enum)",
    ),
    InvalidInfrahubFileCase(
        name="missing-spec",
        content={"apiVersion": "infrahub.app/v1", "kind": "Object"},
        message="spec | Field required (missing)",
    ),
    InvalidInfrahubFileCase(
        name="unknown-api-version",
        content={"apiVersion": "infrahub.app/v2", "kind": "Object", "spec": {}},
        message="apiVersion | Input should be 'infrahub.app/v1', received 'infrahub.app/v2' (enum)",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in INVALID_INFRAHUB_FILE_CASES])
def test_infrahub_file_validate_content_invalid(case: InvalidInfrahubFileCase) -> None:
    infrahub_file = InfrahubFile(location=Path("some/path"), content=case.content)
    with pytest.raises(ValidationError, match=r"^some/path: ") as exc:
        infrahub_file.validate_content()

    assert exc.value.identifier == "some/path"
    assert exc.value.messages == [case.message]


def test_infrahub_file_validate_content_non_string_keys() -> None:
    # PyYAML reads unquoted keys such as `2:` and `off:` as int and bool.
    content = {"apiVersion": "infrahub.app/v1", "kind": "Object", "spec": {}, 2: "extra", False: "off"}
    infrahub_file = InfrahubFile(location=Path("some/path"), content=content)
    infrahub_file.validate_content()

    assert infrahub_file.data.spec == {}


def test_read_missing_file() -> None:
    file_name = "i_do_not_exist.yml"
    test_data_dir = here / "test_data"
    full_path = test_data_dir / file_name
    yaml_file = YamlFile(location=full_path)
    yaml_file.load_content()
    assert not yaml_file.valid
    assert yaml_file.error_message == f"{file_name}: not found at {test_data_dir}"


def test_read_incorrect_encoding() -> None:
    file_name = "schema_encoding_error.yml"
    full_path = here / "test_data" / file_name
    yaml_file = YamlFile(location=full_path)
    yaml_file.load_content()
    assert not yaml_file.valid
    assert yaml_file.error_message == f"Unable to read {file_name} with utf-8 encoding"


def test_read_multiple_files() -> None:
    file = here / "test_data/multiple_files_valid.yml"
    yaml_files = YamlFile.load_file_from_disk(path=file)
    assert len(yaml_files) == 2
    assert yaml_files[0].document_position == 1
    assert yaml_files[0].valid is True
    assert yaml_files[1].document_position == 2
    assert yaml_files[1].valid is True


def test_read_multiple_files_invalid() -> None:
    file = here / "test_data/multiple_files_valid_not_valid.yml"
    yaml_files = YamlFile.load_file_from_disk(path=file)
    assert len(yaml_files) == 2
    assert yaml_files[0].document_position == 1
    assert yaml_files[0].valid is True
    assert yaml_files[1].document_position == 2
    assert yaml_files[1].valid is False


def test_load_non_existing_folder() -> None:
    with pytest.raises(FileNotValidError) as exc:
        YamlFile.load_from_disk(paths=[get_fixtures_dir() / "does_not_exist"])
    assert "does not exist" in str(exc.value)
