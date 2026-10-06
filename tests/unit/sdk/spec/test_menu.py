from __future__ import annotations

import pytest

from infrahub_sdk.exceptions import ValidationError
from infrahub_sdk.spec.menu import MenuFile
from infrahub_sdk.yaml import InfrahubFile


@pytest.fixture
def menu_content() -> dict:
    return {"apiVersion": "infrahub.app/v1", "kind": "Menu", "spec": {"data": [{"name": "Devices"}]}}


@pytest.fixture
def menu_content_bad_spec(menu_content: dict) -> dict:
    menu_content["spec"]["data"] = "not-a-list"
    return menu_content


def test_validate_content(menu_content: dict) -> None:
    menu = MenuFile(location="some/path", content=menu_content)
    menu.validate_content()

    assert menu.spec.kind == "CoreMenuItem"
    assert menu.spec.data == [{"name": "Devices"}]


def test_validate_content_wrong_kind(menu_content: dict) -> None:
    menu_content["kind"] = "Object"
    menu = MenuFile(location="some/path", content=menu_content)
    with pytest.raises(ValidationError, match=r"^some/path: File is not an Infrahub Menu file$") as exc:
        menu.validate_content()

    assert exc.value.identifier == "some/path"


def test_validate_content_invalid_spec(menu_content_bad_spec: dict) -> None:
    menu = MenuFile(location="some/path", content=menu_content_bad_spec)
    with pytest.raises(ValidationError, match=r"^some/path: data \| Input should be a valid list") as exc:
        menu.validate_content()

    assert exc.value.identifier == "some/path"
    assert exc.value.messages == ["data | Input should be a valid list, received 'not-a-list' (list_type)"]


def test_spec_invalid(menu_content_bad_spec: dict) -> None:
    menu = MenuFile(location="some/path", content=menu_content_bad_spec)
    # Load the file envelope only, so the spec is first built by the property.
    InfrahubFile.validate_content(menu)
    with pytest.raises(ValidationError, match=r"^some/path: data \| Input should be a valid list") as exc:
        _ = menu.spec

    assert exc.value.messages == ["data | Input should be a valid list, received 'not-a-list' (list_type)"]


def test_spec_before_validate_content_is_not_a_validation_error(menu_content: dict) -> None:
    menu = MenuFile(location="some/path", content=menu_content)
    with pytest.raises(ValueError, match=r"^_data hasn't been initialized yet$"):
        _ = menu.spec
