import json
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from graphql import parse
from whenever import Instant

from infrahub_sdk.exceptions import JsonDecodeError
from infrahub_sdk.utils import (
    base16decode,
    base16encode,
    base36decode,
    base36encode,
    calculate_time_diff,
    compare_lists,
    decode_json,
    deep_merge_dict,
    dict_hash,
    duplicates,
    extract_fields,
    generate_short_id,
    is_valid_url,
    is_valid_uuid,
    str_to_bool,
    write_to_file,
)


def test_generate_short_id() -> None:
    assert len(generate_short_id()) == 22
    assert isinstance(generate_short_id(), str)
    assert generate_short_id() != generate_short_id()


def test_is_valid_uuid() -> None:
    assert is_valid_uuid(uuid.uuid4()) is True
    assert is_valid_uuid(uuid.UUID("ba0aecd9-546a-4d77-9187-23e17a20633e")) is True
    assert is_valid_uuid("ba0aecd9-546a-4d77-9187-23e17a20633e") is True

    assert is_valid_uuid("xxx-546a-4d77-9187-23e17a20633e") is False
    assert is_valid_uuid(222) is False
    assert is_valid_uuid(False) is False
    assert is_valid_uuid("Not a valid UUID") is False
    assert is_valid_uuid(uuid.UUID) is False


@dataclass
class ValidURLTestCase:
    input: Any
    result: bool


VALID_URL_TEST_CASES = [
    ValidURLTestCase(input=55, result=False),
    ValidURLTestCase(input="https://", result=False),
    ValidURLTestCase(input="my-server", result=False),
    ValidURLTestCase(input="http://my-server", result=True),
    ValidURLTestCase(input="http://my-server:8080", result=True),
    ValidURLTestCase(input="http://192.168.1.10", result=True),
    ValidURLTestCase(input="/test", result=True),
    ValidURLTestCase(input="/", result=True),
    ValidURLTestCase(input="http:/192.168.1.10", result=False),
]


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=str(tc.input)) for tc in VALID_URL_TEST_CASES],
)
def test_is_valid_url(test_case: ValidURLTestCase) -> None:
    assert is_valid_url(test_case.input) is test_case.result


def test_duplicates() -> None:
    assert duplicates([2, 4, 6, 8, 4, 6, 12]) == [4, 6]
    assert duplicates(["first", "second", "first", "third", "first", "last"]) == ["first"]
    assert not duplicates([2, 8, 4, 6, 12])
    assert duplicates([]) == []
    assert duplicates([None, None]) == []


def test_compare_lists() -> None:
    list_a = ["black", "blue", "red"]
    list_b = ["black", "green"]
    list_c = ["purple", "yellow"]

    both, in1, in2 = compare_lists(list_a, list_b)
    assert both == ["black"]
    assert in1 == ["blue", "red"]
    assert in2 == ["green"]

    both, in1, in2 = compare_lists(list_c, list_b)
    assert both == []
    assert in1 == list_c
    assert in2 == list_b

    both, in1, in2 = compare_lists(list_c, ["yellow"])
    assert both == ["yellow"]
    assert in1 == ["purple"]
    assert in2 == []


def test_deep_merge_dict() -> None:
    a = {"keyA": 1}
    b = {"keyB": {"sub1": 10}}
    c = {"keyB": {"sub2": 20}}
    d = {"keyA": [10, 20], "keyB": "foo"}
    e = {"keyA": [20, 30], "keyB": "foo"}
    f = {"keyA": None, "keyB": "bar"}
    g = {"keyA": "foo", "keyB": None}
    assert deep_merge_dict(a, b) == {"keyA": 1, "keyB": {"sub1": 10}}
    assert deep_merge_dict(c, b) == {"keyB": {"sub1": 10, "sub2": 20}}
    assert deep_merge_dict(d, e) == {"keyA": [10, 20, 30], "keyB": "foo"}
    assert deep_merge_dict(f, g) == {"keyA": "foo", "keyB": "bar"}


def test_str_to_bool() -> None:
    assert str_to_bool(True) is True
    assert str_to_bool(False) is False

    assert str_to_bool(1) is True
    assert str_to_bool(0) is False

    assert str_to_bool("True") is True
    assert str_to_bool("TRUE") is True
    assert str_to_bool("Yes") is True
    assert str_to_bool("yes") is True
    assert str_to_bool("1") is True
    assert str_to_bool("on") is True
    assert str_to_bool("y") is True

    assert str_to_bool("No") is False
    assert str_to_bool("False") is False
    assert str_to_bool("f") is False

    with pytest.raises(ValueError):
        str_to_bool("NotABool")

    with pytest.raises(TypeError):
        str_to_bool(tuple("a", "b", "c"))


def test_base36() -> None:
    assert base36encode(1412823931503067241) == "AQF8AA0006EH"
    assert base36decode("AQF8AA0006EH") == 1412823931503067241
    assert base36decode(base36encode(-9223372036721928027)) == -9223372036721928027
    assert base36decode(base36encode(1412823931503067241)) == 1412823931503067241


