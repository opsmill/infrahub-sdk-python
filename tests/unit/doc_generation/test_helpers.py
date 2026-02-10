from __future__ import annotations

from doc_generation.helpers import build_config_properties, get_env_vars


class TestGetEnvVars:
    def test_returns_dict(self) -> None:
        # Act
        result = get_env_vars()

        # Assert
        assert isinstance(result, dict)

    def test_values_are_lists_of_strings(self) -> None:
        # Act
        result = get_env_vars()

        # Assert
        for key, values in result.items():
            assert isinstance(key, str)
            assert isinstance(values, list)
            for v in values:
                assert isinstance(v, str)

    def test_env_vars_are_upper_case(self) -> None:
        # Act
        result = get_env_vars()

        # Assert
        for values in result.values():
            for v in values:
                assert v == v.upper()

    def test_address_field_has_env_var(self) -> None:
        # Act
        result = get_env_vars()

        # Assert
        assert "address" in result
        assert len(result["address"]) > 0


class TestBuildConfigProperties:
    def test_returns_list(self) -> None:
        # Act
        result = build_config_properties()

        # Assert
        assert isinstance(result, list)
        assert len(result) > 0

    def test_each_property_has_required_keys(self) -> None:
        # Arrange
        required_keys = {"name", "description", "type", "choices", "default", "env_vars"}

        # Act
        result = build_config_properties()

        # Assert
        for prop in result:
            assert required_keys.issubset(prop.keys())

    def test_address_property_exists(self) -> None:
        # Act
        result = build_config_properties()

        # Assert
        names = [p["name"] for p in result]
        assert "address" in names

    def test_address_has_env_vars(self) -> None:
        # Act
        result = build_config_properties()

        # Assert
        address_prop = next(p for p in result if p["name"] == "address")
        assert len(address_prop["env_vars"]) > 0
