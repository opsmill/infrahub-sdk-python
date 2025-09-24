from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

CONVERT_OBJECT_MUTATION = """
    mutation($node_id: String!, $target_kind: String!, $fields_mapping: GenericScalar!) {
        ConvertObjectType(data: {
                node_id: $node_id,
                target_kind: $target_kind,
                fields_mapping: $fields_mapping
            }) {
                ok
                node
        }
    }
"""


class ConversionFieldValue(BaseModel):  # Only one of these fields can be not None
    """
    Holds the new value of the destination field during an object conversion.
    Use `attribute_value` to specify the new raw value of an attribute.
    Use `peer_id` to specify new peer of a cardinality one relationship.
    Use `peers_ids` to specify new peers of a cardinality many relationship.
    Only one of `attribute_value`, `peer_id` and `peers_ids` can be specified.
    """

    attribute_value: Any | None = None
    peer_id: str | None = None
    peers_ids: list[str] | None = None

    @model_validator(mode="after")
    def check_only_one_field(self) -> ConversionFieldValue:
        fields = [self.attribute_value, self.peer_id, self.peers_ids]
        set_fields = [f for f in fields if f is not None]
        if len(set_fields) != 1:
            raise ValueError("Exactly one of `attribute_value`, `peer_id`, or `peers_ids` must be set")
        return self


class ConversionFieldInput(BaseModel):
    """
    Indicates how to fill in the value of the destination field during an object conversion.
    Use `source_field` to reuse the value of the corresponding field of the object being converted.
    Use `data` to specify the new value for the field.
    Use `use_default_value` to set the destination field to its schema default.
    Only one of `source_field`, `data`, or `use_default_value` can be specified.
    """

    source_field: str | None = None
    data: ConversionFieldValue | None = None
    use_default_value: bool = False

    @model_validator(mode="after")
    def check_only_one_field(self) -> ConversionFieldInput:
        fields_set = [self.source_field is not None, self.data is not None, self.use_default_value is True]
        if sum(fields_set) != 1:
            raise ValueError("Exactly one of `source_field`, `data` or `use_default_value` must be set")
        return self
