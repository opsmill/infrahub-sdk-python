from enum import Enum

import pytest


class MyStrEnum(str, Enum):
    VALUE1 = "value1"
    VALUE2 = "value2"


class MyIntEnum(int, Enum):
    VALUE1 = 12
    VALUE2 = 24


@pytest.fixture
def query_data_no_filter():
    data = {
        "device": {
            "name": {"value": None},
            "description": {"value": None},
            "interfaces": {"name": {"value": None}},
        }
    }

    return data


@pytest.fixture
def query_data_alias():
    data = {
        "device": {
            "name": {"@alias": "new_name", "value": None},
            "description": {"value": {"@alias": "myvalue"}},
            "interfaces": {"@alias": "myinterfaces", "name": {"value": None}},
        }
    }

    return data


@pytest.fixture
def query_data_fragment():
    data = {
        "device": {
            "name": {"value": None},
            "...on Builtin": {
                "description": {"value": None},
                "interfaces": {"name": {"value": None}},
            },
        }
    }

    return data


@pytest.fixture
def query_data_empty_filter():
    data = {
        "device": {
            "@filters": {},
            "name": {"value": None},
            "description": {"value": None},
            "interfaces": {"name": {"value": None}},
        }
    }

    return data


@pytest.fixture
def query_data_filters_01():
    data = {
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
    return data


@pytest.fixture
def query_data_filters_02():
    data = {
        "device": {
            "@filters": {"name__value": "myname", "integer__value": 44, "enumstr__value": MyStrEnum.VALUE2},
            "name": {"value": None},
            "interfaces": {
                "@filters": {"enabled__value": True, "enumint__value": MyIntEnum.VALUE1},
                "name": {"value": None},
            },
        }
    }
    return data


@pytest.fixture
def input_data_01():
    data = {
        "data": {
            "name": {"value": "$name"},
            "some_number": {"value": 88},
            "some_bool": {"value": True},
            "some_list": {"value": ["value1", 33]},
            "query": {"value": "my_query"},
        }
    }
    return data
