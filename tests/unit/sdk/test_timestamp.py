import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, TypedDict

import pytest
import whenever
from whenever import Instant, ZonedDateTime

from infrahub_sdk.exceptions import TimestampFormatError
from infrahub_sdk.timestamp import Timestamp

UTC = timezone.utc  # Required for older versions of Python
WHENEVER_0_11 = tuple(int(part) for part in whenever.__version__.split(".")[:2]) >= (0, 11)


def test_init_empty() -> None:
    t1 = Timestamp()
    assert isinstance(t1, Timestamp)
    assert t1.to_datetime() == t1._obj.to_stdlib()

    t2 = Timestamp(None)
    assert isinstance(t2, Timestamp)
    assert t2.to_datetime() == t2._obj.to_stdlib()


def test_init_timestamp() -> None:
    t1 = Timestamp()
    t2 = Timestamp(t1)
    assert t1.to_string() == t2.to_string()
    assert isinstance(t2, Timestamp)
    assert t2.to_datetime() == t2._obj.to_stdlib()


def test_parse_string() -> None:
    ref = "2022-01-01T10:00:00.000000Z"

    assert Timestamp._parse_string(ref).to_instant() == Instant.parse_iso(ref)
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
    ("input_str", "expected_datetime"),
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
    ("input_str", "expected_str", "expected_str_no_z"),
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


class ShiftUnits(TypedDict, total=False):
    days: int
    hours: int


@dataclass
class DaylightSavingCase:
    name: str
    start: ZonedDateTime
    operation: Literal["add", "subtract"]
    units: ShiftUnits
    expected: str
    expected_from_whenever_0_11: str | None = None
    """whenever 0.11 keeps the starting offset when the shift by days lands in a repeated hour."""


DAYLIGHT_SAVING_CASES = [
    DaylightSavingCase(
        name="add-into-skipped-hour",
        start=ZonedDateTime(2024, 3, 30, 2, 30, tz="Europe/Amsterdam"),
        operation="add",
        units={"days": 1},
        expected="2024-03-31T03:30:00.000000+02:00",
    ),
    DaylightSavingCase(
        name="subtract-into-skipped-hour",
        start=ZonedDateTime(2024, 4, 1, 2, 30, tz="Europe/Amsterdam"),
        operation="subtract",
        units={"days": 1},
        expected="2024-03-31T03:30:00.000000+02:00",
    ),
    DaylightSavingCase(
        name="add-into-repeated-hour",
        start=ZonedDateTime(2024, 10, 26, 2, 30, tz="Europe/Amsterdam"),
        operation="add",
        units={"days": 1},
        expected="2024-10-27T02:30:00.000000+02:00",
    ),
    DaylightSavingCase(
        name="subtract-into-repeated-hour",
        start=ZonedDateTime(2024, 10, 28, 2, 30, tz="Europe/Amsterdam"),
        operation="subtract",
        units={"days": 1},
        expected="2024-10-27T02:30:00.000000+02:00",
        expected_from_whenever_0_11="2024-10-27T02:30:00.000000+01:00",
    ),
    DaylightSavingCase(
        name="subtract-days-into-repeated-hour-then-hours",
        start=ZonedDateTime(2024, 10, 28, 2, 30, tz="Europe/Amsterdam"),
        operation="subtract",
        units={"days": 1, "hours": 2},
        expected="2024-10-27T00:30:00.000000+02:00",
        expected_from_whenever_0_11="2024-10-27T01:30:00.000000+02:00",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in DAYLIGHT_SAVING_CASES])
def test_shift_across_daylight_saving_change_resolves_without_warning(case: DaylightSavingCase) -> None:
    timestamp = Timestamp(case.start)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = timestamp.add(**case.units) if case.operation == "add" else timestamp.subtract(**case.units)

    expected = case.expected_from_whenever_0_11 if WHENEVER_0_11 and case.expected_from_whenever_0_11 else case.expected
    assert result.to_string() == expected


@pytest.mark.parametrize(
    ("input_str", "expected_str"),
    [
        pytest.param("2024-03-31T02:30:00[Europe/Amsterdam]", "2024-03-31T03:30:00.000000+02:00", id="skipped-hour"),
        pytest.param("2024-10-27T02:30:00[Europe/Amsterdam]", "2024-10-27T02:30:00.000000+02:00", id="repeated-hour"),
    ],
)
def test_parse_zoned_string_across_daylight_saving_change_without_warning(input_str: str, expected_str: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        timestamp = Timestamp(input_str)

    assert timestamp.to_string() == expected_str


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
