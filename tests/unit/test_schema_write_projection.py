from infrahub_sdk.schema._write_projection import normalize_schema_for_load  # noqa: PLC2701


def test_normalize_strips_read_only_and_internal_fields() -> None:
    payload = {
        "version": "1.0",
        "nodes": [
            {
                "id": None,
                "state": "present",
                "namespace": "Test",
                "name": "Widget",
                "used_by": ["TestOther"],
                "hierarchy": None,
                "attributes": [
                    {
                        "name": "field_one",
                        "kind": "Text",
                        "read_only": False,
                        "inherited": False,
                        "parameters": {"id": None, "state": "present", "regex": None, "min_length": 3},
                        "computed_attribute": {"kind": "Jinja2", "jinja2_template": "T{{x}}", "transform": None},
                    }
                ],
            }
        ],
        "extensions": {"id": None, "state": "present", "nodes": []},
    }

    result = normalize_schema_for_load(payload)

    node = result["nodes"][0]
    attribute = node["attributes"][0]

    assert "used_by" not in node
    assert "hierarchy" not in node
    assert "inherited" not in attribute
    # write-settable fields are preserved
    assert attribute["name"] == "field_one"
    assert attribute["kind"] == "Text"
    assert attribute["read_only"] is False
    # nested parameters keep only the fields valid for the write contract
    assert set(attribute["parameters"]) == {"regex", "min_length"}
    # the discriminated computed-attribute drops the field that does not match its kind
    assert attribute["computed_attribute"] == {"kind": "Jinja2", "jinja2_template": "T{{x}}"}
    # the extensions block is a write field, but its read-only id/state are stripped
    assert result["extensions"] == {"nodes": []}


def test_normalize_passes_through_non_dict() -> None:
    not_a_dict: object = []
    assert normalize_schema_for_load(not_a_dict) == []  # type: ignore[arg-type]
