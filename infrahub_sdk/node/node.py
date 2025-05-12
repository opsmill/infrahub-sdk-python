from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, Any

from ..constants import InfrahubClientMode
from ..exceptions import (
    FeatureNotSupportedError,
    NodeNotFoundError,
)
from ..graphql import Mutation, Query
from ..schema import GenericSchemaAPI, RelationshipCardinality, RelationshipKind
from ..utils import compare_lists, generate_short_id, get_flat_value
from .attribute import Attribute
from .constants import (
    ARTIFACT_DEFINITION_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE,
    ARTIFACT_FETCH_FEATURE_NOT_SUPPORTED_MESSAGE,
    ARTIFACT_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE,
    PROPERTIES_OBJECT,
)
from .related_node import RelatedNode, RelatedNodeBase, RelatedNodeSync
from .relationship import RelationshipManager, RelationshipManagerBase, RelationshipManagerSync

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..client import InfrahubClient, InfrahubClientSync
    from ..context import RequestContext
    from ..schema import MainSchemaTypesAPI
    from ..types import Order


def generate_relationship_property(node: InfrahubNode | InfrahubNodeSync, name: str) -> property:
    """Generates a property that stores values under a private non-public name.

    Args:
        node (Union[InfrahubNode, InfrahubNodeSync]): The node instance.
        name (str): The name of the relationship property.

    Returns:
        A property object for managing the relationship.

    """
    internal_name = "_" + name.lower()
    external_name = name

    def prop_getter(self: InfrahubNodeBase) -> Any:
        return getattr(self, internal_name)

    def prop_setter(self: InfrahubNodeBase, value: Any) -> None:
        if isinstance(value, RelatedNodeBase) or value is None:
            setattr(self, internal_name, value)
        else:
            schema = [rel for rel in self._schema.relationships if rel.name == external_name][0]
            if isinstance(node, InfrahubNode):
                setattr(
                    self,
                    internal_name,
                    RelatedNode(
                        name=external_name, branch=node._branch, client=node._client, schema=schema, data=value
                    ),
                )
            else:
                setattr(
                    self,
                    internal_name,
                    RelatedNodeSync(
                        name=external_name, branch=node._branch, client=node._client, schema=schema, data=value
                    ),
                )

    return property(prop_getter, prop_setter)


