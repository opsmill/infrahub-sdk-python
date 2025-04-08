from __future__ import annotations

import asyncio
import json
from collections.abc import MutableMapping
from enum import Enum
from time import sleep
from typing import TYPE_CHECKING, Any, TypedDict, Union
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field
from typing_extensions import TypeAlias

from ..exceptions import (
    InvalidResponseError,
    JsonDecodeError,
    SchemaNotFoundError,
    ValidationError,
)
from ..graphql import Mutation
from ..queries import SCHEMA_HASH_SYNC_STATUS
from .main import (
    AttributeSchema,
    AttributeSchemaAPI,
    BranchSchema,
    BranchSupportType,
    GenericSchema,
    GenericSchemaAPI,
    NodeSchema,
    NodeSchemaAPI,
    ProfileSchemaAPI,
    RelationshipCardinality,
    RelationshipKind,
    RelationshipSchema,
    RelationshipSchemaAPI,
    SchemaRoot,
    SchemaRootAPI,
    TemplateSchemaAPI,
)

if TYPE_CHECKING:
    from ..client import InfrahubClient, InfrahubClientSync, SchemaType, SchemaTypeSync
    from ..node import InfrahubNode, InfrahubNodeSync

    InfrahubNodeTypes = Union[InfrahubNode, InfrahubNodeSync]


__all__ = [
    "AttributeSchema",
    "AttributeSchemaAPI",
    "BranchSupportType",
    "GenericSchema",
    "GenericSchemaAPI",
    "NodeSchema",
    "NodeSchemaAPI",
    "ProfileSchemaAPI",
    "RelationshipCardinality",
    "RelationshipKind",
    "RelationshipSchema",
    "RelationshipSchemaAPI",
    "SchemaRoot",
    "SchemaRootAPI",
    "TemplateSchemaAPI",
]


class DropdownMutationOptionalArgs(TypedDict):
    color: str | None
    description: str | None
    label: str | None


class DropdownMutation(str, Enum):
    add = "SchemaDropdownAdd"
    remove = "SchemaDropdownRemove"


class EnumMutation(str, Enum):
    add = "SchemaEnumAdd"
    remove = "SchemaEnumRemove"


MainSchemaTypes: TypeAlias = Union[NodeSchema, GenericSchema]
MainSchemaTypesAPI: TypeAlias = Union[NodeSchemaAPI, GenericSchemaAPI, ProfileSchemaAPI, TemplateSchemaAPI]
MainSchemaTypesAll: TypeAlias = Union[
    NodeSchema, GenericSchema, NodeSchemaAPI, GenericSchemaAPI, ProfileSchemaAPI, TemplateSchemaAPI
]


class InfrahubSchemaBase:
    def validate(self, data: dict[str, Any]) -> None:
        SchemaRoot(**data)

    def validate_data_against_schema(self, schema: MainSchemaTypesAPI, data: dict) -> None:
        for key in data.keys():
            if key not in schema.relationship_names + schema.attribute_names:
                identifier = f"{schema.kind}"
                raise ValidationError(
                    identifier=identifier,
                    message=f"{key} is not a valid value for {identifier}",
                )

    def generate_payload_create(
        self,
        schema: MainSchemaTypesAPI,
        data: dict,
        source: str | None = None,
        owner: str | None = None,
        is_protected: bool | None = None,
        is_visible: bool | None = None,
    ) -> dict[str, Any]:
        obj_data: dict[str, Any] = {}
        item_metadata: dict[str, Any] = {}
        if source:
            item_metadata["source"] = str(source)
        if owner:
            item_metadata["owner"] = str(owner)
        if is_protected is not None:
            item_metadata["is_protected"] = is_protected
        if is_visible is not None:
            item_metadata["is_visible"] = is_visible

        for key, value in data.items():
            obj_data[key] = {}
            if key in schema.attribute_names:
                obj_data[key] = {"value": value}
                obj_data[key].update(item_metadata)
            elif key in schema.relationship_names:
                rel = schema.get_relationship(name=key)
                if rel:
                    if rel.cardinality == "one":
                        obj_data[key] = {"id": str(value)}
                        obj_data[key].update(item_metadata)
                    elif rel.cardinality == "many":
                        obj_data[key] = [{"id": str(item)} for item in value]
                        for item in obj_data[key]:
                            item.update(item_metadata)

        return obj_data

    @staticmethod
    def _validate_load_schema_response(response: httpx.Response) -> SchemaLoadResponse:
        if response.status_code == httpx.codes.OK:
            status = response.json()
            return SchemaLoadResponse(hash=status["hash"], previous_hash=status["previous_hash"])

        if response.status_code in [
            httpx.codes.BAD_REQUEST,
            httpx.codes.UNPROCESSABLE_ENTITY,
            httpx.codes.UNAUTHORIZED,
            httpx.codes.FORBIDDEN,
        ]:
            return SchemaLoadResponse(errors=response.json())

        response.raise_for_status()

        raise InvalidResponseError(message=f"Invalid response received from server HTTP {response.status_code}")

    @staticmethod
    def _get_schema_name(schema: type[SchemaType | SchemaTypeSync] | str) -> str:
        if hasattr(schema, "_is_runtime_protocol") and schema._is_runtime_protocol:  # type: ignore[union-attr]
            return schema.__name__  # type: ignore[union-attr]

        if isinstance(schema, str):
            return schema

        raise ValueError("schema must be a protocol or a string")


