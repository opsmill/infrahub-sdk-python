from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Protocol, Union, runtime_checkable

if TYPE_CHECKING:
    import ipaddress

    from infrahub_sdk.schema import MainSchemaTypes


@runtime_checkable
class RelatedNode(Protocol): ...


@runtime_checkable
class RelatedNodeSync(Protocol): ...


@runtime_checkable
class Attribute(Protocol):
    name: str
    id: Optional[str]
    is_default: Optional[bool]
    is_from_profile: Optional[bool]
    is_inherited: Optional[bool]
    updated_at: Optional[str]
    is_visible: Optional[bool]
    is_protected: Optional[bool]


# TODO: Consolidate them into on single set of classes
# Classes for builtin schema attribute
class String(Attribute):
    value: str


class StringOptional(Attribute):
    value: Optional[str]


class Integer(Attribute):
    value: int


class IntegerOptional(Attribute):
    value: Optional[int]


class Boolean(Attribute):
    value: bool


class BooleanOptional(Attribute):
    value: Optional[bool]


class DateTime(Attribute):
    value: str


class DateTimeOptional(Attribute):
    value: Optional[str]


class Enum(Attribute):
    value: str


class EnumOptional(Attribute):
    value: Optional[str]


class URL(Attribute):
    value: str


class URLOptional(Attribute):
    value: Optional[str]


class Dropdown(Attribute):
    value: str


class DropdownOptional(Attribute):
    value: Optional[str]


class IPNetwork(Attribute):
    value: Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


class IPNetworkOptional(Attribute):
    value: Optional[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]


class IPHost(Attribute):
    value: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


class IPHostOptional(Attribute):
    value: Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]


class HashedPassword(Attribute):
    value: str


class HashedPasswordOptional(Attribute):
    value: Any


class JSONAttribute(Attribute):
    value: Any


class JSONAttributeOptional(Attribute):
    value: Optional[Any]


# Classes for user defined schema attribute
class IDAttribute(Attribute):
    value: int


class IDAttributeOptional(Attribute):
    value: Optional[int]


class DropdownAttribute(Attribute):
    value: str


class DropdownAttributeOptional(Attribute):
    value: Optional[str]


class TextAttribute(Attribute):
    value: str


class TextAttributeOptional(Attribute):
    value: Optional[str]


class TextAreaAttribute(Attribute):
    value: str


class TextAreaAttributeOptional(Attribute):
    value: Optional[str]


class DateTimeAttribute(Attribute):
    value: str


class DateTimeAttributeOptional(Attribute):
    value: Optional[str]


class EmailAttribute(Attribute):
    value: str


class EmailAttributeOptional(Attribute):
    value: Optional[str]


class PasswordAttribute(Attribute):
    value: str


class PasswordAttributeOptional(Attribute):
    value: Optional[str]


class HashedPasswordAttribute(Attribute):
    value: str


class HashedPasswordAttributeOptional(Attribute):
    value: Optional[str]


class URLAttribute(Attribute):
    value: str


class URLAttributeOptional(Attribute):
    value: Optional[str]


class FileAttribute(Attribute):
    value: str


class FileAttributeOptional(Attribute):
    value: Optional[str]


class MacAddressAttribute(Attribute):
    value: str


class MacAddressAttributeOptional(Attribute):
    value: Optional[str]


class ColorAttribute(Attribute):
    value: str


class ColorAttributeOptional(Attribute):
    value: Optional[str]


class NumberAttribute(Attribute):
    value: float


class NumberAttributeOptional(Attribute):
    value: Optional[float]


class BandwidthAttribute(Attribute):
    value: float


class BandwidthAttributeOptional(Attribute):
    value: Optional[float]


class IPHostAttribute(Attribute):
    value: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


class IPHostAttributeOptional(Attribute):
    value: Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]


class IPNetworkAttribute(Attribute):
    value: Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


class IPNetworkAttributeOptional(Attribute):
    value: Optional[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]


class BooleanAttribute(Attribute):
    value: bool


class BooleanAttributeOptional(Attribute):
    value: Optional[bool]


class CheckboxAttribute(Attribute):
    value: bool


class CheckboxAttributeOptional(Attribute):
    value: Optional[bool]


class ListAttribute(Attribute):
    value: list[Any]


class ListAttributeOptional(Attribute):
    value: Optional[list[Any]]


class AnyAttribute(Attribute):
    value: float


class AnyAttributeOptional(Attribute):
    value: Optional[float]


@runtime_checkable
class CoreNodeBase(Protocol):
    _schema: MainSchemaTypes
    id: str
    display_label: Optional[str]

    @property
    def hfid(self) -> Optional[list[str]]: ...

    @property
    def hfid_str(self) -> Optional[str]: ...

    def get_human_friendly_id_as_string(self, include_kind: bool = False) -> Optional[str]: ...

    def get_kind(self) -> str: ...

    def is_ip_prefix(self) -> bool: ...

    def is_ip_address(self) -> bool: ...

    def is_resource_pool(self) -> bool: ...

    def get_raw_graphql_data(self) -> Optional[dict]: ...

    def extract(self, params: dict[str, str]) -> dict[str, Any]: ...


@runtime_checkable
class CoreNode(CoreNodeBase, Protocol):
    async def save(self, allow_upsert: bool = False, update_group_context: Optional[bool] = None) -> None: ...

    async def delete(self) -> None: ...

    async def update(self, do_full_update: bool) -> None: ...

    async def create(self, allow_upsert: bool = False) -> None: ...

    async def add_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None: ...

    async def remove_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None: ...


@runtime_checkable
class CoreNodeSync(CoreNodeBase, Protocol):
    def save(self, allow_upsert: bool = False, update_group_context: Optional[bool] = None) -> None: ...

    def delete(self) -> None: ...

    def update(self, do_full_update: bool) -> None: ...

    def create(self, allow_upsert: bool = False) -> None: ...

    def add_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None: ...

    def remove_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None: ...