class InfrahubNodeBase:
    """Base class for InfrahubNode and InfrahubNodeSync"""

    def __init__(self, schema: MainSchemaTypesAPI, branch: str, data: dict | None = None) -> None:
        """
        Args:
            schema: The schema of the node.
            branch: The branch where the node resides.
            data: Optional data to initialize the node.
        """
        self._schema = schema
        self._data = data
        self._branch = branch
        self._existing: bool = True

        # Generate a unique ID only to be used inside the SDK
        # The format if this ID is purposely different from the ID used by the API
        # This is done to avoid confusion and potential conflicts between the IDs
        self._internal_id = generate_short_id()

        self.id = data.get("id", None) if isinstance(data, dict) else None
        self.display_label: str | None = data.get("display_label", None) if isinstance(data, dict) else None
        self.typename: str | None = data.get("__typename", schema.kind) if isinstance(data, dict) else schema.kind

        self._attributes = [item.name for item in self._schema.attributes]
        self._relationships = [item.name for item in self._schema.relationships]

        self._artifact_support = hasattr(schema, "inherit_from") and "CoreArtifactTarget" in schema.inherit_from
        self._artifact_definition_support = schema.kind == "CoreArtifactDefinition"

        if not self.id:
            self._existing = False

        self._init_attributes(data)
        self._init_relationships(data)

    def get_branch(self) -> str:
        return self._branch

    def get_path_value(self, path: str) -> Any:
        path_parts = path.split("__")
        return_value = None

        # Manage relationship value lookup
        if path_parts[0] in self._schema.relationship_names:
            related_node = getattr(self, path_parts[0], None)
            if not related_node:
                return None

            try:
                peer = related_node.get()
            except (NodeNotFoundError, ValueError):
                # This can happen while batch creating nodes, the lookup won't work as the store is not populated
                # If so we cannot complete the HFID computation as we cannot access the related node attribute value
                return None

            if attribute_piece := path_parts[1] if len(path_parts) > 1 else None:
                related_node_attribute = getattr(peer, attribute_piece, None)
            else:
                return peer.hfid or peer.id

            if property_piece := path_parts[2] if len(path_parts) > 2 else None:
                return_value = getattr(related_node_attribute, property_piece, None)
            else:
                return_value = related_node_attribute

        # Manage attribute value lookup
        if path_parts[0] in self._schema.attribute_names:
            attribute = getattr(self, path_parts[0], None)
            if property_piece := path_parts[1] if len(path_parts) > 1 else None:
                return_value = getattr(attribute, property_piece, None)
            else:
                return_value = attribute

        return return_value

    def get_human_friendly_id(self) -> list[str] | None:
        if not hasattr(self._schema, "human_friendly_id"):
            return None

        if not self._schema.human_friendly_id:
            return None

        # If an HFID component is missing we assume that it is invalid and not usable for this node
        hfid_components = [self.get_path_value(path=item) for item in self._schema.human_friendly_id]
        if None in hfid_components:
            return None
        return [str(hfid) for hfid in hfid_components]

    def get_human_friendly_id_as_string(self, include_kind: bool = False) -> str | None:
        hfid = self.get_human_friendly_id()
        if not hfid:
            return None
        if include_kind:
            hfid = [self.get_kind()] + hfid
        return "__".join(hfid)

    @property
    def hfid(self) -> list[str] | None:
        return self.get_human_friendly_id()

    @property
    def hfid_str(self) -> str | None:
        return self.get_human_friendly_id_as_string(include_kind=True)

    def _init_attributes(self, data: dict | None = None) -> None:
        for attr_schema in self._schema.attributes:
            attr_data = data.get(attr_schema.name, None) if isinstance(data, dict) else None
            setattr(
                self,
                attr_schema.name,
                Attribute(name=attr_schema.name, schema=attr_schema, data=attr_data),
            )

    def _get_request_context(self, request_context: RequestContext | None = None) -> dict[str, Any] | None:
        if request_context:
            return request_context.model_dump(exclude_none=True)

        client: InfrahubClient | InfrahubClientSync | None = getattr(self, "_client", None)
        if not client or not client.request_context:
            return None

        return client.request_context.model_dump(exclude_none=True)

    def _init_relationships(self, data: dict | None = None) -> None:
        pass

    def __repr__(self) -> str:
        if self.display_label:
            return self.display_label
        if not self._existing:
            return f"{self._schema.kind} ({self.id})[NEW]"

        return f"{self._schema.kind} ({self.id}) "

    def get_kind(self) -> str:
        return self._schema.kind

    def get_all_kinds(self) -> list[str]:
        if hasattr(self._schema, "inherit_from"):
            return [self._schema.kind] + self._schema.inherit_from
        return [self._schema.kind]

    def is_ip_prefix(self) -> bool:
        builtin_ipprefix_kind = "BuiltinIPPrefix"
        return self.get_kind() == builtin_ipprefix_kind or builtin_ipprefix_kind in self._schema.inherit_from  # type: ignore[union-attr]

    def is_ip_address(self) -> bool:
        builtin_ipaddress_kind = "BuiltinIPAddress"
        return self.get_kind() == builtin_ipaddress_kind or builtin_ipaddress_kind in self._schema.inherit_from  # type: ignore[union-attr]

    def is_resource_pool(self) -> bool:
        return hasattr(self._schema, "inherit_from") and "CoreResourcePool" in self._schema.inherit_from  # type: ignore[union-attr]

    def get_raw_graphql_data(self) -> dict | None:
        return self._data

    def _generate_input_data(  # noqa: C901
        self,
        exclude_unmodified: bool = False,
        exclude_hfid: bool = False,
        request_context: RequestContext | None = None,
    ) -> dict[str, dict]:
        """Generate a dictionary that represent the input data required by a mutation.

        Returns:
            dict[str, Dict]: Representation of an input data in dict format
        """

        data = {}
        variables = {}

        for item_name in self._attributes:
            attr: Attribute = getattr(self, item_name)
            if attr._schema.read_only:
                continue
            attr_data = attr._generate_input_data()

            # NOTE, this code has been inherited when we splitted attributes and relationships
            # into 2 loops, most likely it's possible to simply it
            if attr_data and isinstance(attr_data, dict):
                if variable_values := attr_data.get("data"):
                    data[item_name] = variable_values
                else:
                    data[item_name] = attr_data
                if variable_names := attr_data.get("variables"):
                    variables.update(variable_names)

            elif attr_data and isinstance(attr_data, list):
                data[item_name] = attr_data

        for item_name in self._relationships:
            allocate_from_pool = False
            rel_schema = self._schema.get_relationship(name=item_name)
            if not rel_schema or rel_schema.read_only:
                continue

            rel: RelatedNodeBase | RelationshipManagerBase = getattr(self, item_name)

            # BLOCKED by https://github.com/opsmill/infrahub/issues/330
            # if (
            #     item is None
            #     and item_name in self._relationships
            #     and self._schema.get_relationship(item_name).cardinality == "one"
            # ):
            #     data[item_name] = None
            #     continue
            # el
            if rel is None or not rel.initialized:
                continue

            if isinstance(rel, (RelatedNode, RelatedNodeSync)) and rel.is_resource_pool:
                # If the relatiionship is a resource pool and the expected schema is different from the one of the pool, this means we expect to get
                # a resource from the pool itself
                allocate_from_pool = rel_schema.peer != rel.peer._schema.kind

            rel_data = rel._generate_input_data(allocate_from_pool=allocate_from_pool)

            if rel_data and isinstance(rel_data, dict):
                if variable_values := rel_data.get("data"):
                    data[item_name] = variable_values
                else:
                    data[item_name] = rel_data
                if variable_names := rel_data.get("variables"):
                    variables.update(variable_names)
            elif isinstance(rel_data, list):
                data[item_name] = rel_data
            elif rel_schema.cardinality == RelationshipCardinality.MANY:
                data[item_name] = []

        if exclude_unmodified:
            data, variables = self._strip_unmodified(data=data, variables=variables)

        mutation_variables = {key: type(value) for key, value in variables.items()}

        if self.id is not None:
            data["id"] = self.id
        elif self.hfid is not None and not exclude_hfid:
            data["hfid"] = self.hfid

        mutation_payload = {"data": data}
        if context_data := self._get_request_context(request_context=request_context):
            mutation_payload["context"] = context_data

        return {
            "data": mutation_payload,
            "variables": variables,
            "mutation_variables": mutation_variables,
        }

    @staticmethod
    def _strip_unmodified_dict(data: dict, original_data: dict, variables: dict, item: str) -> None:
        data_item = data.get(item)
        if item in original_data and isinstance(original_data[item], dict) and isinstance(data_item, dict):
            for item_key in original_data[item].keys():
                for property_name in PROPERTIES_OBJECT:
                    if item_key == property_name and isinstance(original_data[item][property_name], dict):
                        if original_data[item][property_name].get("id"):
                            original_data[item][property_name] = original_data[item][property_name]["id"]
                if item_key in data[item].keys():
                    if item_key == "id" and len(data[item].keys()) > 1:
                        # Related nodes typically require an ID. So the ID is only
                        # removed if it's the last key in the current context
                        continue

                    variable_key = None
                    if isinstance(data[item].get(item_key), str):
                        variable_key = data[item][item_key][1:]

                    if original_data[item].get(item_key) == data[item].get(item_key):
                        data[item].pop(item_key)
                    elif (
                        variable_key
                        and variable_key in variables
                        and original_data[item].get(item_key) == variables.get(variable_key)
                    ):
                        data[item].pop(item_key)
                        variables.pop(variable_key)

        # TODO: I do not feel _great_ about this
        if not data_item and data_item != [] and item in data:
            data.pop(item)

    def _strip_unmodified(self, data: dict, variables: dict) -> tuple[dict, dict]:
        original_data = self._data or {}
        for relationship in self._relationships:
            relationship_property = getattr(self, relationship)
            if not relationship_property or relationship not in data:
                continue
            if not relationship_property.initialized:
                data.pop(relationship)
            elif isinstance(relationship_property, RelationshipManagerBase) and not relationship_property.has_update:
                data.pop(relationship)

        for item in original_data.keys():
            if item in data.keys():
                if data[item] == original_data[item]:
                    if attr := getattr(self, item, None):  # this should never be None, just a safety default value
                        if not isinstance(attr, Attribute) or not attr.value_has_been_mutated:
                            data.pop(item)
                    continue
                if isinstance(original_data[item], dict):
                    self._strip_unmodified_dict(data=data, original_data=original_data, variables=variables, item=item)
                    if item in self._relationships and original_data[item].get("node"):
                        relationship_data_cardinality_one = copy(original_data)
                        relationship_data_cardinality_one[item] = original_data[item]["node"]
                        self._strip_unmodified_dict(
                            data=data, original_data=relationship_data_cardinality_one, variables=variables, item=item
                        )
                        # Run again to remove the "id" key if it's the last one remaining
                        self._strip_unmodified_dict(
                            data=data, original_data=relationship_data_cardinality_one, variables=variables, item=item
                        )

        return data, variables

    @staticmethod
    def _strip_alias(data: dict) -> dict[str, dict]:
        clean = {}

        under_node = False
        data_to_clean = data
        if "node" in data:
            under_node = True
            data_to_clean = data["node"]

        for key, value in data_to_clean.items():
            if "__alias__" in key:
                clean_key = key.split("__")[-1]
                clean[clean_key] = value
            else:
                clean[key] = value

        if under_node:
            complete = {k: v for k, v in data.items() if k != "node"}
            complete["node"] = clean
            return complete
        return clean

    def _validate_artifact_support(self, message: str) -> None:
        if not self._artifact_support:
            raise FeatureNotSupportedError(message)

    def _validate_artifact_definition_support(self, message: str) -> None:
        if not self._artifact_definition_support:
            raise FeatureNotSupportedError(message)

    def generate_query_data_init(
        self,
        filters: dict[str, Any] | None = None,
        offset: int | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        partial_match: bool = False,
        order: Order | None = None,
    ) -> dict[str, Any | dict]:
        data: dict[str, Any] = {
            "count": None,
            "edges": {"node": {"id": None, "hfid": None, "display_label": None, "__typename": None}},
        }

        data["@filters"] = filters or {}

        if order:
            data["@filters"]["order"] = order

        if offset:
            data["@filters"]["offset"] = offset

        if limit:
            data["@filters"]["limit"] = limit

        if include and exclude:
            in_both, _, _ = compare_lists(include, exclude)
            if in_both:
                raise ValueError(f"{in_both} are part of both include and exclude")

        if partial_match:
            data["@filters"]["partial_match"] = True

        return data

    def extract(self, params: dict[str, str]) -> dict[str, Any]:
        """Extract some datapoints defined in a flat notation."""
        result: dict[str, Any] = {}
        for key, value in params.items():
            result[key] = get_flat_value(self, key=value)

        return result

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (InfrahubNode, InfrahubNodeSync)):
            return NotImplemented
        return self.id == other.id

    def _relationship_mutation(self, action: str, relation_to_update: str, related_nodes: list[str]) -> str:
        related_node_str = ["{ id: " + f'"{node}"' + " }" for node in related_nodes]
        return f"""
        mutation {{
            Relationship{action}(
                data: {{
                    id: "{self.id}",
                    name: "{relation_to_update}",
                    nodes: [{", ".join(related_node_str)}]
                }}
            ) {{
                ok
            }}
        }}
        """