class InfrahubSchema(InfrahubSchemaBase):
    def __init__(self, client: InfrahubClient):
        self.client = client
        self.cache: dict[str, BranchSchema] = {}

    async def get(
        self,
        kind: type[SchemaType | SchemaTypeSync] | str,
        branch: str | None = None,
        refresh: bool = False,
        timeout: int | None = None,
    ) -> MainSchemaTypesAPI:
        branch = branch or self.client.default_branch

        kind_str = self._get_schema_name(schema=kind)

        if refresh:
            self.cache[branch] = await self._fetch(branch=branch, timeout=timeout)

        if branch in self.cache and kind_str in self.cache[branch].nodes:
            return self.cache[branch].nodes[kind_str]

        # Fetching the latest schema from the server if we didn't fetch it earlier
        #   because we coulnd't find the object on the local cache
        if not refresh:
            self.cache[branch] = await self._fetch(branch=branch, timeout=timeout)

        if branch in self.cache and kind_str in self.cache[branch].nodes:
            return self.cache[branch].nodes[kind_str]

        raise SchemaNotFoundError(identifier=kind_str)

    async def all(
        self,
        branch: str | None = None,
        refresh: bool = False,
        namespaces: list[str] | None = None,
        schema_hash: str | None = None,
    ) -> MutableMapping[str, MainSchemaTypesAPI]:
        """Retrieve the entire schema for a given branch.

        if present in cache, the schema will be served from the cache, unless refresh is set to True
        if the schema is not present in the cache, it will be fetched automatically from the server

        Args:
            branch (str, optional): Name of the branch to query. Defaults to default_branch.
            refresh (bool, optional): Force a refresh of the schema. Defaults to False.
            schema_hash (str, optional): Only refresh if the current schema doesn't match this hash.

        Returns:
            dict[str, MainSchemaTypes]: Dictionary of all schema organized by kind
        """
        branch = branch or self.client.default_branch
        if refresh and branch in self.cache and schema_hash and self.cache[branch].hash == schema_hash:
            refresh = False

        if refresh or branch not in self.cache:
            self.cache[branch] = await self._fetch(branch=branch, namespaces=namespaces)

        return self.cache[branch].nodes

    async def load(
        self, schemas: list[dict], branch: str | None = None, wait_until_converged: bool = False
    ) -> SchemaLoadResponse:
        branch = branch or self.client.default_branch
        url = f"{self.client.address}/api/schema/load?branch={branch}"
        response = await self.client._post(
            url=url, timeout=max(120, self.client.default_timeout), payload={"schemas": schemas}
        )

        if wait_until_converged:
            await self.wait_until_converged(branch=branch)

        return self._validate_load_schema_response(response=response)

    async def wait_until_converged(self, branch: str | None = None) -> None:
        """Wait until the schema has converged on the selected branch or the timeout has been reached"""
        waited = 0
        while True:
            if await self.in_sync(branch=branch):
                self.client.log.info(f"Schema successfully converged after {waited} seconds")
                return

            if waited >= self.client.config.schema_converge_timeout:
                self.client.log.warning(f"Schema not converged after {waited} seconds, proceeding regardless")
                return

            waited += 1
            await asyncio.sleep(delay=1)

    async def in_sync(self, branch: str | None = None) -> bool:
        """Indicate if the schema is in sync across all workers for the provided branch"""
        response = await self.client.execute_graphql(query=SCHEMA_HASH_SYNC_STATUS, branch_name=branch)
        return response["InfrahubStatus"]["summary"]["schema_hash_synced"]

    async def check(self, schemas: list[dict], branch: str | None = None) -> tuple[bool, dict | None]:
        branch = branch or self.client.default_branch
        url = f"{self.client.address}/api/schema/check?branch={branch}"
        response = await self.client._post(
            url=url, timeout=max(120, self.client.default_timeout), payload={"schemas": schemas}
        )

        if response.status_code == httpx.codes.ACCEPTED:
            return True, response.json()

        if response.status_code == httpx.codes.UNPROCESSABLE_ENTITY:
            return False, response.json()

        response.raise_for_status()
        return False, None

    async def _get_kind_and_attribute_schema(
        self, kind: str | InfrahubNodeTypes, attribute: str, branch: str | None = None
    ) -> tuple[str, AttributeSchema]:
        node_kind: str = kind._schema.kind if not isinstance(kind, str) else kind
        node_schema = await self.client.schema.get(kind=node_kind, branch=branch)
        schema_attr = node_schema.get_attribute(name=attribute)

        if schema_attr is None:
            raise ValueError(f"Unable to find attribute {attribute}")

        return node_kind, schema_attr

    async def _mutate_enum_attribute(
        self,
        mutation: EnumMutation,
        kind: str | InfrahubNodeTypes,
        attribute: str,
        option: str | int,
        branch: str | None = None,
    ) -> None:
        node_kind, schema_attr = await self._get_kind_and_attribute_schema(
            kind=kind, attribute=attribute, branch=branch
        )

        if schema_attr.enum is None:
            raise ValueError(f"Attribute '{schema_attr.name}' is not of kind Enum")

        input_data = {"data": {"kind": node_kind, "attribute": schema_attr.name, "enum": option}}

        query = Mutation(mutation=mutation.value, input_data=input_data, query={"ok": None})
        await self.client.execute_graphql(
            query=query.render(),
            branch_name=branch,
            tracker=f"mutation-{mutation.name}-add",
            timeout=max(60, self.client.default_timeout),
        )

    async def add_enum_option(
        self, kind: str | InfrahubNodeTypes, attribute: str, option: str | int, branch: str | None = None
    ) -> None:
        await self._mutate_enum_attribute(
            mutation=EnumMutation.add, kind=kind, attribute=attribute, option=option, branch=branch
        )

    async def remove_enum_option(
        self, kind: str | InfrahubNodeTypes, attribute: str, option: str | int, branch: str | None = None
    ) -> None:
        await self._mutate_enum_attribute(
            mutation=EnumMutation.remove, kind=kind, attribute=attribute, option=option, branch=branch
        )

    async def _mutate_dropdown_attribute(
        self,
        mutation: DropdownMutation,
        kind: str | InfrahubNodeTypes,
        attribute: str,
        option: str,
        branch: str | None = None,
        dropdown_optional_args: DropdownMutationOptionalArgs | None = None,
    ) -> None:
        dropdown_optional_args = dropdown_optional_args or DropdownMutationOptionalArgs(
            color="", description="", label=""
        )

        node_kind, schema_attr = await self._get_kind_and_attribute_schema(
            kind=kind, attribute=attribute, branch=branch
        )

        if schema_attr.kind != "Dropdown":
            raise ValueError(f"Attribute '{schema_attr.name}' is not of kind Dropdown")

        input_data: dict[str, Any] = {
            "data": {
                "kind": node_kind,
                "attribute": schema_attr.name,
                "dropdown": option,
            }
        }
        if mutation == DropdownMutation.add:
            input_data["data"].update(dropdown_optional_args)

        query = Mutation(mutation=mutation.value, input_data=input_data, query={"ok": None})
        await self.client.execute_graphql(
            query=query.render(),
            branch_name=branch,
            tracker=f"mutation-{mutation.name}-remove",
            timeout=max(60, self.client.default_timeout),
        )

    async def remove_dropdown_option(
        self, kind: str | InfrahubNodeTypes, attribute: str, option: str, branch: str | None = None
    ) -> None:
        await self._mutate_dropdown_attribute(
            mutation=DropdownMutation.remove, kind=kind, attribute=attribute, option=option, branch=branch
        )

    async def add_dropdown_option(
        self,
        kind: str | InfrahubNodeTypes,
        attribute: str,
        option: str,
        color: str | None = "",
        description: str | None = "",
        label: str | None = "",
        branch: str | None = None,
    ) -> None:
        dropdown_optional_args = DropdownMutationOptionalArgs(color=color, description=description, label=label)
        await self._mutate_dropdown_attribute(
            mutation=DropdownMutation.add,
            kind=kind,
            attribute=attribute,
            option=option,
            branch=branch,
            dropdown_optional_args=dropdown_optional_args,
        )

    async def fetch(
        self, branch: str, namespaces: list[str] | None = None, timeout: int | None = None
    ) -> MutableMapping[str, MainSchemaTypesAPI]:
        """Fetch the schema from the server for a given branch.

        Args:
            branch (str): Name of the branch to fetch the schema for.
            timeout (int, optional): Overrides default timeout used when querying the GraphQL API. Specified in seconds.

        Returns:
            dict[str, MainSchemaTypes]: Dictionary of all schema organized by kind
        """
        branch_schema = await self._fetch(branch=branch, namespaces=namespaces, timeout=timeout)
        return branch_schema.nodes

    async def _fetch(
        self, branch: str, namespaces: list[str] | None = None, timeout: int | None = None
    ) -> BranchSchema:
        url_parts = [("branch", branch)]
        if namespaces:
            url_parts.extend([("namespaces", ns) for ns in namespaces])
        query_params = urlencode(url_parts)
        url = f"{self.client.address}/api/schema?{query_params}"

        response = await self.client._get(url=url, timeout=timeout)
        response.raise_for_status()

        try:
            data: MutableMapping[str, Any] = response.json()
        except json.decoder.JSONDecodeError as exc:
            raise JsonDecodeError(
                message=f"Invalid Schema response received from the server at {response.url}: {response.text} [{response.status_code}] ",
                content=response.text,
                url=response.url,
            ) from exc

        nodes: MutableMapping[str, MainSchemaTypesAPI] = {}
        for node_schema in data.get("nodes", []):
            node = NodeSchemaAPI(**node_schema)
            nodes[node.kind] = node

        for generic_schema in data.get("generics", []):
            generic = GenericSchemaAPI(**generic_schema)
            nodes[generic.kind] = generic

        for profile_schema in data.get("profiles", []):
            profile = ProfileSchemaAPI(**profile_schema)
            nodes[profile.kind] = profile

        for template_schema in data.get("templates", []):
            template = TemplateSchemaAPI(**template_schema)
            nodes[template.kind] = template

        schema_hash = data.get("main", "")

        return BranchSchema(hash=schema_hash, nodes=nodes)


