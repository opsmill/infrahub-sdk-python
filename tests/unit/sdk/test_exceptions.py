from __future__ import annotations

from dataclasses import dataclass

import pytest

from infrahub_sdk.exceptions import (
    Error,
    FieldNotLoadedError,
    FieldNotLoadedWarning,
    SelectionConflictError,
    SelectionFieldNotFoundError,
    UninitializedError,
)

SELECTION_ERRORS = [FieldNotLoadedError, SelectionFieldNotFoundError, SelectionConflictError]


@pytest.mark.parametrize("error_class", SELECTION_ERRORS)
def test_selection_errors_are_direct_subclasses_of_error(error_class: type[Error]) -> None:
    assert error_class.__bases__ == (Error,)


@pytest.mark.parametrize("error_class", SELECTION_ERRORS)
@pytest.mark.parametrize("absorbing_class", [AttributeError, UninitializedError, ValueError])
def test_selection_errors_are_not_absorbed_by_existing_handlers(
    error_class: type[Error], absorbing_class: type[Exception]
) -> None:
    assert not issubclass(error_class, absorbing_class)


def test_field_not_loaded_warning_is_a_future_warning() -> None:
    assert FieldNotLoadedWarning.__bases__ == (FutureWarning,)
    assert issubclass(FieldNotLoadedWarning, FutureWarning)


def test_field_not_loaded_error_attributes() -> None:
    error = FieldNotLoadedError(
        kind="InfraDevice",
        field="description",
        selection="only=['name']",
        message="InfraDevice.description was not fetched (selection: only=['name']).",
    )

    assert error.kind == "InfraDevice"
    assert error.field == "description"
    assert error.selection == "only=['name']"
    assert error.message == "InfraDevice.description was not fetched (selection: only=['name'])."
    assert str(error) == "InfraDevice.description was not fetched (selection: only=['name'])."


def test_field_not_loaded_error_default_message() -> None:
    error = FieldNotLoadedError(kind="InfraDevice", field="description", selection=None)

    assert error.selection is None
    assert str(error) == "InfraDevice.description was not fetched."


def test_selection_field_not_found_error_for_unknown_name() -> None:
    error = SelectionFieldNotFoundError(kind="InfraDevice", field="colour")

    assert error.kind == "InfraDevice"
    assert error.field == "colour"
    assert error.implementing_kinds == []
    assert str(error) == "'colour' is not an attribute or relationship of InfraDevice."


def test_selection_field_not_found_error_for_implementing_kind_name() -> None:
    error = SelectionFieldNotFoundError(
        kind="TestGenericDevice", field="role", implementing_kinds=["TestRouter", "TestSwitch"]
    )

    assert error.implementing_kinds == ["TestRouter", "TestSwitch"]
    assert str(error) == (
        "'role' is not defined on TestGenericDevice, only on the kinds implementing it (TestRouter, TestSwitch). "
        "Pass fragment=True to select it."
    )


@dataclass
class ConflictMessageCase:
    name: str
    parameters: list[str]
    expected_message: str


CONFLICT_MESSAGE_CASES = [
    ConflictMessageCase(
        name="include",
        parameters=["only", "include"],
        expected_message="'only' cannot be combined with 'include'; pass 'only' on its own.",
    ),
    ConflictMessageCase(
        name="exclude",
        parameters=["only", "exclude"],
        expected_message="'only' cannot be combined with 'exclude'; pass 'only' on its own.",
    ),
    ConflictMessageCase(
        name="include-and-exclude",
        parameters=["only", "include", "exclude"],
        expected_message="'only' cannot be combined with 'include' or 'exclude'; pass 'only' on its own.",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in CONFLICT_MESSAGE_CASES])
def test_selection_conflict_error_message(case: ConflictMessageCase) -> None:
    error = SelectionConflictError(parameters=case.parameters)

    assert error.parameters == case.parameters
    assert str(error) == case.expected_message