class InfrahubNode(InfrahubNodeBase):
    """Represents a Infrahub node in an asynchronous context."""

    def __init__(
        self,
        client: InfrahubClient,
        schema: MainSchemaTypesAPI,
        branch: str | None = None,
        data: dict | None = None,
    ) -> None:
        """
        Args:
            client: The client used to interact with the backend.
            schema: The schema of the node.
            branch: The branch where the node resides.
            data: Optional data to initialize the node.
        """
        self._client = client
        self.__class__ = type(f"{schema.kind}InfrahubNode", (self.__class__,), {})

        if isinstance(data, dict) and isinstance(data.get("node"), dict):
            data = data.get("node")

        super().__init__(schema=schema, branch=branch or client.default_branch, data=data)

    @classmethod
    async def from_graphql(
        cls,
        client: InfrahubClient,
        branch: str,
        data: dict,
        schema: MainSchemaTypesAPI | None = None,
        timeout: int | None = None,
    ) -> Self:
        if not schema:
            node_kind = data.get("__typename") or data.get("node", {}).get("__typename", None)
            if not node_kind:
                raise ValueError("Unable to determine the type of the node, __typename not present in data")
            schema = await client.schema.get(kind=node_kind, branch=branch, timeout=timeout)

        return cls(client=client, schema=schema, branch=branch, data=cls._strip_alias(data))

    def _init_relationships(self, data: dict | None = None) -> None:
        for rel_schema in self._schema.relationships:
            rel_data = data.get(rel_schema.name, None) if isinstance(data, dict) else None

            if rel_schema.cardinality == "one":
                setattr(self, f"_{rel_schema.name}", None)
                setattr(
                    self.__class__,
                    rel_schema.name,
                    generate_relationship_property(name=rel_schema.name, node=self),
                )
                setattr(self, rel_schema.name, rel_data)
            else:
                setattr(
                    self,
                    rel_schema.name,
                    RelationshipManager(
                        name=rel_schema.name,
                        client=self._client,
                        node=self,
                        branch=self._branch,
                        schema=rel_schema,
                        data=rel_data,
                    ),
                )

    async def generate(self, nodes: list[str] | None = None) -> None:
        self._validate_artifact_definition_support(ARTIFACT_DEFINITION_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE)

        nodes = nodes or []
        payload = {"nodes": nodes}
        resp = await self._client._post(f"{self._client.address}/api/artifact/generate/{self.id}", payload=payload)
        resp.raise_for_status()

    async def artifact_generate(self, name: str) -> None:
        self._validate_artifact_support(ARTIFACT_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE)

        artifact = await self._client.get(kind="CoreArtifact", name__value=name, object__ids=[self.id])
        await artifact.definition.fetch()  # type: ignore[attr-defined]
        await artifact.definition.peer.generate([artifact.id])  # type: ignore[attr-defined]

    async def artifact_fetch(self, name: str) -> str | dict[str, Any]:
        self._validate_artifact_support(ARTIFACT_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE)

        artifact = await self._client.get(kind="CoreArtifact", name__value=name, object__ids=[self.id])
        content = await self._client.object_store.get(identifier=artifact.storage_id.value)  # type: ignore[attr-defined]
        return content

    async def delete(self, timeout: int | None = None, request_context: RequestContext | None = None) -> None:
        input_data = {"data": {"id": self.id}}
        if context_data := self._get_request_context(request_context=request_context):
            input_data["context"] = context_data

        mutation_query = {"ok": None}
        query = Mutation(
            mutation=f"{self._schema.kind}Delete",
            input_data=input_data,
            query=mutation_query,
        )
        await self._client.execute_graphql(
            query=query.render(),
            branch_name=self._branch,
            timeout=timeout,
            tracker=f"mutation-{str(self._schema.kind).lower()}-delete",
        )

    async def save(
        self,
        allow_upsert: bool = False,
        update_group_context: bool | None = None,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
    ) -> None:
        if self._existing is False or allow_upsert is True:
            await self.create(allow_upsert=allow_upsert, timeout=timeout, request_context=request_context)
        else:
            await self.update(timeout=timeout, request_context=request_context)

        if update_group_context is None and self._client.mode == InfrahubClientMode.TRACKING:
            update_group_context = True

        if not isinstance(self._schema, GenericSchemaAPI):
            if "CoreGroup" in self._schema.inherit_from:
                await self._client.group_context.add_related_groups(
                    ids=[self.id], update_group_context=update_group_context
                )
            else:
                await self._client.group_context.add_related_nodes(
                    ids=[self.id], update_group_context=update_group_context
                )
        else:
            await self._client.group_context.add_related_nodes(ids=[self.id], update_group_context=update_group_context)

        self._client.store.set(node=self)

    async def generate_query_data(
        self,
        filters: dict[str, Any] | None = None,
        offset: int | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        partial_match: bool = False,
        property: bool = False,
        order: Order | None = None,
    ) -> dict[str, Any | dict]:
        data = self.generate_query_data_init(
            filters=filters,
            offset=offset,
            limit=limit,
            include=include,
            exclude=exclude,
            partial_match=partial_match,
            order=order,
        )
        data["edges"]["node"].update(
            await self.generate_query_data_node(
                include=include,
                exclude=exclude,
                prefetch_relationships=prefetch_relationships,
                inherited=True,
                property=property,
            )
        )

        if isinstance(self._schema, GenericSchemaAPI) and fragment:
            for child in self._schema.used_by:
                child_schema = await self._client.schema.get(kind=child)
                child_node = InfrahubNode(client=self._client, schema=child_schema)

                # Add the attribute and the relationship already part of the parent to the exclude list for the children
                exclude_parent = self._attributes + self._relationships
                _, _, only_in_list2 = compare_lists(list1=include or [], list2=exclude_parent)

                exclude_child = only_in_list2
                if exclude:
                    exclude_child += exclude

                child_data = await child_node.generate_query_data_node(
                    include=include,
                    exclude=exclude_child,
                    prefetch_relationships=prefetch_relationships,
                    inherited=False,
                    insert_alias=True,
                    property=property,
                )

                if child_data:
                    data["edges"]["node"][f"...on {child}"] = child_data

        return {self._schema.kind: data}

    async def generate_query_data_node(
        self,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        inherited: bool = True,
        insert_alias: bool = False,
        prefetch_relationships: bool = False,
        property: bool = False,
    ) -> dict[str, Any | dict]:
        """Generate the node part of a GraphQL Query with attributes and nodes.

        Args:
            include (Optional[list[str]], optional): List of attributes or relationships to include. Defaults to None.
            exclude (Optional[list[str]], optional): List of attributes or relationships to exclude. Defaults to None.
            inherited (bool, optional): Indicated of the attributes and the relationships inherited from generics should be included as well.
                                        Defaults to True.
            insert_alias (bool, optional): If True, inserts aliases in the query for each attribute or relationship.
            prefetch_relationships (bool, optional): If True, pre-fetches relationship data as part of the query.

        Returns:
            dict[str, Union[Any, Dict]]: GraphQL query in dictionary format
        """

        data: dict[str, Any] = {}

        for attr_name in self._attributes:
            if exclude and attr_name in exclude:
                continue

            attr: Attribute = getattr(self, attr_name)

            if not inherited and attr._schema.inherited:
                continue

            attr_data = attr._generate_query_data(property=property)
            if attr_data:
                data[attr_name] = attr_data
                if insert_alias:
                    data[attr_name]["@alias"] = f"__alias__{self._schema.kind}__{attr_name}"
            elif insert_alias:
                if insert_alias:
                    data[attr_name] = {"@alias": f"__alias__{self._schema.kind}__{attr_name}"}

        for rel_name in self._relationships:
            if exclude and rel_name in exclude:
                continue

            rel_schema = self._schema.get_relationship(name=rel_name)

            if not rel_schema or (not inherited and rel_schema.inherited):
                continue

            if (
                rel_schema.cardinality == RelationshipCardinality.MANY  # type: ignore[union-attr]
                and rel_schema.kind not in [RelationshipKind.ATTRIBUTE, RelationshipKind.PARENT]  # type: ignore[union-attr]
                and not (include and rel_name in include)
            ):
                continue

            peer_data: dict[str, Any] = {}
            if rel_schema and prefetch_relationships:
                peer_schema = await self._client.schema.get(kind=rel_schema.peer, branch=self._branch)
                peer_node = InfrahubNode(client=self._client, schema=peer_schema, branch=self._branch)
                peer_data = await peer_node.generate_query_data_node(
                    include=include,
                    exclude=exclude,
                    property=property,
                )

            if rel_schema and rel_schema.cardinality == "one":
                rel_data = RelatedNode._generate_query_data(peer_data=peer_data, property=property)
                # Nodes involved in a hierarchy are required to inherit from a common ancestor node, and graphql
                # tries to resolve attributes in this ancestor instead of actual node. To avoid
                # invalid queries issues when attribute is missing in the common ancestor, we use a fragment
                # to explicit actual node kind we are querying.
                if rel_schema.kind == RelationshipKind.HIERARCHY:
                    data_node = rel_data["node"]
                    rel_data["node"] = {}
                    rel_data["node"][f"...on {rel_schema.peer}"] = data_node
            elif rel_schema and rel_schema.cardinality == "many":
                rel_data = RelationshipManager._generate_query_data(peer_data=peer_data, property=property)

            data[rel_name] = rel_data

            if insert_alias:
                data[rel_name]["@alias"] = f"__alias__{self._schema.kind}__{rel_name}"

        return data

    async def add_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None:
        query = self._relationship_mutation(
            action="Add", relation_to_update=relation_to_update, related_nodes=related_nodes
        )
        tracker = f"mutation-{str(self._schema.kind).lower()}-relationshipadd-{relation_to_update}"
        await self._client.execute_graphql(query=query, branch_name=self._branch, tracker=tracker)

    async def remove_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None:
        query = self._relationship_mutation(
            action="Remove", relation_to_update=relation_to_update, related_nodes=related_nodes
        )
        tracker = f"mutation-{str(self._schema.kind).lower()}-relationshipremove-{relation_to_update}"
        await self._client.execute_graphql(query=query, branch_name=self._branch, tracker=tracker)

    def _generate_mutation_query(self) -> dict[str, Any]:
        query_result: dict[str, Any] = {"ok": None, "object": {"id": None}}

        for attr_name in self._attributes:
            attr: Attribute = getattr(self, attr_name)
            query_result["object"].update(attr._generate_mutation_query())

        for rel_name in self._relationships:
            rel = getattr(self, rel_name)
            if not isinstance(rel, RelatedNode):
                continue

            query_result["object"].update(rel._generate_mutation_query())

        return query_result

    async def _process_mutation_result(
        self, mutation_name: str, response: dict[str, Any], timeout: int | None = None
    ) -> None:
        object_response: dict[str, Any] = response[mutation_name]["object"]
        self.id = object_response["id"]
        self._existing = True

        for attr_name in self._attributes:
            attr = getattr(self, attr_name)
            if (
                attr_name not in object_response
                or not isinstance(attr.value, InfrahubNodeBase)
                or not attr.value.is_resource_pool()
            ):
                continue

            # Process allocated resource from a pool and update attribute
            attr.value = object_response[attr_name]["value"]

        for rel_name in self._relationships:
            rel = getattr(self, rel_name)
            if rel_name not in object_response or not isinstance(rel, RelatedNode) or not rel.is_resource_pool:
                continue

            # Process allocated resource from a pool and update related node
            allocated_resource = object_response[rel_name]
            related_node = RelatedNode(
                client=self._client, branch=self._branch, schema=rel.schema, data=allocated_resource
            )
            await related_node.fetch(timeout=timeout)
            setattr(self, rel_name, related_node)

    async def create(
        self, allow_upsert: bool = False, timeout: int | None = None, request_context: RequestContext | None = None
    ) -> None:
        mutation_query = self._generate_mutation_query()

        # Upserting means we may want to create, meaning payload contains all mandatory fields required for a creation,
        # so hfid is just redondant information. Currently, upsert mutation has performance overhead if `hfid` is filled.
        if allow_upsert:
            input_data = self._generate_input_data(exclude_hfid=True, request_context=request_context)
            mutation_name = f"{self._schema.kind}Upsert"
            tracker = f"mutation-{str(self._schema.kind).lower()}-upsert"
        else:
            input_data = self._generate_input_data(exclude_hfid=True, request_context=request_context)
            mutation_name = f"{self._schema.kind}Create"
            tracker = f"mutation-{str(self._schema.kind).lower()}-create"
        query = Mutation(
            mutation=mutation_name,
            input_data=input_data["data"],
            query=mutation_query,
            variables=input_data["mutation_variables"],
        )
        response = await self._client.execute_graphql(
            query=query.render(),
            branch_name=self._branch,
            tracker=tracker,
            variables=input_data["variables"],
            timeout=timeout,
        )
        await self._process_mutation_result(mutation_name=mutation_name, response=response, timeout=timeout)

    async def update(
        self, do_full_update: bool = False, timeout: int | None = None, request_context: RequestContext | None = None
    ) -> None:
        input_data = self._generate_input_data(exclude_unmodified=not do_full_update, request_context=request_context)
        mutation_query = self._generate_mutation_query()
        mutation_name = f"{self._schema.kind}Update"

        query = Mutation(
            mutation=mutation_name,
            input_data=input_data["data"],
            query=mutation_query,
            variables=input_data["mutation_variables"],
        )
        response = await self._client.execute_graphql(
            query=query.render(),
            branch_name=self._branch,
            timeout=timeout,
            tracker=f"mutation-{str(self._schema.kind).lower()}-update",
            variables=input_data["variables"],
        )
        await self._process_mutation_result(mutation_name=mutation_name, response=response, timeout=timeout)

    async def _process_relationships(
        self, node_data: dict[str, Any], branch: str, related_nodes: list[InfrahubNode], timeout: int | None = None
    ) -> None:
        """Processes the Relationships of a InfrahubNode and add Related Nodes to a list.

        Args:
            node_data (dict[str, Any]): The item from the GraphQL response corresponding to the node.
            branch (str): The branch name.
            related_nodes (list[InfrahubNode]): The list to which related nodes will be appended.
            timeout (int, optional): Overrides default timeout used when querying the graphql API. Specified in seconds.
        """
        for rel_name in self._relationships:
            rel = getattr(self, rel_name)
            if rel and isinstance(rel, RelatedNode):
                relation = node_data["node"].get(rel_name, None)
                if relation and relation.get("node", None):
                    related_node = await InfrahubNode.from_graphql(
                        client=self._client, branch=branch, data=relation, timeout=timeout
                    )
                    related_nodes.append(related_node)
            elif rel and isinstance(rel, RelationshipManager):
                peers = node_data["node"].get(rel_name, None)
                if peers and peers["edges"]:
                    for peer in peers["edges"]:
                        related_node = await InfrahubNode.from_graphql(
                            client=self._client, branch=branch, data=peer, timeout=timeout
                        )
                        related_nodes.append(related_node)

    async def get_pool_allocated_resources(self, resource: InfrahubNode) -> list[InfrahubNode]:
        """Fetch all nodes that were allocated for the pool and a given resource.

        Args:
            resource (InfrahubNode): The resource from which the nodes were allocated.

        Returns:
            list[InfrahubNode]: The allocated nodes.
        """
        if not self.is_resource_pool():
            raise ValueError("Allocated resources can only be fetched from resource pool nodes.")

        graphql_query_name = "InfrahubResourcePoolAllocated"
        node_ids_per_kind: dict[str, list[str]] = {}

        has_remaining_items = True
        page_number = 1
        while has_remaining_items:
            page_offset = (page_number - 1) * self._client.pagination_size

            query = Query(
                query={
                    graphql_query_name: {
                        "@filters": {
                            "pool_id": "$pool_id",
                            "resource_id": "$resource_id",
                            "offset": page_offset,
                            "limit": self._client.pagination_size,
                        },
                        "count": None,
                        "edges": {"node": {"id": None, "kind": None, "branch": None, "identifier": None}},
                    }
                },
                name="GetAllocatedResourceForPool",
                variables={"pool_id": str, "resource_id": str},
            )
            response = await self._client.execute_graphql(
                query=query.render(),
                variables={"pool_id": self.id, "resource_id": resource.id},
                branch_name=self._branch,
                tracker=f"get-allocated-resources-page{page_number}",
            )

            for edge in response[graphql_query_name]["edges"]:
                node = edge["node"]
                node_ids_per_kind.setdefault(node["kind"], []).append(node["id"])

            remaining_items = response[graphql_query_name].get("count", 0) - (
                page_offset + self._client.pagination_size
            )
            if remaining_items <= 0:
                has_remaining_items = False

            page_number += 1

        nodes: list[InfrahubNode] = []
        for kind, node_ids in node_ids_per_kind.items():
            nodes.extend(await self._client.filters(kind=kind, branch=self._branch, ids=node_ids))

        return nodes

    async def get_pool_resources_utilization(self) -> list[dict[str, Any]]:
        """Fetch the utilization of each resource for the pool.

        Returns:
            list[dict[str, Any]]: A list containing the allocation numbers for each resource of the pool.
        """
        if not self.is_resource_pool():
            raise ValueError("Pool utilization can only be fetched for resource pool nodes.")

        graphql_query_name = "InfrahubResourcePoolUtilization"

        query = Query(
            query={
                graphql_query_name: {
                    "@filters": {"pool_id": "$pool_id"},
                    "count": None,
                    "edges": {
                        "node": {
                            "id": None,
                            "kind": None,
                            "utilization": None,
                            "utilization_branches": None,
                            "utilization_default_branch": None,
                        }
                    },
                }
            },
            name="GetUtilizationForPool",
            variables={"pool_id": str},
        )
        response = await self._client.execute_graphql(
            query=query.render(),
            variables={"pool_id": self.id},
            branch_name=self._branch,
            tracker="get-pool-utilization",
        )

        if response[graphql_query_name].get("count", 0):
            return [edge["node"] for edge in response[graphql_query_name]["edges"]]
        return []