class InfrahubSchemaSync(InfrahubSchemaBase):
    def __init__(self, client: InfrahubClientSync):
        self.client = client
        self.cache: dict[str, BranchSchema] = {}

    def all(
        self,
        branch: str | None = None,
        refresh: bool = False,
        namespaces: list[str] | None = None,
        schema_hash: str | None = None,
    ) -> MutableMapping[str, MainSchemaTypesAPI]:
        """Retrieve the entire schema for a given branch.

        if present in cache, the schema will be served from the cache, unless refresh is set to True
        if the schema is not present in the cache, it will be fetched automatically from the server

        Args:
            branch (str, optional): Name of the branch to query. Defaults to default_branch.
            refresh (bool, optional): Force a refresh of the schema. Defaults to False.
            schema_hash (str, optional): Only refresh if the current schema doesn't match this hash.

        Returns:
            dict[str, MainSchemaTypes]: Dictionary of all schema organized by kind
        """
        branch = branch or self.client.default_branch
        if refresh and branch in self.cache and schema_hash and self.cache[branch].hash == schema_hash:
            refresh = False

        if refresh or branch not in self.cache:
            self.cache[branch] = self._fetch(branch=branch, namespaces=namespaces)

        return self.cache[branch].nodes

    def get(
        self,
        kind: type[SchemaType | SchemaTypeSync] | str,
        branch: str | None = None,
        refresh: bool = False,
        timeout: int | None = None,
    ) -> MainSchemaTypesAPI:
        branch = branch or self.client.default_branch

        kind_str = self._get_schema_name(schema=kind)

        if refresh:
            self.cache[branch] = self._fetch(branch=branch)

        if branch in self.cache and kind_str in self.cache[branch].nodes:
            return self.cache[branch].nodes[kind_str]

        # Fetching the latest schema from the server if we didn't fetch it earlier
        #   because we coulnd't find the object on the local cache
        if not refresh:
            self.cache[branch] = self._fetch(branch=branch, timeout=timeout)

        if branch in self.cache and kind_str in self.cache[branch].nodes:
            return self.cache[branch].nodes[kind_str]

        raise SchemaNotFoundError(identifier=kind_str)

    def _get_kind_and_attribute_schema(
        self, kind: str | InfrahubNodeTypes, attribute: str, branch: str | None = None
    ) -> tuple[str, AttributeSchemaAPI]:
        node_kind: str = kind._schema.kind if not isinstance(kind, str) else kind
        node_schema = self.client.schema.get(kind=node_kind, branch=branch)
        schema_attr = node_schema.get_attribute(name=attribute)

        if schema_attr is None:
            raise ValueError(f"Unable to find attribute {attribute}")

        return node_kind, schema_attr

    def _mutate_enum_attribute(
        self,
        mutation: EnumMutation,
        kind: str | InfrahubNodeTypes,
        attribute: str,
        option: str | int,
        branch: str | None = None,
    ) -> None:
        node_kind, schema_attr = self._get_kind_and_attribute_schema(kind=kind, attribute=attribute, branch=branch)

        if schema_attr.enum is None:
            raise ValueError(f"Attribute '{schema_attr.name}' is not of kind Enum")

        input_data = {"data": {"kind": node_kind, "attribute": schema_attr.name, "enum": option}}

        query = Mutation(mutation=mutation.value, input_data=input_data, query={"ok": None})
        self.client.execute_graphql(
            query=query.render(),
            branch_name=branch,
            tracker=f"mutation-{mutation.name}-add",
            timeout=max(60, self.client.default_timeout),
        )

    def add_enum_option(
        self, kind: str | InfrahubNodeTypes, attribute: str, option: str | int, branch: str | None = None
    ) -> None:
        self._mutate_enum_attribute(
            mutation=EnumMutation.add, kind=kind, attribute=attribute, option=option, branch=branch
        )

    def remove_enum_option(
        self, kind: str | InfrahubNodeTypes, attribute: str, option: str | int, branch: str | None = None
    ) -> None:
        self._mutate_enum_attribute(
            mutation=EnumMutation.remove, kind=kind, attribute=attribute, option=option, branch=branch
        )

    def _mutate_dropdown_attribute(
        self,
        mutation: DropdownMutation,
        kind: str | InfrahubNodeTypes,
        attribute: str,
        option: str,
        branch: str | None = None,
        dropdown_optional_args: DropdownMutationOptionalArgs | None = None,
    ) -> None:
        dropdown_optional_args = dropdown_optional_args or DropdownMutationOptionalArgs(
            color="", description="", label=""
        )
        node_kind, schema_attr = self._get_kind_and_attribute_schema(kind=kind, attribute=attribute, branch=branch)

        if schema_attr.kind != "Dropdown":
            raise ValueError(f"Attribute '{schema_attr.name}' is not of kind Dropdown")

        input_data: dict[str, Any] = {
            "data": {
                "kind": node_kind,
                "attribute": schema_attr.name,
                "dropdown": option,
            }
        }

        if mutation == DropdownMutation.add:
            input_data["data"].update(dropdown_optional_args)

        query = Mutation(mutation=mutation.value, input_data=input_data, query={"ok": None})
        self.client.execute_graphql(
            query=query.render(),
            branch_name=branch,
            tracker=f"mutation-{mutation.name}-remove",
            timeout=max(60, self.client.default_timeout),
        )

    def remove_dropdown_option(
        self, kind: str | InfrahubNodeTypes, attribute: str, option: str, branch: str | None = None
    ) -> None:
        self._mutate_dropdown_attribute(
            mutation=DropdownMutation.remove, kind=kind, attribute=attribute, option=option, branch=branch
        )

    def add_dropdown_option(
        self,
        kind: str | InfrahubNodeTypes,
        attribute: str,
        option: str,
        color: str | None = "",
        description: str | None = "",
        label: str | None = "",
        branch: str | None = None,
    ) -> None:
        dropdown_optional_args = DropdownMutationOptionalArgs(color=color, description=description, label=label)
        self._mutate_dropdown_attribute(
            mutation=DropdownMutation.add,
            kind=kind,
            attribute=attribute,
            option=option,
            branch=branch,
            dropdown_optional_args=dropdown_optional_args,
        )

    def fetch(
        self, branch: str, namespaces: list[str] | None = None, timeout: int | None = None
    ) -> MutableMapping[str, MainSchemaTypesAPI]:
        """Fetch the schema from the server for a given branch.

        Args:
            branch (str): Name of the branch to fetch the schema for.
            timeout (int, optional): Overrides default timeout used when querying the GraphQL API. Specified in seconds.

        Returns:
            dict[str, MainSchemaTypes]: Dictionary of all schema organized by kind
        """
        branch_schema = self._fetch(branch=branch, namespaces=namespaces, timeout=timeout)
        return branch_schema.nodes

    def _fetch(self, branch: str, namespaces: list[str] | None = None, timeout: int | None = None) -> BranchSchema:
        url_parts = [("branch", branch)]
        if namespaces:
            url_parts.extend([("namespaces", ns) for ns in namespaces])
        query_params = urlencode(url_parts)
        url = f"{self.client.address}/api/schema?{query_params}"
        response = self.client._get(url=url, timeout=timeout)
        response.raise_for_status()

        data: MutableMapping[str, Any] = response.json()

        nodes: MutableMapping[str, MainSchemaTypesAPI] = {}
        for node_schema in data.get("nodes", []):
            node = NodeSchemaAPI(**node_schema)
            nodes[node.kind] = node

        for generic_schema in data.get("generics", []):
            generic = GenericSchemaAPI(**generic_schema)
            nodes[generic.kind] = generic

        for profile_schema in data.get("profiles", []):
            profile = ProfileSchemaAPI(**profile_schema)
            nodes[profile.kind] = profile

        for template_schema in data.get("templates", []):
            template = TemplateSchemaAPI(**template_schema)
            nodes[template.kind] = template

        schema_hash = data.get("main", "")

        return BranchSchema(hash=schema_hash, nodes=nodes)

    def load(
        self, schemas: list[dict], branch: str | None = None, wait_until_converged: bool = False
    ) -> SchemaLoadResponse:
        branch = branch or self.client.default_branch
        url = f"{self.client.address}/api/schema/load?branch={branch}"
        response = self.client._post(
            url=url, timeout=max(120, self.client.default_timeout), payload={"schemas": schemas}
        )

        if wait_until_converged:
            self.wait_until_converged(branch=branch)

        return self._validate_load_schema_response(response=response)

    def wait_until_converged(self, branch: str | None = None) -> None:
        """Wait until the schema has converged on the selected branch or the timeout has been reached"""
        waited = 0
        while True:
            if self.in_sync(branch=branch):
                self.client.log.info(f"Schema successfully converged after {waited} seconds")
                return

            if waited >= self.client.config.schema_converge_timeout:
                self.client.log.warning(f"Schema not converged after {waited} seconds, proceeding regardless")
                return

            waited += 1
            sleep(1)

    def in_sync(self, branch: str | None = None) -> bool:
        """Indicate if the schema is in sync across all workers for the provided branch"""
        response = self.client.execute_graphql(query=SCHEMA_HASH_SYNC_STATUS, branch_name=branch)
        return response["InfrahubStatus"]["summary"]["schema_hash_synced"]

    def check(self, schemas: list[dict], branch: str | None = None) -> tuple[bool, dict | None]:
        branch = branch or self.client.default_branch
        url = f"{self.client.address}/api/schema/check?branch={branch}"
        response = self.client._post(
            url=url, timeout=max(120, self.client.default_timeout), payload={"schemas": schemas}
        )

        if response.status_code == httpx.codes.ACCEPTED:
            return True, response.json()

        if response.status_code == httpx.codes.UNPROCESSABLE_ENTITY:
            return False, response.json()

        response.raise_for_status()
        return False, None


class SchemaLoadResponse(BaseModel):
    hash: str = Field(default="", description="The new hash for the entire schema")
    previous_hash: str = Field(default="", description="The previous hash for the entire schema")
    errors: dict = Field(default_factory=dict, description="Errors reported by the server")

    @property
    def schema_updated(self) -> bool:
        return bool(self.hash and self.previous_hash and self.hash != self.previous_hash)
