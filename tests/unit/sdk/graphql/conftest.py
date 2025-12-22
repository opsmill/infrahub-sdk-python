from enum import Enum
from typing import Any

import pytest


class MyStrEnum(str, Enum):
    VALUE1 = "value1"
    VALUE2 = "value2"


class MyIntEnum(int, Enum):
    VALUE1 = 12
    VALUE2 = 24


@pytest.fixture
def query_data_no_filter() -> dict[str, Any]:
    return {
        "device": {
            "name": {"value": None},
            "description": {"value": None},
            "interfaces": {"name": {"value": None}},
        }
    }


@pytest.fixture
def query_data_alias() -> dict[str, Any]:
    return {
        "device": {
            "name": {"@alias": "new_name", "value": None},
            "description": {"value": {"@alias": "myvalue"}},
            "interfaces": {"@alias": "myinterfaces", "name": {"value": None}},
        }
    }


@pytest.fixture
def query_data_fragment() -> dict[str, Any]:
    return {
        "device": {
            "name": {"value": None},
            "...on Builtin": {
                "description": {"value": None},
                "interfaces": {"name": {"value": None}},
            },
        }
    }


@pytest.fixture
def query_data_empty_filter() -> dict[str, Any]:
    return {
        "device": {
            "@filters": {},
            "name": {"value": None},
            "description": {"value": None},
            "interfaces": {"name": {"value": None}},
        }
    }


@pytest.fixture
def query_data_filters_01() -> dict[str, Any]:
    return {
        "device": {
            "@filters": {"name__value": "$name"},
            "name": {"value": None},
            "description": {"value": None},
            "interfaces": {
                "@filters": {"enabled__value": "$enabled"},
                "name": {"value": None},
            },
        }
    }


@pytest.fixture
def query_data_filters_02() -> dict[str, Any]:
    return {
        "device": {
            "@filters": {"name__value": "myname", "integer__value": 44, "enumstr__value": MyStrEnum.VALUE2},
            "name": {"value": None},
            "interfaces": {
                "@filters": {"enabled__value": True, "enumint__value": MyIntEnum.VALUE1},
                "name": {"value": None},
            },
        }
    }


@pytest.fixture
def input_data_01() -> dict[str, Any]:
    return {
        "data": {
            "name": {"value": "$name"},
            "some_number": {"value": 88},
            "some_bool": {"value": True},
            "some_list": {"value": ["value1", 33]},
            "query": {"value": "my_query"},
        }
    }
