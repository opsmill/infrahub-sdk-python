from datetime import datetime
from typing import Union

VARIABLE_TYPE_MAPPING = (
    (str, "String!"),
    (Union[str, None], "String"),
    (int, "Int!"),
    (Union[int, None], "Int"),
    (float, "Float!"),
    (Union[float, None], "Float"),
    (bool, "Boolean!"),
    (Union[bool, None], "Boolean"),
    (datetime, "DateTime!"),
    (Union[datetime, None], "DateTime"),
)