def test_base16() -> None:
    assert base16encode(1412823931503067241) == "139b5be157694069"
    assert base16decode("139b5be157694069") == 1412823931503067241
    assert base16decode(base16encode(-9223372036721928027)) == -9223372036721928027
    assert base16decode(base16encode(1412823931503067241)) == 1412823931503067241


def test_dict_hash() -> None:
    assert dict_hash({"a": 1, "b": 2}) == "608de49a4600dbb5b173492759792e4a"
    assert dict_hash({"b": 2, "a": 1}) == "608de49a4600dbb5b173492759792e4a"
    assert dict_hash({"b": 2, "a": {"c": 1, "d": 2}}) == "4d8f1a3d03e0b487983383d0ff984d13"
    assert dict_hash({"b": 2, "a": {"d": 2, "c": 1}}) == "4d8f1a3d03e0b487983383d0ff984d13"
    assert dict_hash({}) == "99914b932bd37a50b983c5e7c90ae93b"


async def test_extract_fields(query_01: str) -> None:
    document = parse(query_01)
    expected_response = {
        "TestPerson": {
            "edges": {
                "node": {
                    "cars": {"edges": {"node": {"name": {"value": None}}}},
                    "name": {"value": None},
                },
            },
        },
    }
    assert await extract_fields(document.definitions[0].selection_set) == expected_response


async def test_extract_fields_fragment(query_02: str) -> None:
    document = parse(query_02)

    expected_response = {
        "TestPerson": {
            "edges": {
                "node": {
                    "cars": {
                        "edges": {
                            "node": {
                                "member_of_groups": {
                                    "edges": {"node": {"id": None}},
                                },
                                "mpg": {"is_protected": None, "value": None},
                                "name": {"value": None},
                                "nbr_engine": {"value": None},
                            },
                        },
                    },
                    "name": {"value": None},
                },
            },
        },
    }

    assert await extract_fields(document.definitions[0].selection_set) == expected_response


def test_write_to_file() -> None:
    tmp_dir = tempfile.TemporaryDirectory()
    directory = Path(tmp_dir.name)

    with pytest.raises(FileExistsError):
        write_to_file(directory, "placeholder")

    assert write_to_file(directory / "file.txt", "placeholder") is True
    assert write_to_file(directory / "file.txt", "placeholder") is True
    assert write_to_file(directory / "file.txt", "") is True
    assert write_to_file(directory / "file.txt", None) is True
    assert write_to_file(directory / "file.txt", 1234) is True
    assert write_to_file(directory / "file.txt", {"key": "value"}) is True

    tmp_dir.cleanup()


def test_calculate_time_diff() -> None:
    time1 = Instant.now().subtract(seconds=98).format_iso()
    assert calculate_time_diff(time1) == "1m and 38s ago"

    time2 = Instant.now().subtract(hours=1, minutes=12, seconds=34).format_iso()
    assert calculate_time_diff(time2) == "1h 12m and 34s ago"

    time3 = Instant.now().format_iso()
    assert calculate_time_diff(time3) == "now"

    time4 = Instant.now().subtract(seconds=23).format_iso()
    assert calculate_time_diff(time4) == "23s ago"

    time5 = Instant.now().subtract(hours=77, minutes=12, seconds=34).format_iso()
    assert calculate_time_diff(time5) == "3d and 5h ago"


def test_decode_json_success() -> None:
    """Test decode_json with valid JSON response."""
    mock_response = Mock()
    mock_response.json.return_value = {"status": "ok", "data": {"key": "value"}}

    result = decode_json(mock_response)
    assert result == {"status": "ok", "data": {"key": "value"}}


def test_decode_json_failure_with_content() -> None:
    """Test decode_json with invalid JSON response includes server content in error message."""
    mock_response = Mock()
    mock_response.json.side_effect = json.decoder.JSONDecodeError("Invalid JSON", "document", 0)
    mock_response.text = "Internal Server Error: Database connection failed"
    mock_response.url = "https://example.com/api/graphql"

    with pytest.raises(JsonDecodeError) as exc_info:
        decode_json(mock_response)

    error_message = str(exc_info.value)
    assert "Unable to decode response as JSON data from https://example.com/api/graphql" in error_message
    assert "Server response: Internal Server Error: Database connection failed" in error_message


def test_decode_json_failure_without_content() -> None:
    """Test decode_json with invalid JSON response and no content."""
    mock_response = Mock()
    mock_response.json.side_effect = json.decoder.JSONDecodeError("Invalid JSON", "document", 0)
    mock_response.text = ""
    mock_response.url = "https://example.com/api/graphql"

    with pytest.raises(JsonDecodeError) as exc_info:
        decode_json(mock_response)

    error_message = str(exc_info.value)
    assert "Unable to decode response as JSON data from https://example.com/api/graphql" in error_message
    # Should not include server response part when content is empty
    assert "Server response:" not in error_message


def test_json_decode_error_custom_message() -> None:
    """Test JsonDecodeError with custom message does not override custom message."""
    custom_message = "Custom error message"
    error = JsonDecodeError(message=custom_message, content="server error", url="https://example.com")

    assert str(error) == custom_message
    assert error.content == "server error"
    assert error.url == "https://example.com"
