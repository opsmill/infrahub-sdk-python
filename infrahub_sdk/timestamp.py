from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone
from typing import Literal

from whenever import Date, Instant, LocalDateTime, OffsetDateTime, Time, ZonedDateTime

from .exceptions import TimestampFormatError

UTC = timezone.utc  # Required for older versions of Python

REGEX_MAPPING = {
    "seconds": r"(\d+)(s|sec|second|seconds)",
    "minutes": r"(\d+)(m|min|minute|minutes)",
    "hours": r"(\d+)(h|hour|hours)",
}


class Timestamp:
    _obj: ZonedDateTime

    def __init__(self, value: str | ZonedDateTime | Timestamp | None = None):
        if value and isinstance(value, ZonedDateTime):
            self._obj = value
        elif value and isinstance(value, self.__class__):
            self._obj = value._obj
        elif isinstance(value, str):
            self._obj = self._parse_string(value)
        else:
            self._obj = ZonedDateTime.now("UTC").round(unit="microsecond")

    @property
    def obj(self) -> ZonedDateTime:
        warnings.warn(
            "Direct access to obj property is deprecated. Use to_string(), to_timestamp(), or to_datetime() instead.",
            UserWarning,
            stacklevel=2,
        )
        return self._obj

    @classmethod
    def _parse_string(cls, value: str) -> ZonedDateTime:
        try:
            zoned_date = ZonedDateTime.parse_common_iso(value)
            return zoned_date
        except ValueError:
            pass

        try:
            instant_date = Instant.parse_common_iso(value)
            return instant_date.to_tz("UTC")
        except ValueError:
            pass

        try:
            local_date_time = LocalDateTime.parse_common_iso(value)
            return local_date_time.assume_utc().to_tz("UTC")
        except ValueError:
            pass

        try:
            offset_date_time = OffsetDateTime.parse_common_iso(value)
            return offset_date_time.to_tz("UTC")
        except ValueError:
            pass

        try:
            date = Date.parse_common_iso(value)
            local_date = date.at(Time(12, 00))
            return local_date.assume_tz("UTC", disambiguate="compatible")
        except ValueError:
            pass

        params: dict[str, float] = {}
        for key, regex in REGEX_MAPPING.items():
            match = re.search(regex, value)
            if match:
                params[key] = float(match.group(1))

        if params:
            return ZonedDateTime.now("UTC").subtract(**params)  # type: ignore[call-overload]

        raise TimestampFormatError(f"Invalid time format for {value}")

    def __repr__(self) -> str:
        return f"Timestamp: {self.to_string()}"

    def to_string(self, with_z: bool = True) -> str:
        time_str = self.to_datetime().isoformat(timespec="microseconds")
        if with_z and time_str.endswith("+00:00"):
            time_str = time_str[:-6]
            time_str += "Z"
        return time_str

    def to_timestamp(self) -> int:
        return self._obj.timestamp()

    def to_datetime(self) -> datetime:
        return self._obj.py_datetime()

    def get_obj(self) -> ZonedDateTime:
        return self._obj

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Timestamp):
            return NotImplemented
        return self._obj == other._obj

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Timestamp):
            return NotImplemented
        return self._obj < other._obj

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Timestamp):
            return NotImplemented
        return self._obj > other._obj

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Timestamp):
            return NotImplemented
        return self._obj <= other._obj

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Timestamp):
            return NotImplemented
        return self._obj >= other._obj

    def __hash__(self) -> int:
        return hash(self.to_string())

    def add_delta(self, hours: int = 0, minutes: int = 0, seconds: int = 0, microseconds: int = 0) -> Timestamp:
        warnings.warn(
            "add_delta() is deprecated. Use add() instead.",
            UserWarning,
            stacklevel=2,
        )
        return self.add(hours=hours, minutes=minutes, seconds=seconds, microseconds=microseconds)

    def add(
        self,
        years: int = 0,
        months: int = 0,
        weeks: int = 0,
        days: int = 0,
        hours: float = 0,
        minutes: float = 0,
        seconds: float = 0,
        milliseconds: float = 0,
        microseconds: float = 0,
        nanoseconds: int = 0,
        disambiguate: Literal["compatible"] = "compatible",
    ) -> Timestamp:
        return self.__class__(
            self._obj.add(
                years=years,
                months=months,
                weeks=weeks,
                days=days,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
                milliseconds=milliseconds,
                microseconds=microseconds,
                nanoseconds=nanoseconds,
                disambiguate=disambiguate,
            )
        )

    def subtract(
        self,
        years: int = 0,
        months: int = 0,
        weeks: int = 0,
        days: int = 0,
        hours: float = 0,
        minutes: float = 0,
        seconds: float = 0,
        milliseconds: float = 0,
        microseconds: float = 0,
        nanoseconds: int = 0,
        disambiguate: Literal["compatible"] = "compatible",
    ) -> Timestamp:
        return self.__class__(
            self._obj.subtract(
                years=years,
                months=months,
                weeks=weeks,
                days=days,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
                milliseconds=milliseconds,
                microseconds=microseconds,
                nanoseconds=nanoseconds,
                disambiguate=disambiguate,
            )
        )
