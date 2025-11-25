from datetime import datetime

VARIABLE_TYPE_MAPPING = (
    (str, "String!"),
    (str | None, "String"),
    (int, "Int!"),
    (int | None, "Int"),
    (float, "Float!"),
    (float | None, "Float"),
    (bool, "Boolean!"),
    (bool | None, "Boolean"),
    (datetime, "DateTime!"),
    (datetime | None, "DateTime"),
)
