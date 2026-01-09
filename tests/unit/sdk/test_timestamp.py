from datetime import datetime, timezone

import pytest
from whenever import Instant

from infrahub_sdk.exceptions import TimestampFormatError
from infrahub_sdk.timestamp import Timestamp

UTC = timezone.utc  # Required for older versions of Python


def test_init_empty() -> None:
    t1 = Timestamp()
    assert isinstance(t1, Timestamp)
    assert t1.to_datetime() == t1._obj.py_datetime()

    t2 = Timestamp(None)
    assert isinstance(t2, Timestamp)
    assert t2.to_datetime() == t2._obj.py_datetime()


def test_init_timestamp() -> None:
    t1 = Timestamp()
    t2 = Timestamp(t1)
    assert t1.to_string() == t2.to_string()
    assert isinstance(t2, Timestamp)
    assert t2.to_datetime() == t2._obj.py_datetime()


def test_parse_string() -> None:
    REF = "2022-01-01T10:00:00.000000Z"

    assert Timestamp._parse_string(REF).to_instant() == Instant.parse_iso(REF)
    assert Timestamp._parse_string("5m")
    assert Timestamp._parse_string("10min")
    assert Timestamp._parse_string("2h")
    assert Timestamp._parse_string("10s")
    assert Timestamp._parse_string("2025-01-02")
    assert Timestamp._parse_string("2024-06-04T03:13:03.386270")
    assert Timestamp._parse_string("2025-03-05T18:01:52+01:00")
    with pytest.raises(TimestampFormatError):
        Timestamp._parse_string("notvalid")


@pytest.mark.parametrize(
    "input_str,expected_datetime",
    [
        pytest.param(
            "2022-01-01T10:01:01.123000Z", datetime(2022, 1, 1, 10, 1, 1, 123000, tzinfo=UTC), id="milliseconds"
        ),
        pytest.param(
            "2023-12-31T23:59:59.999999Z", datetime(2023, 12, 31, 23, 59, 59, 999999, tzinfo=UTC), id="microseconds"
        ),
        pytest.param(
            "2025-02-25T05:58:54.524191Z",
            datetime(2025, 2, 25, 5, 58, 54, 524191, tzinfo=UTC),
            id="milliseconds_with_offset",
        ),
        pytest.param(
            "2025-02-25T06:38:37.753389419Z",
            datetime(2025, 2, 25, 6, 38, 37, 753389, tzinfo=UTC),
            id="nanoseconds",
        ),
    ],
)
def test_to_datetime(input_str: str, expected_datetime: datetime) -> None:
    assert isinstance(Timestamp(input_str).to_datetime(), datetime)
    assert Timestamp(input_str).to_datetime() == expected_datetime


@pytest.mark.parametrize(
    "input_str,expected_str,expected_str_no_z",
    [
        pytest.param(
            "2022-01-01T10:01:01.123000Z",
            "2022-01-01T10:01:01.123000Z",
            "2022-01-01T10:01:01.123000+00:00",
            id="milliseconds",
        ),
        pytest.param(
            "2023-12-31T23:59:59.999999Z",
            "2023-12-31T23:59:59.999999Z",
            "2023-12-31T23:59:59.999999+00:00",
            id="microseconds",
        ),
    ],
)
def test_to_string_default(input_str: str, expected_str: str, expected_str_no_z: str) -> None:
    assert isinstance(Timestamp(input_str).to_string(), str)
    assert Timestamp(input_str).to_string() == expected_str
    assert Timestamp(input_str).to_string(with_z=False) == expected_str_no_z


def test_add() -> None:
    t1 = Timestamp("2022-01-01T10:01:01.123Z")
    t2 = t1.add(hours=1)
    assert t2.to_string() == "2022-01-01T11:01:01.123000Z"


def test_subtract() -> None:
    t1 = Timestamp("2022-01-01T10:05:01.123Z")
    t2 = t1.subtract(hours=1)
    assert t2.to_string() == "2022-01-01T09:05:01.123000Z"


def test_compare() -> None:
    time1 = "2022-01-01T11:00:00.000000Z"
    time2 = "2022-02-01T11:00:00.000000Z"

    t11 = Timestamp(time1)
    t12 = Timestamp(time1)

    t21 = Timestamp(time2)

    assert t11 < t21
    assert t21 > t12
    assert t11 <= t12
    assert t11 >= t12
    assert t11 == t12


def test_serialize() -> None:
    time_no_z = "2022-01-01T11:00:00.000000+00:00"
    time = "2022-01-01T11:00:00.000000Z"
    timestamp = Timestamp(time)

    assert timestamp.to_string(with_z=False) == time_no_z
    assert timestamp.to_string() == time


@pytest.mark.parametrize("invalid_str", ["blurple", "1122334455667788", "2023-45-99"])
def test_invalid_raises_correct_error(invalid_str: str) -> None:
    with pytest.raises(TimestampFormatError):
        Timestamp(invalid_str)
