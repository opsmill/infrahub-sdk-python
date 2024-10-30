from pathlib import Path

from infrahub_sdk.yaml import YamlFile

here = Path(__file__).parent.resolve()


def test_read_missing_file() -> None:
    file = here / "test_data/i_do_not_exist.yml"
    yaml_file = YamlFile(location=file)
    yaml_file.load_content()
    assert not yaml_file.valid
    assert yaml_file.error_message == f"{file} is not a valid file"


def test_read_incorrect_encoding() -> None:
    file = here / "test_data/schema_encoding_error.yml"
    yaml_file = YamlFile(location=file)
    yaml_file.load_content()
    assert not yaml_file.valid
    assert yaml_file.error_message == f"Unable to read {file} with utf-8 encoding"