class InfrahubNodeSync(InfrahubNodeBase):
    """Represents a Infrahub node in a synchronous context."""

    def __init__(
        self,
        client: InfrahubClientSync,
        schema: MainSchemaTypesAPI,
        branch: str | None = None,
        data: dict | None = None,
    ) -> None:
        """
        Args:
            client (InfrahubClientSync): The client used to interact with the backend synchronously.
            schema (MainSchemaTypes): The schema of the node.
            branch (Optional[str]): The branch where the node resides.
            data (Optional[dict]): Optional data to initialize the node.
        """
        self.__class__ = type(f"{schema.kind}InfrahubNodeSync", (self.__class__,), {})
        self._client = client

        if isinstance(data, dict) and isinstance(data.get("node"), dict):
            data = data.get("node")

        super().__init__(schema=schema, branch=branch or client.default_branch, data=data)

    @classmethod
    def from_graphql(
        cls,
        client: InfrahubClientSync,
        branch: str,
        data: dict,
        schema: MainSchemaTypesAPI | None = None,
        timeout: int | None = None,
    ) -> Self:
        if not schema:
            node_kind = data.get("__typename") or data.get("node", {}).get("__typename", None)
            if not node_kind:
                raise ValueError("Unable to determine the type of the node, __typename not present in data")
            schema = client.schema.get(kind=node_kind, branch=branch, timeout=timeout)

        return cls(client=client, schema=schema, branch=branch, data=cls._strip_alias(data))

    def _init_relationships(self, data: dict | None = None) -> None:
        for rel_schema in self._schema.relationships:
            rel_data = data.get(rel_schema.name, None) if isinstance(data, dict) else None

            if rel_schema.cardinality == "one":
                setattr(self, f"_{rel_schema.name}", None)
                setattr(
                    self.__class__,
                    rel_schema.name,
                    generate_relationship_property(name=rel_schema.name, node=self),
                )
                setattr(self, rel_schema.name, rel_data)
            else:
                setattr(
                    self,
                    rel_schema.name,
                    RelationshipManagerSync(
                        name=rel_schema.name,
                        client=self._client,
                        node=self,
                        branch=self._branch,
                        schema=rel_schema,
                        data=rel_data,
                    ),
                )

    def generate(self, nodes: list[str] | None = None) -> None:
        self._validate_artifact_definition_support(ARTIFACT_DEFINITION_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE)
        nodes = nodes or []
        payload = {"nodes": nodes}
        resp = self._client._post(f"{self._client.address}/api/artifact/generate/{self.id}", payload=payload)
        resp.raise_for_status()

    def artifact_generate(self, name: str) -> None:
        self._validate_artifact_support(ARTIFACT_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE)
        artifact = self._client.get(kind="CoreArtifact", name__value=name, object__ids=[self.id])
        artifact.definition.fetch()  # type: ignore[attr-defined]
        artifact.definition.peer.generate([artifact.id])  # type: ignore[attr-defined]

    def artifact_fetch(self, name: str) -> str | dict[str, Any]:
        self._validate_artifact_support(ARTIFACT_FETCH_FEATURE_NOT_SUPPORTED_MESSAGE)
        artifact = self._client.get(kind="CoreArtifact", name__value=name, object__ids=[self.id])
        content = self._client.object_store.get(identifier=artifact.storage_id.value)  # type: ignore[attr-defined]
        return content

    def delete(self, timeout: int | None = None, request_context: RequestContext | None = None) -> None:
        input_data = {"data": {"id": self.id}}
        if context_data := self._get_request_context(request_context=request_context):
            input_data["context"] = context_data

        mutation_query = {"ok": None}
        query = Mutation(
            mutation=f"{self._schema.kind}Delete",
            input_data=input_data,
            query=mutation_query,
        )
        self._client.execute_graphql(
            query=query.render(),
            branch_name=self._branch,
            tracker=f"mutation-{str(self._schema.kind).lower()}-delete",
            timeout=timeout,
        )

    def save(
        self,
        allow_upsert: bool = False,
        update_group_context: bool | None = None,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
    ) -> None:
        if self._existing is False or allow_upsert is True:
            self.create(allow_upsert=allow_upsert, timeout=timeout, request_context=request_context)
        else:
            self.update(timeout=timeout, request_context=request_context)

        if update_group_context is None and self._client.mode == InfrahubClientMode.TRACKING:
            update_group_context = True

        if not isinstance(self._schema, GenericSchemaAPI):
            if "CoreGroup" in self._schema.inherit_from:
                self._client.group_context.add_related_groups(ids=[self.id], update_group_context=update_group_context)
            else:
                self._client.group_context.add_related_nodes(ids=[self.id], update_group_context=update_group_context)
        else:
            self._client.group_context.add_related_nodes(ids=[self.id], update_group_context=update_group_context)

        self._client.store.set(node=self)

    def generate_query_data(
        self,
        filters: dict[str, Any] | None = None,
        offset: int | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        partial_match: bool = False,
        property: bool = False,
        order: Order | None = None,
    ) -> dict[str, Any | dict]:
        data = self.generate_query_data_init(
            filters=filters,
            offset=offset,
            limit=limit,
            include=include,
            exclude=exclude,
            partial_match=partial_match,
            order=order,
        )
        data["edges"]["node"].update(
            self.generate_query_data_node(
                include=include,
                exclude=exclude,
                prefetch_relationships=prefetch_relationships,
                inherited=True,
                property=property,
            )
        )

        if isinstance(self._schema, GenericSchemaAPI) and fragment:
            for child in self._schema.used_by:
                child_schema = self._client.schema.get(kind=child)
                child_node = InfrahubNodeSync(client=self._client, schema=child_schema)

                exclude_parent = self._attributes + self._relationships
                _, _, only_in_list2 = compare_lists(list1=include or [], list2=exclude_parent)

                exclude_child = only_in_list2
                if exclude:
                    exclude_child += exclude

                child_data = child_node.generate_query_data_node(
                    include=include,
                    exclude=exclude_child,
                    prefetch_relationships=prefetch_relationships,
                    inherited=False,
                    insert_alias=True,
                    property=property,
                )

                if child_data:
                    data["edges"]["node"][f"...on {child}"] = child_data

        return {self._schema.kind: data}

    def generate_query_data_node(
        self,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        inherited: bool = True,
        insert_alias: bool = False,
        prefetch_relationships: bool = False,
        property: bool = False,
    ) -> dict[str, Any | dict]:
        """Generate the node part of a GraphQL Query with attributes and nodes.

        Args:
            include (Optional[list[str]], optional): List of attributes or relationships to include. Defaults to None.
            exclude (Optional[list[str]], optional): List of attributes or relationships to exclude. Defaults to None.
            inherited (bool, optional): Indicated of the attributes and the relationships inherited from generics should be included as well.
                                        Defaults to True.
            insert_alias (bool, optional): If True, inserts aliases in the query for each attribute or relationship.
            prefetch_relationships (bool, optional): If True, pre-fetches relationship data as part of the query.

        Returns:
            dict[str, Union[Any, Dict]]: GraphQL query in dictionary format
        """

        data: dict[str, Any] = {}

        for attr_name in self._attributes:
            if exclude and attr_name in exclude:
                continue

            attr: Attribute = getattr(self, attr_name)

            if not inherited and attr._schema.inherited:
                continue

            attr_data = attr._generate_query_data(property=property)
            if attr_data:
                data[attr_name] = attr_data
                if insert_alias:
                    data[attr_name]["@alias"] = f"__alias__{self._schema.kind}__{attr_name}"
            elif insert_alias:
                if insert_alias:
                    data[attr_name] = {"@alias": f"__alias__{self._schema.kind}__{attr_name}"}

        for rel_name in self._relationships:
            if exclude and rel_name in exclude:
                continue

            rel_schema = self._schema.get_relationship(name=rel_name)

            if not rel_schema or (not inherited and rel_schema.inherited):
                continue

            if (
                rel_schema.cardinality == RelationshipCardinality.MANY  # type: ignore[union-attr]
                and rel_schema.kind not in [RelationshipKind.ATTRIBUTE, RelationshipKind.PARENT]  # type: ignore[union-attr]
                and not (include and rel_name in include)
            ):
                continue

            peer_data: dict[str, Any] = {}
            if rel_schema and prefetch_relationships:
                peer_schema = self._client.schema.get(kind=rel_schema.peer, branch=self._branch)
                peer_node = InfrahubNodeSync(client=self._client, schema=peer_schema, branch=self._branch)
                peer_data = peer_node.generate_query_data_node(include=include, exclude=exclude, property=property)

            if rel_schema and rel_schema.cardinality == "one":
                rel_data = RelatedNodeSync._generate_query_data(peer_data=peer_data, property=property)
                # Nodes involved in a hierarchy are required to inherit from a common ancestor node, and graphql
                # tries to resolve attributes in this ancestor instead of actual node. To avoid
                # invalid queries issues when attribute is missing in the common ancestor, we use a fragment
                # to explicit actual node kind we are querying.
                if rel_schema.kind == RelationshipKind.HIERARCHY:
                    data_node = rel_data["node"]
                    rel_data["node"] = {}
                    rel_data["node"][f"...on {rel_schema.peer}"] = data_node
            elif rel_schema and rel_schema.cardinality == "many":
                rel_data = RelationshipManagerSync._generate_query_data(peer_data=peer_data, property=property)

            data[rel_name] = rel_data

            if insert_alias:
                data[rel_name]["@alias"] = f"__alias__{self._schema.kind}__{rel_name}"

        return data

    def add_relationships(
        self,
        relation_to_update: str,
        related_nodes: list[str],
    ) -> None:
        query = self._relationship_mutation(
            action="Add", relation_to_update=relation_to_update, related_nodes=related_nodes
        )
        tracker = f"mutation-{str(self._schema.kind).lower()}-relationshipadd-{relation_to_update}"
        self._client.execute_graphql(query=query, branch_name=self._branch, tracker=tracker)

    def remove_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None:
        query = self._relationship_mutation(
            action="Remove", relation_to_update=relation_to_update, related_nodes=related_nodes
        )
        tracker = f"mutation-{str(self._schema.kind).lower()}-relationshipremove-{relation_to_update}"
        self._client.execute_graphql(query=query, branch_name=self._branch, tracker=tracker)

    def _generate_mutation_query(self) -> dict[str, Any]:
        query_result: dict[str, Any] = {"ok": None, "object": {"id": None}}

        for attr_name in self._attributes:
            attr: Attribute = getattr(self, attr_name)
            query_result["object"].update(attr._generate_mutation_query())

        for rel_name in self._relationships:
            rel = getattr(self, rel_name)
            if not isinstance(rel, RelatedNodeSync):
                continue

            query_result["object"].update(rel._generate_mutation_query())

        return query_result

    def _process_mutation_result(
        self, mutation_name: str, response: dict[str, Any], timeout: int | None = None
    ) -> None:
        object_response: dict[str, Any] = response[mutation_name]["object"]
        self.id = object_response["id"]
        self._existing = True

        for attr_name in self._attributes:
            attr = getattr(self, attr_name)
            if (
                attr_name not in object_response
                or not isinstance(attr.value, InfrahubNodeBase)
                or not attr.value.is_resource_pool()
            ):
                continue

            # Process allocated resource from a pool and update attribute
            attr.value = object_response[attr_name]["value"]

        for rel_name in self._relationships:
            rel = getattr(self, rel_name)
            if rel_name not in object_response or not isinstance(rel, RelatedNodeSync) or not rel.is_resource_pool:
                continue

            # Process allocated resource from a pool and update related node
            allocated_resource = object_response[rel_name]
            related_node = RelatedNodeSync(
                client=self._client, branch=self._branch, schema=rel.schema, data=allocated_resource
            )
            related_node.fetch(timeout=timeout)
            setattr(self, rel_name, related_node)

    def create(
        self, allow_upsert: bool = False, timeout: int | None = None, request_context: RequestContext | None = None
    ) -> None:
        mutation_query = self._generate_mutation_query()

        if allow_upsert:
            input_data = self._generate_input_data(exclude_hfid=False, request_context=request_context)
            mutation_name = f"{self._schema.kind}Upsert"
            tracker = f"mutation-{str(self._schema.kind).lower()}-upsert"
        else:
            input_data = self._generate_input_data(exclude_hfid=True, request_context=request_context)
            mutation_name = f"{self._schema.kind}Create"
            tracker = f"mutation-{str(self._schema.kind).lower()}-create"
        query = Mutation(
            mutation=mutation_name,
            input_data=input_data["data"],
            query=mutation_query,
            variables=input_data["mutation_variables"],
        )

        response = self._client.execute_graphql(
            query=query.render(),
            branch_name=self._branch,
            tracker=tracker,
            variables=input_data["variables"],
            timeout=timeout,
        )
        self._process_mutation_result(mutation_name=mutation_name, response=response, timeout=timeout)

    def update(
        self, do_full_update: bool = False, timeout: int | None = None, request_context: RequestContext | None = None
    ) -> None:
        input_data = self._generate_input_data(exclude_unmodified=not do_full_update, request_context=request_context)
        mutation_query = self._generate_mutation_query()
        mutation_name = f"{self._schema.kind}Update"

        query = Mutation(
            mutation=mutation_name,
            input_data=input_data["data"],
            query=mutation_query,
            variables=input_data["mutation_variables"],
        )

        response = self._client.execute_graphql(
            query=query.render(),
            branch_name=self._branch,
            tracker=f"mutation-{str(self._schema.kind).lower()}-update",
            variables=input_data["variables"],
            timeout=timeout,
        )
        self._process_mutation_result(mutation_name=mutation_name, response=response, timeout=timeout)

    def _process_relationships(
        self,
        node_data: dict[str, Any],
        branch: str,
        related_nodes: list[InfrahubNodeSync],
        timeout: int | None = None,
    ) -> None:
        """Processes the Relationships of a InfrahubNodeSync and add Related Nodes to a list.

        Args:
            node_data (dict[str, Any]): The item from the GraphQL response corresponding to the node.
            branch (str): The branch name.
            related_nodes (list[InfrahubNodeSync]): The list to which related nodes will be appended.
            timeout (int, optional): Overrides default timeout used when querying the graphql API. Specified in seconds.

        """
        for rel_name in self._relationships:
            rel = getattr(self, rel_name)
            if rel and isinstance(rel, RelatedNodeSync):
                relation = node_data["node"].get(rel_name)
                if relation.get("node", None):
                    related_node = InfrahubNodeSync.from_graphql(
                        client=self._client, branch=branch, data=relation, timeout=timeout
                    )
                    related_nodes.append(related_node)
            elif rel and isinstance(rel, RelationshipManagerSync):
                peers = node_data["node"].get(rel_name)
                if peers:
                    for peer in peers["edges"]:
                        related_node = InfrahubNodeSync.from_graphql(
                            client=self._client, branch=branch, data=peer, timeout=timeout
                        )
                        related_nodes.append(related_node)

    def get_pool_allocated_resources(self, resource: InfrahubNodeSync) -> list[InfrahubNodeSync]:
        """Fetch all nodes that were allocated for the pool and a given resource.

        Args:
            resource (InfrahubNodeSync): The resource from which the nodes were allocated.

        Returns:
            list[InfrahubNodeSync]: The allocated nodes.
        """
        if not self.is_resource_pool():
            raise ValueError("Allocate resources can only be fetched from resource pool nodes.")

        graphql_query_name = "InfrahubResourcePoolAllocated"
        node_ids_per_kind: dict[str, list[str]] = {}

        has_remaining_items = True
        page_number = 1
        while has_remaining_items:
            page_offset = (page_number - 1) * self._client.pagination_size

            query = Query(
                query={
                    graphql_query_name: {
                        "@filters": {
                            "pool_id": "$pool_id",
                            "resource_id": "$resource_id",
                            "offset": page_offset,
                            "limit": self._client.pagination_size,
                        },
                        "count": None,
                        "edges": {"node": {"id": None, "kind": None, "branch": None, "identifier": None}},
                    }
                },
                name="GetAllocatedResourceForPool",
                variables={"pool_id": str, "resource_id": str},
            )
            response = self._client.execute_graphql(
                query=query.render(),
                variables={"pool_id": self.id, "resource_id": resource.id},
                branch_name=self._branch,
                tracker=f"get-allocated-resources-page{page_number}",
            )

            for edge in response[graphql_query_name]["edges"]:
                node = edge["node"]
                node_ids_per_kind.setdefault(node["kind"], []).append(node["id"])

            remaining_items = response[graphql_query_name].get("count", 0) - (
                page_offset + self._client.pagination_size
            )
            if remaining_items <= 0:
                has_remaining_items = False

            page_number += 1

        nodes: list[InfrahubNodeSync] = []
        for kind, node_ids in node_ids_per_kind.items():
            nodes.extend(self._client.filters(kind=kind, branch=self._branch, ids=node_ids))

        return nodes

    def get_pool_resources_utilization(self) -> list[dict[str, Any]]:
        """Fetch the utilization of each resource for the pool.

        Returns:
            list[dict[str, Any]]: A list containing the allocation numbers for each resource of the pool.
        """
        if not self.is_resource_pool():
            raise ValueError("Pool utilization can only be fetched for resource pool nodes.")

        graphql_query_name = "InfrahubResourcePoolUtilization"

        query = Query(
            query={
                graphql_query_name: {
                    "@filters": {"pool_id": "$pool_id"},
                    "count": None,
                    "edges": {
                        "node": {
                            "id": None,
                            "kind": None,
                            "utilization": None,
                            "utilization_branches": None,
                            "utilization_default_branch": None,
                        }
                    },
                }
            },
            name="GetUtilizationForPool",
            variables={"pool_id": str},
        )
        response = self._client.execute_graphql(
            query=query.render(),
            variables={"pool_id": self.id},
            branch_name=self._branch,
            tracker="get-pool-utilization",
        )

        if response[graphql_query_name].get("count", 0):
            return [edge["node"] for edge in response[graphql_query_name]["edges"]]
        return []
