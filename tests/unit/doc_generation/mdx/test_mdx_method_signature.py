"""Tests for MethodSignature."""

from __future__ import annotations

from docs.docs_generation.content_gen_methods.mdx.mdx_collapsed_overload_section import (
    MethodSignature,
)
from docs.docs_generation.content_gen_methods.mdx.mdx_section import MdxSection

from .conftest import make_method_section


class TestMethodSignatureParamCount:
    def test_simple_signature_returns_correct_count(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self, kind: str, id: int)"))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 2

    def test_self_only_returns_zero(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self)"))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 0

    def test_kwargs_counts_as_one(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self, **kwargs: Any)"))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 1

    def test_args_and_kwargs_count_separately(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self, *args: str, **kwargs: Any)"))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 2

    def test_nested_brackets_not_split(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self, kind: dict[str, int], other: list[str])"))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 2

    def test_deeply_nested_generics(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self, x: dict[str, list[tuple[int, ...]]])"))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 1

    def test_signature_with_return_type(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self, kind: str) -> InfrahubNode"))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 1

    def test_default_values_dont_affect_count(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self, kind: str = ..., id: int = None)"))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 2

    def test_real_world_get_signature(self) -> None:
        # Arrange
        signature = (
            "get(self, kind: str | type[SchemaType], raise_when_missing: bool = True, "
            "at: Timestamp | None = None, branch: str | None = None, "
            "timeout: int | None = None, id: str | None = None, "
            "hfid: list[str] | None = None, include: list[str] | None = None, "
            "exclude: list[str] | None = None, populate_store: bool = True, "
            "fragment: bool = False, prefetch_relationships: bool = False, "
            "property: bool = False, include_metadata: bool = False, "
            "**kwargs: Any) -> InfrahubNode | SchemaType | None"
        )
        sig = MethodSignature(make_method_section("get", signature))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 15

    def test_empty_signature(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get()"))

        # Act
        result = sig.param_count()

        # Assert
        assert result == 0

    def test_no_code_fence_returns_zero(self) -> None:
        # Arrange
        section = MdxSection(name="get", heading_level=4, _lines=["#### `get`", "", "Some description."])
        sig = MethodSignature(section)

        # Act
        result = sig.param_count()

        # Assert
        assert result == 0


class TestMethodSignatureReturnType:
    def test_returns_none_type(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("value", "value(self, value: Any) -> None"))

        # Act
        result = sig.return_type()

        # Assert
        assert result == "None"

    def test_returns_concrete_type(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("value", "value(self) -> Any"))

        # Act
        result = sig.return_type()

        # Assert
        assert result == "Any"

    def test_no_return_annotation_returns_empty(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self, kind: str)"))

        # Act
        result = sig.return_type()

        # Assert
        assert not result

    def test_generic_return_type(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self) -> dict[str, list[int]]"))

        # Act
        result = sig.return_type()

        # Assert
        assert result == "dict[str, list[int]]"

    def test_union_return_type(self) -> None:
        # Arrange
        sig = MethodSignature(make_method_section("get", "get(self, kind: str) -> InfrahubNode | None"))

        # Act
        result = sig.return_type()

        # Assert
        assert result == "InfrahubNode | None"

    def test_no_code_fence_returns_empty(self) -> None:
        # Arrange
        section = MdxSection(name="get", heading_level=4, _lines=["#### `get`", "", "Some description."])
        sig = MethodSignature(section)

        # Act
        result = sig.return_type()

        # Assert
        assert not result
