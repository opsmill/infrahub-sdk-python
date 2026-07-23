from __future__ import annotations

from collections.abc import Iterable
from copy import copy, deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, overload

from ..constants import InfrahubClientMode, Priority
from ..exceptions import (
    FeatureNotSupportedError,
    NodeNotFoundError,
    ResourceNotDefinedError,
    SchemaNotFoundError,
    ValidationError,
)
from ..file_handler import FileHandler, FileHandlerBase, FileHandlerSync, PreparedFile, sha1_of_source
from ..graphql import Mutation, Query
from ..schema import (
    GenericSchemaAPI,
    RelationshipCardinality,
    RelationshipKind,
    RelationshipSchemaAPI,
)
from ..utils import compare_lists, generate_short_id
from .attribute import Attribute
from .constants import (
    ARTIFACT_DEFINITION_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE,
    ARTIFACT_FETCH_FEATURE_NOT_SUPPORTED_MESSAGE,
    ARTIFACT_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE,
    FILE_DOWNLOAD_FEATURE_NOT_SUPPORTED_MESSAGE,
    MATCHES_LOCAL_CHECKSUM_FEATURE_NOT_SUPPORTED_MESSAGE,
    PROPERTIES_OBJECT,
    UPLOAD_IF_CHANGED_FEATURE_NOT_SUPPORTED_MESSAGE,
)
from .metadata import NodeMetadata
from .related_node import RelatedNode, RelatedNodeBase, RelatedNodeSync
from .relationship import RelationshipManager, RelationshipManagerBase, RelationshipManagerSync

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..client import InfrahubClient, InfrahubClientSync
    from ..context import RequestContext
    from ..schema import MainSchemaTypesAPI
    from ..types import Order


@dataclass(frozen=True)
class UploadResult:
    """Outcome of an idempotent upload attempt.

    Returned by :meth:`InfrahubNode.upload_if_changed` and its sync twin.
    ``was_uploaded`` tells the caller whether a network transfer actually
    happened; ``checksum`` carries the SHA-1 of the content held on the
    server after the operation — on skip paths that is the server's
    pre-existing value, on upload paths it is the locally-computed SHA-1
    used as a proxy (which matches what a standard CoreFileObject server
    stores, since the server computes SHA-1 of received bytes). ``None``
    only when no server checksum was available (either the node was
    unsaved and nothing was transferred, or the save returned no checksum
    value).

    The comparison used by ``upload_if_changed`` reads the node's
    ``checksum`` attribute, which was populated when the node was
    fetched via ``client.get(...)``. A server-side change to the file
    between the fetch and the call will not be detected unless the
    caller re-fetches the node first.
    """

    was_uploaded: bool
    checksum: str | None


class InfrahubNodeBase:
    """Base class for :class:`InfrahubNode` and :class:`InfrahubNodeSync`.

    Owns the schema-driven state shared between the async and sync clients: attributes,
    relationships, identity (``id``, ``hfid``), node metadata, and the helpers that turn
    the in-memory state into GraphQL query and mutation payloads. This class is not
    meant to be instantiated directly; use :class:`InfrahubNode` or
    :class:`InfrahubNodeSync` instead.

    Attributes:
        id (str | None): The unique identifier of the node, when known.
        display_label (str | None): Human-readable label of the node.
        typename (str | None): The GraphQL ``__typename`` of the node.

    """

    def __init__(self, schema: MainSchemaTypesAPI, branch: str, data: dict | None = None) -> None:
        """Initialize the base node.

        Args:
            schema: The schema of the node.
            branch: The branch where the node resides.
            data: Optional data to initialize the node.

        """
        self._schema = schema
        self._data = data
        self._branch = branch
        self._existing: bool = True
        self._attribute_data: dict[str, Attribute] = {}
        self._metadata: NodeMetadata | None = None

        # Generate a unique ID only to be used inside the SDK
        # The format if this ID is purposely different from the ID used by the API
        # This is done to avoid confusion and potential conflicts between the IDs
        self._internal_id = generate_short_id()

        self.id = data.get("id", None) if isinstance(data, dict) else None
        self.display_label: str | None = data.get("display_label", None) if isinstance(data, dict) else None
        self.typename: str | None = data.get("__typename", schema.kind) if isinstance(data, dict) else schema.kind

        self._attributes = [item.name for item in self._schema.attributes]
        self._relationships = [item.name for item in self._schema.relationships]

        self._artifact_support = schema.supports_artifacts
        self._file_object_support = schema.supports_file_object
        self._hierarchy_support = schema.supports_hierarchy
        self._artifact_definition_support = schema.supports_artifact_definition

        self._file_content: bytes | Path | BinaryIO | None = None
        self._file_name: str | None = None

        if not self.id:
            self._existing = False

        self._init_attributes(data)
        self._init_relationships(data)

    def get_branch(self) -> str:
        """Return the branch this node is bound to.

        Returns:
            str: The name of the branch.

        """
        return self._branch

    def get_path_value(self, path: str) -> Any:
        """Resolve a value addressed by a dunder-separated path on this node.

        The path can target an attribute (``name__value``, ``name__source``), a
        cardinality-one related node (``parent``), an attribute of that related node
        (``parent__name__value``), or a property of one of its attributes
        (``parent__name__source``).

        Args:
            path (str): A path with components separated by ``__``.

        Returns:
            Any: The resolved value, or ``None`` when any path component cannot be
            resolved (for example, an unfetched related node not present in the store).

        """
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
        """Compute the human-friendly ID for this node from its schema.

        The HFID is composed of the values addressed by the schema's
        ``human_friendly_id`` paths. When any component cannot be resolved, the HFID is
        considered invalid and ``None`` is returned.

        Returns:
            list[str] | None: The HFID as a list of stringified components, or ``None``
            when the schema does not define an HFID or a component is missing.

        """
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
        """Return the human-friendly ID joined into a single string.

        Args:
            include_kind (bool, optional): When ``True``, the node kind is prepended as
                the first component of the resulting string. Defaults to ``False``.

        Returns:
            str | None: The HFID joined with the HFID separator, or ``None`` when no
            HFID is available.

        """
        hfid = self.get_human_friendly_id()
        if not hfid:
            return None
        if include_kind:
            hfid = [self.get_kind(), *hfid]
        return "__".join(hfid)

    @property
    def hfid(self) -> list[str] | None:
        """Return the human-friendly ID of this node as a list of components.

        Returns:
            list[str] | None: The HFID components, or ``None`` when unavailable.

        """
        return self.get_human_friendly_id()

    @property
    def hfid_str(self) -> str | None:
        """Return the human-friendly ID of this node as a string, including the kind prefix.

        Returns:
            str | None: The HFID as ``Kind__part1__part2``, or ``None`` when unavailable.

        """
        return self.get_human_friendly_id_as_string(include_kind=True)

    def get_node_metadata(self) -> NodeMetadata | None:
        """Return the node metadata (``created_at``, ``created_by``, ``updated_at``, ``updated_by``).

        The metadata is populated only when the parent query was executed with
        ``include_metadata=True``.

        Returns:
            NodeMetadata | None: The node metadata if fetched, otherwise ``None``.

        """
        return self._metadata

    def _init_attributes(self, data: dict | None = None) -> None:
        for attr_schema in self._schema.attributes:
            attr_data = data.get(attr_schema.name, None) if isinstance(data, dict) else None
            self._attribute_data[attr_schema.name] = Attribute(
                name=attr_schema.name, schema=attr_schema, data=attr_data
            )

    def __setattr__(self, name: str, value: Any) -> None:
        """Set values for attributes that exist or revert to normal behaviour."""
        if "_attribute_data" in self.__dict__ and name in self._attribute_data:
            self._attribute_data[name].value = value
            return

        super().__setattr__(name, value)

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
        """Return the schema kind of this node.

        Returns:
            str: The schema kind (for example ``"CoreAccount"``).

        """
        return self._schema.kind

    def get_all_kinds(self) -> list[str]:
        """Return this node's kind plus all generic kinds it inherits from.

        Returns:
            list[str]: The node's own kind followed by the inherited kinds, in the order
            declared on the schema.

        """
        if inherit_from := getattr(self._schema, "inherit_from", None):
            return [self._schema.kind, *inherit_from]
        return [self._schema.kind]

    def is_ip_prefix(self) -> bool:
        """Return whether this node represents an IP prefix.

        Returns:
            bool: ``True`` when the node kind is ``BuiltinIPPrefix`` or inherits from it.

        """
        builtin_ipprefix_kind = "BuiltinIPPrefix"
        return self.get_kind() == builtin_ipprefix_kind or builtin_ipprefix_kind in self._schema.inherit_from  # type: ignore[union-attr]

    def is_ip_address(self) -> bool:
        """Return whether this node represents an IP address.

        Returns:
            bool: ``True`` when the node kind is ``BuiltinIPAddress`` or inherits from it.

        """
        builtin_ipaddress_kind = "BuiltinIPAddress"
        return self.get_kind() == builtin_ipaddress_kind or builtin_ipaddress_kind in self._schema.inherit_from  # type: ignore[union-attr]

    def is_resource_pool(self) -> bool:
        """Return whether this node is a resource pool.

        Returns:
            bool: ``True`` when the node inherits from ``CoreResourcePool``.

        """
        return hasattr(self._schema, "inherit_from") and "CoreResourcePool" in self._schema.inherit_from  # type: ignore[union-attr]

    def is_file_object(self) -> bool:
        """Return whether this node inherits from ``CoreFileObject`` and supports file uploads.

        Returns:
            bool: ``True`` when file upload/download operations are supported on this node.

        """
        return self._file_object_support

    def upload_from_path(self, path: Path) -> None:
        """Set a file from disk to be uploaded when saving this FileObject node.

        The file will be streamed during upload, avoiding loading the entire file into memory.

        Args:
            path: Path to the file on disk.

        Raises:
            FeatureNotSupportedError: If this node doesn't inherit from CoreFileObject.

        Example:
            node.upload_from_path(path=Path("/path/to/large_file.pdf"))

        """
        if not self._file_object_support:
            raise FeatureNotSupportedError(
                f"File upload is not supported for {self._schema.kind}. Only nodes inheriting from CoreFileObject support file uploads."
            )
        self._file_content = path
        self._file_name = path.name

    def upload_from_bytes(self, content: bytes | BinaryIO, name: str) -> None:
        """Set content to be uploaded when saving this FileObject node.

        The content can be provided as bytes or a file-like object.
        Using BinaryIO is recommended for large content to stream during upload.

        Args:
            content: The file content as bytes or a file-like object.
            name: The filename to use for the uploaded file.

        Raises:
            FeatureNotSupportedError: If this node doesn't inherit from CoreFileObject.

        Examples:
            >>> # Using bytes (for small files)
            >>> node.upload_from_bytes(content=b"file content", name="example.txt")

            >>> # Using file-like object (for large files)
            >>> with open("/path/to/file.bin", "rb") as f:
            ...     node.upload_from_bytes(content=f, name="file.bin")

        """
        if not self._file_object_support:
            raise FeatureNotSupportedError(
                f"File upload is not supported for {self._schema.kind}. Only nodes inheriting from CoreFileObject support file uploads."
            )
        self._file_content = content
        self._file_name = name

    def clear_file(self) -> None:
        """Clear any pending file content."""
        self._file_content = None
        self._file_name = None

    async def _get_file_for_upload(self) -> PreparedFile:
        """Get the file content as a file-like object for upload (async version)."""
        return await FileHandlerBase.prepare_upload(content=self._file_content, name=self._file_name)

    def _get_file_for_upload_sync(self) -> PreparedFile:
        """Get the file content as a file-like object for upload (sync version)."""
        return FileHandlerBase.prepare_upload_sync(content=self._file_content, name=self._file_name)

    def get_raw_graphql_data(self) -> dict | None:
        """Return the raw GraphQL payload used to build this node.

        Returns:
            dict | None: The original GraphQL data, or ``None`` when the node was
            constructed without payload (for example, a brand-new node).

        """
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
        data: dict[str, Any] = {}
        variables: dict[str, Any] = {}

        for item_name in self._attributes:
            attr: Attribute = getattr(self, item_name)
            if attr._schema.read_only:
                continue
            graphql_payload = attr._generate_input_data()
            if graphql_payload.payload:
                data[item_name] = graphql_payload.payload
            if graphql_payload.variables:
                variables.update(graphql_payload.variables)

        for item_name in self._relationships:
            allocate_from_pool = False
            rel_schema = self._schema.get_relationship(name=item_name)
            if not rel_schema or rel_schema.read_only:
                continue

            rel: RelatedNodeBase | RelationshipManagerBase = getattr(self, item_name)

            if rel_schema.cardinality == RelationshipCardinality.ONE and rel_schema.optional and not rel.initialized:
                # Emit `None` only when the caller has explicitly cleared the relationship
                # (tracked by `_peer_has_been_mutated`). Without this guard, a node hydrated
                # from a partial GraphQL payload — one that didn't fetch this relationship —
                # would silently clear it on save.
                if self._existing and isinstance(rel, RelatedNodeBase) and rel._peer_has_been_mutated:
                    data[item_name] = None
                continue

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

        mutation_payload: dict[str, Any] = {"data": data}
        if context_data := self._get_request_context(request_context=request_context):
            mutation_payload["context"] = context_data

        # Add file variable for FileObject nodes with pending file content
        # file is a mutation argument at the same level as data, not inside data
        if self._file_object_support and self._file_content is not None:
            mutation_payload["file"] = "$file"
            mutation_variables["file"] = bytes

        return {
            "data": mutation_payload,
            "variables": variables,
            "mutation_variables": mutation_variables,
        }

    @staticmethod
    def _strip_unmodified_dict(data: dict, original_data: dict, variables: dict, item: str) -> None:
        data_item = data.get(item)
        if item in original_data and isinstance(original_data[item], dict) and isinstance(data_item, dict):
            for item_key in original_data[item]:
                for property_name in PROPERTIES_OBJECT:
                    if (
                        item_key == property_name
                        and isinstance(original_data[item][property_name], dict)
                        and original_data[item][property_name].get("id")
                    ):
                        original_data[item][property_name] = original_data[item][property_name]["id"]
                if item_key in data[item]:
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
        # -> I don't even know who you are (but this is not great indeed) -- gmazoyer (quoting Thanos)
        original_data_item = original_data.get(item)
        original_data_item_is_none = original_data_item is None
        if isinstance(original_data_item, dict):
            if "node" in original_data_item:
                original_data_item_is_none = original_data_item["node"] is None
            elif "id" not in original_data_item:
                original_data_item_is_none = True

        if item in data and (data_item in ({}, []) or (data_item is None and original_data_item_is_none)):
            data.pop(item)

    def _strip_unmodified(self, data: dict, variables: dict) -> tuple[dict, dict]:
        original_data = self._data or {}
        for relationship in self._relationships:
            relationship_property = getattr(self, relationship)
            if not relationship_property or relationship not in data:
                continue
            if (
                not relationship_property.initialized
                and (
                    not isinstance(relationship_property, RelatedNodeBase) or not relationship_property.schema.optional
                )
            ) or (isinstance(relationship_property, RelationshipManagerBase) and not relationship_property.has_update):
                data.pop(relationship)

        for item in original_data:
            if item in data:
                if data[item] == original_data[item]:
                    if (
                        attr := getattr(self, item, None)
                    ) and (  # this should never be None, just a safety default value
                        not isinstance(attr, Attribute) or not attr.value_has_been_mutated
                    ):
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

    def _validate_hierarchy_support(self, message: str) -> None:
        if not self._hierarchy_support:
            raise FeatureNotSupportedError(message)

    def _validate_artifact_definition_support(self, message: str) -> None:
        if not self._artifact_definition_support:
            raise FeatureNotSupportedError(message)

    def _validate_file_object_support(self, message: str) -> None:
        if not self._file_object_support:
            raise FeatureNotSupportedError(message)

    def generate_query_data_init(
        self,
        filters: dict[str, Any] | None = None,
        offset: int | str | None = None,
        limit: int | str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        partial_match: bool = False,
        order: Order | None = None,
        include_metadata: bool = False,
    ) -> dict[str, Any | dict]:
        """Build the top-level ``count``/``edges`` skeleton of a GraphQL query for this kind.

        The returned dict is the outer structure consumed by
        :meth:`generate_query_data`; it carries the ``@filters`` block and the empty
        ``edges.node`` placeholder that will later be filled by the caller.

        Args:
            filters (dict[str, Any], optional): Filters to apply to the query.
            offset (int | str, optional): Pagination offset, either a literal value or a
                GraphQL variable placeholder such as ``"$offset"``.
            limit (int | str, optional): Pagination limit, either a literal value or a
                GraphQL variable placeholder such as ``"$limit"``.
            include (list[str], optional): Attributes or relationships to include.
            exclude (list[str], optional): Attributes or relationships to exclude.
            partial_match (bool, optional): When ``True``, allow partial matches on filter
                criteria. Defaults to ``False``.
            order (Order, optional): Ordering options to apply to the query.
            include_metadata (bool, optional): When ``True``, include ``node_metadata`` in
                the result. Defaults to ``False``.

        Returns:
            dict[str, Any | dict]: The query skeleton ready to be combined with node-level
            attributes and relationships.

        Raises:
            ValueError: If the same name appears in both ``include`` and ``exclude``.

        """
        data: dict[str, Any] = {
            "count": None,
            "edges": {"node": {"id": None, "hfid": None, "display_label": None, "__typename": None}},
        }

        if include_metadata:
            data["edges"]["node_metadata"] = NodeMetadata._generate_query_data()

        data["@filters"] = deepcopy(filters) if filters is not None else {}

        if order:
            data["@filters"]["order"] = order

        if offset is not None:
            data["@filters"]["offset"] = offset

        if limit is not None:
            data["@filters"]["limit"] = limit

        if include and exclude:
            in_both, _, _ = compare_lists(include, exclude)
            if in_both:
                raise ValueError(f"{in_both} are part of both include and exclude")

        if partial_match:
            data["@filters"]["partial_match"] = True

        return data

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

    def _get_attribute(self, name: str) -> Attribute:
        if name in self._attribute_data:
            return self._attribute_data[name]

        raise ResourceNotDefinedError(message=f"The node doesn't have an attribute for {name}")

    def _validate_upsert(self, allow_upsert: bool) -> None:
        """Block an upsert that would silently duplicate because an HFID attribute is pool-sourced.

        A CoreNumberPool assigns its value when the node is created on the server, and a new
        value on every creation. When such an attribute is part of the human-friendly identifier,
        the HFID is never stable, so an upsert can never match an existing node by it: instead of
        updating, each call creates another node. Fail fast with guidance rather than duplicating
        data silently.

        Raises:
            ValidationError: If an HFID attribute is sourced from an unresolved CoreNumberPool.

        """
        if not (allow_upsert and not self.id):
            return

        for hfid_path in self._schema.human_friendly_id or []:
            attr_name = hfid_path.split("__")[0]
            try:
                attr = self._get_attribute(attr_name)
            except ResourceNotDefinedError:
                continue
            if attr.is_unresolved_pool_attribute():
                raise ValidationError(
                    identifier=attr_name,
                    message=(
                        f"Attribute '{attr_name}' is sourced from a CoreNumberPool and is part of "
                        "this node's human-friendly identifier (HFID). The pool assigns a new value "
                        "each time the node is created, so the HFID is never stable: an upsert cannot "
                        "match an existing node by it, and every run would silently create a duplicate. "
                        "To manage this node idempotently, look it up first by a stable attribute or "
                        "relationship and reuse it, or set an explicit id before saving."
                    ),
                )

    @staticmethod
    def _build_rel_query_data(
        rel_schema: RelationshipSchemaAPI,
        peer_data: dict[str, Any],
        property: bool,
        include_metadata: bool,
    ) -> dict[str, Any] | None:
        if rel_schema.cardinality == RelationshipCardinality.ONE:
            rel_data = RelatedNodeBase._generate_query_data(
                peer_data=peer_data, property=property, include_metadata=include_metadata
            )
            # Nodes involved in a hierarchy are required to inherit from a common ancestor node, and graphql
            # tries to resolve attributes in this ancestor instead of actual node. To avoid
            # invalid queries issues when attribute is missing in the common ancestor, we use a fragment
            # to explicit actual node kind we are querying.
            if rel_schema.kind == RelationshipKind.HIERARCHY:
                data_node = rel_data["node"]
                rel_data["node"] = {}
                rel_data["node"][f"...on {rel_schema.peer}"] = data_node
            return rel_data
        if rel_schema.cardinality == RelationshipCardinality.MANY:
            return RelationshipManagerBase._generate_query_data(
                peer_data=peer_data, property=property, include_metadata=include_metadata
            )
        return None


class InfrahubNode(InfrahubNodeBase):
    """Asynchronous Infrahub node bound to an :class:`InfrahubClient`.

    Provides full CRUD against the backend (:meth:`save`, :meth:`create`, :meth:`update`,
    :meth:`delete`) along with relationship traversal (:meth:`get_flat_value`,
    :meth:`extract`), feature-gated artifact and resource-pool helpers
    (:meth:`artifact_generate`, :meth:`get_pool_allocated_resources`), and file upload
    or download for nodes inheriting from ``CoreFileObject``.

    Attributes and relationships defined on the schema are exposed as instance
    attributes via attribute-style access (``node.name.value``, ``node.parent``).
    """

    def __init__(
        self,
        client: InfrahubClient,
        schema: MainSchemaTypesAPI,
        branch: str | None = None,
        data: dict | None = None,
    ) -> None:
        """Initialize the async node.

        Args:
            client: The client used to interact with the backend.
            schema: The schema of the node.
            branch: The branch where the node resides.
            data: Optional data to initialize the node.

        """
        self._client = client
        self._file_handler = FileHandler(client=client)

        # Extract node_metadata before extracting node data (node_metadata is sibling to node in edges)
        node_metadata_data: dict | None = None
        if isinstance(data, dict):
            node_metadata_data = data.get("node_metadata")
            if isinstance(data.get("node"), dict):
                data = data.get("node")

        self._relationship_cardinality_many_data: dict[str, RelationshipManager] = {}
        self._relationship_cardinality_one_data: dict[str, RelatedNode] = {}
        self._hierarchical_data: dict[str, RelatedNode | RelationshipManager] = {}

        super().__init__(schema=schema, branch=branch or client.default_branch, data=data)

        # Initialize metadata after base class init
        if node_metadata_data:
            self._metadata = NodeMetadata(node_metadata_data)

    @classmethod
    async def from_graphql(
        cls,
        client: InfrahubClient,
        branch: str,
        data: dict,
        schema: MainSchemaTypesAPI | None = None,
        timeout: int | None = None,
    ) -> Self:
        """Build an :class:`InfrahubNode` from a raw GraphQL response.

        When no ``schema`` is provided, the node kind is read from ``__typename`` in the
        payload and the schema is fetched from the client.

        Args:
            client (InfrahubClient): The client used to interact with the backend.
            branch (str): The branch the node belongs to.
            data (dict): The GraphQL payload describing the node.
            schema (MainSchemaTypesAPI, optional): Pre-fetched schema for the node kind.
                Skips the schema lookup when provided.
            timeout (int, optional): Overrides the default timeout used when fetching the
                schema. Specified in seconds.

        Returns:
            InfrahubNode: The hydrated node instance.

        Raises:
            ValueError: If ``__typename`` is missing from ``data`` and no ``schema`` was provided.

        """
        if not schema:
            node_kind = data.get("__typename") or data.get("node", {}).get("__typename", None)
            if not node_kind:
                raise ValueError("Unable to determine the type of the node, __typename not present in data")
            schema = await client.schema.get(kind=node_kind, branch=branch, timeout=timeout)

        return cls(client=client, schema=schema, branch=branch, data=cls._strip_alias(data))

    def _init_relationships(self, data: dict | RelatedNode | None = None) -> None:
        for rel_schema in self._schema.relationships:
            rel_data = data.get(rel_schema.name, None) if isinstance(data, dict) else None

            if rel_schema.cardinality == RelationshipCardinality.ONE:
                if isinstance(rel_data, RelatedNode):
                    peer_id_data: dict[str, Any] = {
                        key: value
                        for key, value in (
                            ("id", rel_data.id),
                            ("hfid", rel_data.hfid),
                            ("__typename", rel_data.typename),
                            ("kind", rel_data.kind),
                            ("display_label", rel_data.display_label),
                        )
                        if value is not None
                    }
                    rel_data = peer_id_data or None
                self._relationship_cardinality_one_data[rel_schema.name] = RelatedNode(
                    name=rel_schema.name, branch=self._branch, client=self._client, schema=rel_schema, data=rel_data
                )
            else:
                self._relationship_cardinality_many_data[rel_schema.name] = RelationshipManager(
                    name=rel_schema.name,
                    client=self._client,
                    node=self,
                    branch=self._branch,
                    schema=rel_schema,
                    data=rel_data,
                )
        # Initialize parent, children, ancestors and descendants for hierarchical nodes
        for rel_schema in self._schema.hierarchical_relationship_schemas:
            rel_data = data.get(rel_schema.name, None) if isinstance(data, dict) else None
            if rel_schema.cardinality_is_one:
                self._hierarchical_data[rel_schema.name] = RelatedNode(
                    name=rel_schema.name,
                    client=self._client,
                    branch=self._branch,
                    schema=rel_schema,
                    data=rel_data,
                )
            else:
                self._hierarchical_data[rel_schema.name] = RelationshipManager(
                    name=rel_schema.name,
                    client=self._client,
                    node=self,
                    branch=self._branch,
                    schema=rel_schema,
                    data=rel_data,
                )

    def __getattr__(self, name: str) -> Attribute | RelationshipManager | RelatedNode:
        if "_attribute_data" in self.__dict__ and name in self._attribute_data:
            return self._attribute_data[name]
        if "_relationship_cardinality_many_data" in self.__dict__ and name in self._relationship_cardinality_many_data:
            return self._relationship_cardinality_many_data[name]
        if "_relationship_cardinality_one_data" in self.__dict__ and name in self._relationship_cardinality_one_data:
            return self._relationship_cardinality_one_data[name]
        if "_hierarchical_data" in self.__dict__ and name in self._hierarchical_data:
            return self._hierarchical_data[name]

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        """Set values for relationship names that exist or revert to normal behaviour.

        Raises:
            SchemaNotFoundError: If a matching relationship schema cannot be found for ``name``.

        """
        if "_relationship_cardinality_one_data" in self.__dict__ and name in self._relationship_cardinality_one_data:
            rel_schemas = [rel_schema for rel_schema in self._schema.relationships if rel_schema.name == name]
            if not rel_schemas:
                raise SchemaNotFoundError(
                    identifier=self._schema.kind,
                    message=f"Unable to find relationship schema for '{name}' on {self._schema.kind}",
                )
            rel_schema = rel_schemas[0]
            new_rel = RelatedNode(
                name=rel_schema.name, branch=self._branch, client=self._client, schema=rel_schema, data=value
            )
            new_rel._peer_has_been_mutated = True
            self._relationship_cardinality_one_data[name] = new_rel
            return

        super().__setattr__(name, value)

    async def generate(self, nodes: list[str] | None = None) -> None:
        """Trigger artifact generation for this artifact definition.

        Only available on nodes whose kind is ``CoreArtifactDefinition``.

        Args:
            nodes (list[str], optional): The IDs of target nodes to generate artifacts
                for. When omitted, generation runs for all targets matched by the
                definition.

        Raises:
            FeatureNotSupportedError: If this node is not a ``CoreArtifactDefinition``.

        """
        self._validate_artifact_definition_support(ARTIFACT_DEFINITION_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE)

        nodes = nodes or []
        payload = {"nodes": nodes}
        resp = await self._client._post(f"{self._client.address}/api/artifact/generate/{self.id}", payload=payload)
        resp.raise_for_status()

    async def artifact_generate(self, name: str) -> None:
        """Regenerate a named artifact targeting this node.

        Looks up the ``CoreArtifact`` named ``name`` for this node, then calls
        :meth:`generate` on the related definition with this artifact's ID.

        Args:
            name (str): The name of the artifact to regenerate.

        Raises:
            FeatureNotSupportedError: If this node does not inherit from ``CoreArtifactTarget``.

        """
        self._validate_artifact_support(ARTIFACT_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE)

        artifact = await self._client.get(kind="CoreArtifact", name__value=name, object__ids=[self.id])
        await artifact._get_relationship_one(name="definition").fetch()
        await artifact._get_relationship_one(name="definition").peer.generate([artifact.id])

    async def artifact_fetch(self, name: str) -> str | dict[str, Any]:
        """Fetch the stored content of a named artifact for this node.

        Args:
            name (str): The name of the artifact to fetch.

        Returns:
            str | dict[str, Any]: The artifact content. Returns a parsed object for
            JSON-typed artifacts and a string for text-typed artifacts.

        Raises:
            FeatureNotSupportedError: If this node does not inherit from ``CoreArtifactTarget``.

        """
        self._validate_artifact_support(ARTIFACT_FETCH_FEATURE_NOT_SUPPORTED_MESSAGE)

        artifact = await self._client.get(kind="CoreArtifact", name__value=name, object__ids=[self.id])
        return await self._client.object_store.get(identifier=artifact._get_attribute(name="storage_id").value)

    @overload
    async def download_file(self, dest: None = None, skip_if_unchanged: bool = ...) -> bytes: ...

    @overload
    async def download_file(self, dest: Path, skip_if_unchanged: bool = ...) -> int: ...

    async def download_file(
        self,
        dest: Path | None = None,
        skip_if_unchanged: bool = False,
    ) -> bytes | int:
        """Download the file content from this FileObject node.

        This method is only available for nodes that inherit from CoreFileObject.
        The node must have been saved (have an id) before calling this method.

        Args:
            dest: Optional destination path. If provided, the file will be streamed
                  directly to this path (memory-efficient for large files) and the
                  number of bytes written will be returned. If not provided, the
                  file content will be returned as bytes.
            skip_if_unchanged: When ``True``, compute the SHA-1 of the file at
                  ``dest`` (which must be provided) and compare against the
                  node's ``checksum`` attribute. If they match, return ``0``
                  without hitting the network. The ``checksum`` is the value
                  loaded when this node was fetched — a later server-side
                  change to the file will not be detected unless the caller
                  re-fetches the node first.

        Returns:
            If ``dest`` is None: The file content as bytes.
            If ``dest`` is provided: The number of bytes written to the file.
            If ``skip_if_unchanged=True`` and the local file matches the server checksum: ``0``.

        Raises:
            FeatureNotSupportedError: If this node doesn't inherit from CoreFileObject.
            ValueError: If the node hasn't been saved yet, file not found, or
                  ``skip_if_unchanged=True`` was passed without a ``dest``.
            AuthenticationError: If authentication fails.

        Examples:
            >>> # Download to memory
            >>> content = await contract.download_file()

            >>> # Stream to file (memory-efficient for large files)
            >>> bytes_written = await contract.download_file(dest=Path("/tmp/contract.pdf"))

            >>> # Skip download if local file already matches server checksum
            >>> bytes_written = await contract.download_file(
            ...     dest=Path("/tmp/contract.pdf"), skip_if_unchanged=True
            ... )

        """
        self._validate_file_object_support(message=FILE_DOWNLOAD_FEATURE_NOT_SUPPORTED_MESSAGE)

        if not self.id:
            raise ValueError("Cannot download file for a node that hasn't been saved yet.")

        if skip_if_unchanged:
            if dest is None:
                raise ValueError("skip_if_unchanged requires dest to be provided")
            if dest.exists() and dest.is_file():
                server_checksum = self.checksum  # type: ignore[attr-defined]
                if server_checksum.value is not None and sha1_of_source(dest) == server_checksum.value:  # type: ignore[union-attr]
                    return 0

        return await self._file_handler.download(node_id=self.id, branch=self._branch, dest=dest)

    async def matches_local_checksum(self, source: bytes | Path | BinaryIO) -> bool:
        """Return True if ``source``'s SHA-1 matches this node's server checksum.

        Only available for nodes inheriting from ``CoreFileObject``. Callers
        that want to branch on the comparison without invoking a transfer
        should use this primitive instead of reading ``node.checksum.value``
        and hashing ``source`` themselves, so the hashing convention stays
        centralised in the SDK.

        The comparison is against the ``checksum`` attribute as loaded
        when this node was retrieved from the server. If the server's
        file has been replaced since the node was fetched, this method
        will not see that change — re-fetch the node to refresh the
        checksum before comparing.

        Args:
            source: Local content to hash and compare. Accepts the same
                shapes as :func:`infrahub_sdk.file_handler.sha1_of_source`.

        Returns:
            True if the local digest equals the server's stored checksum.

        Raises:
            FeatureNotSupportedError: Node is not a ``CoreFileObject``.
            ValueError: Node has no server-side checksum yet (unsaved or
                file never attached).

        """
        self._validate_file_object_support(message=MATCHES_LOCAL_CHECKSUM_FEATURE_NOT_SUPPORTED_MESSAGE)

        server_checksum = self.checksum  # type: ignore[attr-defined]
        if server_checksum.value is None:  # type: ignore[union-attr]
            raise ValueError(
                f"{self._schema.kind} node has no server-side checksum; "
                "ensure the node has been saved with file content attached before comparing."
            )

        return sha1_of_source(source) == server_checksum.value  # type: ignore[union-attr]

    async def upload_if_changed(
        self,
        source: bytes | Path | BinaryIO,
        name: str | None = None,
    ) -> UploadResult:
        """Upload ``source`` only if its SHA-1 differs from the server checksum.

        Composes :meth:`matches_local_checksum` with :meth:`upload_from_path`
        (or :meth:`upload_from_bytes`) and :meth:`save`. For unsaved nodes or
        nodes that have no prior server-side file, the upload is always
        performed — there is nothing to compare against.

        Idempotency is content-only: when the local SHA-1 matches the server
        checksum the upload is skipped even if ``name`` differs from the
        server-side filename. Use a regular :meth:`upload_from_path` /
        :meth:`save` round-trip if you need to rename without changing
        content.

        Args:
            source: Content to upload. ``bytes`` and ``BinaryIO`` sources
                must supply ``name``; for a ``Path`` the filename is derived
                from ``source.name`` when ``name`` is omitted.
            name: Filename to use on the server. Required for ``bytes`` /
                ``BinaryIO`` sources.

        Returns:
            :class:`UploadResult` with ``was_uploaded=False`` (skipped) or
            ``was_uploaded=True`` (transfer occurred), and the resulting server
            checksum (``None`` only when no server checksum was available
            after the operation).

        Raises:
            FeatureNotSupportedError: Node is not a ``CoreFileObject``.
            ValueError: ``source`` is ``bytes`` or ``BinaryIO`` and no
                ``name`` was supplied.

        """
        self._validate_file_object_support(message=UPLOAD_IF_CHANGED_FEATURE_NOT_SUPPORTED_MESSAGE)

        resolved_name: str | None = name
        if resolved_name is None and isinstance(source, Path):
            resolved_name = source.name
        if resolved_name is None:
            raise ValueError("name is required when source is bytes or BinaryIO")

        # Short-circuit only if we have a server checksum to compare against.
        server_checksum = self.checksum  # type: ignore[attr-defined]
        have_server_state = bool(self.id) and server_checksum.value is not None  # type: ignore[union-attr]

        # Compute digest before staging — source may only be readable once.
        local_digest = sha1_of_source(source)

        if have_server_state and local_digest == server_checksum.value:  # type: ignore[union-attr]
            return UploadResult(was_uploaded=False, checksum=server_checksum.value)  # type: ignore[union-attr]

        # Either no server state, or checksum mismatched — stage + save.
        if isinstance(source, Path):
            self.upload_from_path(path=source)
        else:
            self.upload_from_bytes(content=source, name=resolved_name)

        await self.save()

        return UploadResult(was_uploaded=True, checksum=local_digest)

    async def delete(
        self,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Delete this node on the backend.

        Args:
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.
            request_context (RequestContext, optional): Request-level context passed through
                to the mutation. When omitted, the client's request context is used.
            priority (Priority, optional): Per-request priority emitted as the X-Priority header,
                overriding the client default for this request only.

        """
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
            priority=priority,
        )

    async def save(
        self,
        allow_upsert: bool = False,
        update_group_context: bool | None = None,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Persist this node to the backend, creating or updating it as appropriate.

        New nodes are created (or upserted when ``allow_upsert`` is set), and existing
        nodes are updated with only the modified fields. After a successful save, the
        node is added to the client store and, when applicable, to the active group
        context for tracking.

        Args:
            allow_upsert (bool, optional): When ``True``, an existing node is upserted
                instead of failing with a duplicate. Defaults to ``False``.
            update_group_context (bool, optional): Whether to update the group context
                with this node. When ``None`` and the client is in tracking mode, defaults
                to ``True``.
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.
            request_context (RequestContext, optional): Request-level context passed through
                to the mutation. When omitted, the client's request context is used.
            priority (Priority, optional): Per-request priority emitted as the X-Priority header,
                overriding the client default for this request only.

        """
        if self._existing is False or allow_upsert is True:
            await self.create(
                allow_upsert=allow_upsert, timeout=timeout, request_context=request_context, priority=priority
            )
        else:
            await self.update(timeout=timeout, request_context=request_context, priority=priority)

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

    async def _process_hierarchical_fields(
        self,
        data: dict[str, Any],
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        prefetch_relationships: bool = False,
        insert_alias: bool = False,
        property: bool = False,
    ) -> None:
        """Process hierarchical fields (parent, children, ancestors, descendants) for hierarchical nodes."""
        if not self._hierarchy_support:
            return

        for hierarchical_name in ["parent", "children", "ancestors", "descendants"]:
            if exclude and hierarchical_name in exclude:
                continue

            # Only include if explicitly requested or if prefetch_relationships is True
            should_fetch = prefetch_relationships or (include is not None and hierarchical_name in include)
            if not should_fetch:
                continue

            peer_schema = await self._client.schema.get(kind=self._schema.hierarchy, branch=self._branch)  # type: ignore[union-attr, arg-type]
            peer_node = InfrahubNode(client=self._client, schema=peer_schema, branch=self._branch)
            # Exclude hierarchical fields from peer data to prevent infinite recursion
            peer_exclude = list(exclude) if exclude else []
            peer_exclude.extend(["parent", "children", "ancestors", "descendants"])
            peer_data = await peer_node.generate_query_data_node(
                exclude=peer_exclude,
                property=property,
            )

            # Parent is cardinality one, others are cardinality many
            if hierarchical_name == "parent":
                hierarchical_data = RelatedNode._generate_query_data(peer_data=peer_data, property=property)
                # Use fragment for hierarchical fields similar to hierarchy relationships
                data_node = hierarchical_data["node"]
                hierarchical_data["node"] = {}
                hierarchical_data["node"][f"...on {self._schema.hierarchy}"] = data_node  # type: ignore[union-attr]
            else:
                hierarchical_data = RelationshipManager._generate_query_data(peer_data=peer_data, property=property)
                # Use fragment for hierarchical fields similar to hierarchy relationships
                data_node = hierarchical_data["edges"]["node"]
                hierarchical_data["edges"]["node"] = {}
                hierarchical_data["edges"]["node"][f"...on {self._schema.hierarchy}"] = data_node  # type: ignore[union-attr]

            data[hierarchical_name] = hierarchical_data

            if insert_alias:
                data[hierarchical_name]["@alias"] = f"__alias__{self._schema.kind}__{hierarchical_name}"

    async def generate_query_data(
        self,
        filters: dict[str, Any] | None = None,
        offset: int | str | None = None,
        limit: int | str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        partial_match: bool = False,
        property: bool = False,
        order: Order | None = None,
        include_metadata: bool = False,
    ) -> dict[str, Any | dict]:
        """Generate the full GraphQL query payload for this node kind.

        The returned dict combines :meth:`generate_query_data_init` with
        :meth:`generate_query_data_node`. When the node is a generic and ``fragment`` is
        ``True``, ``...on Kind`` fragments are added for every implementing kind so the
        relevant attributes are returned alongside the generic fields.

        Args:
            filters (dict[str, Any], optional): Filters to apply to the query.
            offset (int | str, optional): Pagination offset, either a literal value or a
                GraphQL variable placeholder such as ``"$offset"``.
            limit (int | str, optional): Pagination limit, either a literal value or a
                GraphQL variable placeholder such as ``"$limit"``.
            include (list[str], optional): Attributes or relationships to include.
            exclude (list[str], optional): Attributes or relationships to exclude.
            fragment (bool, optional): When ``True`` and the schema is a generic, emit
                ``...on Kind`` fragments for each implementing kind. Defaults to ``False``.
            prefetch_relationships (bool, optional): When ``True``, pre-fetch related node
                data instead of returning only their identifiers. Defaults to ``False``.
            partial_match (bool, optional): When ``True``, allow partial matches on filter
                criteria. Defaults to ``False``.
            property (bool, optional): When ``True``, include attribute and relationship
                properties (``source``, ``owner``, ``is_protected``, ...). Defaults to ``False``.
            order (Order, optional): Ordering options to apply to the query.
            include_metadata (bool, optional): When ``True``, include ``node_metadata`` and
                ``relationship_metadata`` in the result. Defaults to ``False``.

        Returns:
            dict[str, Any | dict]: A query payload keyed by the node kind, ready to be
            rendered as GraphQL.

        """
        data = self.generate_query_data_init(
            filters=filters,
            offset=offset,
            limit=limit,
            include=include,
            exclude=exclude,
            partial_match=partial_match,
            order=order,
            include_metadata=include_metadata,
        )
        data["edges"]["node"].update(
            await self.generate_query_data_node(
                include=include,
                exclude=exclude,
                prefetch_relationships=prefetch_relationships,
                inherited=True,
                property=property,
                include_metadata=include_metadata,
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
                    include_metadata=include_metadata,
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
        include_metadata: bool = False,
    ) -> dict[str, Any | dict]:
        """Generate the node part of a GraphQL Query with attributes and nodes.

        Args:
            include (Optional[list[str]], optional): List of attributes or relationships to include. Defaults to None.
            exclude (Optional[list[str]], optional): List of attributes or relationships to exclude. Defaults to None.
            inherited (bool, optional): Indicated of the attributes and the relationships inherited from generics should be included as well.
                                        Defaults to True.
            insert_alias (bool, optional): If True, inserts aliases in the query for each attribute or relationship.
            prefetch_relationships (bool, optional): If True, pre-fetches relationship data as part of the query.
            include_metadata (bool, optional): If True, includes node_metadata and relationship_metadata in the query.

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

            attr_data = attr._generate_query_data(property=property, include_metadata=include_metadata)
            if attr_data:
                data[attr_name] = attr_data
                if insert_alias:
                    data[attr_name]["@alias"] = f"__alias__{self._schema.kind}__{attr_name}"
            elif insert_alias:
                data[attr_name] = {"@alias": f"__alias__{self._schema.kind}__{attr_name}"}

        for rel_name in self._relationships:
            if exclude and rel_name in exclude:
                continue

            rel_schema = self._schema.get_relationship(name=rel_name)

            if not rel_schema or (not inherited and rel_schema.inherited):
                continue

            if (
                rel_schema.cardinality == RelationshipCardinality.MANY  # type: ignore[union-attr]
                and rel_schema.kind not in {RelationshipKind.ATTRIBUTE, RelationshipKind.PARENT}  # type: ignore[union-attr]
                and not (include and rel_name in include)
            ):
                continue

            peer_data: dict[str, Any] = {}
            should_fetch_relationship = prefetch_relationships or (include is not None and rel_name in include)
            if rel_schema and should_fetch_relationship:
                peer_schema = await self._client.schema.get(kind=rel_schema.peer, branch=self._branch)
                peer_node = InfrahubNode(client=self._client, schema=peer_schema, branch=self._branch)
                peer_data = await peer_node.generate_query_data_node(
                    property=property,
                    include_metadata=include_metadata,
                )

            rel_data = self._build_rel_query_data(rel_schema, peer_data, property, include_metadata)
            if rel_data is None:
                continue

            data[rel_name] = rel_data

            if insert_alias:
                data[rel_name]["@alias"] = f"__alias__{self._schema.kind}__{rel_name}"

        # Add parent, children, ancestors and descendants for hierarchical nodes
        await self._process_hierarchical_fields(
            data=data,
            include=include,
            exclude=exclude,
            prefetch_relationships=prefetch_relationships,
            insert_alias=insert_alias,
            property=property,
        )

        return data

    async def add_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None:
        """Add peers to a cardinality-many relationship through a dedicated mutation.

        Unlike :meth:`save`, this method targets a single relationship and only adds
        peers, leaving every other field untouched.

        Args:
            relation_to_update (str): The name of the relationship to update.
            related_nodes (list[str]): The IDs of the peers to add.

        """
        query = self._relationship_mutation(
            action="Add", relation_to_update=relation_to_update, related_nodes=related_nodes
        )
        tracker = f"mutation-{str(self._schema.kind).lower()}-relationshipadd-{relation_to_update}"
        await self._client.execute_graphql(query=query, branch_name=self._branch, tracker=tracker)

    async def remove_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None:
        """Remove peers from a cardinality-many relationship through a dedicated mutation.

        Unlike :meth:`save`, this method targets a single relationship and only removes
        the listed peers, leaving every other field untouched.

        Args:
            relation_to_update (str): The name of the relationship to update.
            related_nodes (list[str]): The IDs of the peers to remove.

        """
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
        self,
        mutation_name: str,
        response: dict[str, Any],
        timeout: int | None = None,
        priority: Priority | None = None,
    ) -> None:
        object_response: dict[str, Any] = response[mutation_name]["object"]
        self.id = object_response["id"]
        self._existing = True

        for attr_name in self._attributes:
            attr = getattr(self, attr_name)
            if attr_name not in object_response or not attr.is_from_pool_attribute():
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
            await related_node.fetch(timeout=timeout, priority=priority)
            setattr(self, rel_name, related_node)

    async def create(
        self,
        allow_upsert: bool = False,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Create this node on the backend.

        For nodes inheriting from ``CoreFileObject``, the file content set with
        :meth:`upload_from_path` or :meth:`upload_from_bytes` is uploaded as part of the
        mutation and cleared from the node afterward.

        Prefer :meth:`save` over calling ``create()`` directly so existing-vs-new logic
        is handled for you.

        Args:
            allow_upsert (bool, optional): When ``True``, the operation upserts instead of
                erroring on a duplicate. Defaults to ``False``.
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.
            request_context (RequestContext, optional): Request-level context passed through
                to the mutation. When omitted, the client's request context is used.
            priority (Priority, optional): Per-request priority emitted as the X-Priority header,
                overriding the client default for this request only.

        Raises:
            ValueError: If this is a file-object node and no file content has been set.

        """
        self._validate_upsert(allow_upsert=allow_upsert)

        if self._file_object_support and self._file_content is None:
            raise ValueError(
                f"Cannot create {self._schema.kind} without file content. Use upload_from_path() or upload_from_bytes() to provide "
                "file content before saving."
            )

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

        if "file" in input_data["mutation_variables"]:
            prepared = await self._get_file_for_upload()
            try:
                response = await self._client._execute_graphql_with_file(
                    query=query.render(),
                    variables=input_data["variables"],
                    file_content=prepared.file_object,
                    file_name=prepared.filename,
                    branch_name=self._branch,
                    tracker=tracker,
                    timeout=timeout,
                    priority=priority,
                )
            finally:
                if prepared.should_close and prepared.file_object:
                    prepared.file_object.close()
            # Clear the file content after successful upload
            self.clear_file()
        else:
            response = await self._client.execute_graphql(
                query=query.render(),
                branch_name=self._branch,
                tracker=tracker,
                variables=input_data["variables"],
                timeout=timeout,
                priority=priority,
            )
        await self._process_mutation_result(
            mutation_name=mutation_name, response=response, timeout=timeout, priority=priority
        )

    async def update(
        self,
        do_full_update: bool = False,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Update this node on the backend.

        By default only the modified attributes and relationships are sent so the server
        can compute a minimal diff. Setting ``do_full_update`` re-sends every field even
        when unchanged, which is useful when forcing relationship reconciliation.

        Prefer :meth:`save` over calling ``update()`` directly so existing-vs-new logic
        is handled for you.

        Args:
            do_full_update (bool, optional): When ``True``, send every field even when
                unmodified. Defaults to ``False``.
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.
            request_context (RequestContext, optional): Request-level context passed through
                to the mutation. When omitted, the client's request context is used.
            priority (Priority, optional): Per-request priority emitted as the X-Priority header,
                overriding the client default for this request only.

        """
        input_data = self._generate_input_data(exclude_unmodified=not do_full_update, request_context=request_context)
        mutation_query = self._generate_mutation_query()
        mutation_name = f"{self._schema.kind}Update"
        tracker = f"mutation-{str(self._schema.kind).lower()}-update"

        query = Mutation(
            mutation=mutation_name,
            input_data=input_data["data"],
            query=mutation_query,
            variables=input_data["mutation_variables"],
        )

        if "file" in input_data["mutation_variables"]:
            prepared = await self._get_file_for_upload()
            try:
                response = await self._client._execute_graphql_with_file(
                    query=query.render(),
                    variables=input_data["variables"],
                    file_content=prepared.file_object,
                    file_name=prepared.filename,
                    branch_name=self._branch,
                    tracker=tracker,
                    timeout=timeout,
                    priority=priority,
                )
            finally:
                if prepared.should_close and prepared.file_object:
                    prepared.file_object.close()
            # Clear the file content after successful upload
            self.clear_file()
        else:
            response = await self._client.execute_graphql(
                query=query.render(),
                branch_name=self._branch,
                timeout=timeout,
                tracker=tracker,
                variables=input_data["variables"],
                priority=priority,
            )
        await self._process_mutation_result(
            mutation_name=mutation_name, response=response, timeout=timeout, priority=priority
        )

    async def _process_relationships(
        self,
        node_data: dict[str, Any],
        branch: str,
        related_nodes: list[InfrahubNode],
        timeout: int | None = None,
        recursive: bool = False,
    ) -> None:
        """Processes the Relationships of a InfrahubNode and add Related Nodes to a list.

        Args:
            node_data (dict[str, Any]): The item from the GraphQL response corresponding to the node.
            branch (str): The branch name.
            related_nodes (list[InfrahubNode]): The list to which related nodes will be appended.
            timeout (int, optional): Overrides default timeout used when querying the graphql API. Specified in seconds.
            recursive:(bool): Whether to recursively process relationships of related nodes.

        """
        for rel_name in self._relationships:
            rel = getattr(self, rel_name)
            if rel and isinstance(rel, RelatedNode):
                relation = node_data["node"].get(rel_name, None)
                if relation and relation.get("node", None):
                    related_node = await InfrahubNode.from_graphql(
                        client=self._client,
                        branch=branch,
                        data=relation,
                        timeout=timeout,
                    )
                    related_nodes.append(related_node)
                    if recursive:
                        await related_node._process_relationships(
                            node_data=relation,
                            branch=branch,
                            related_nodes=related_nodes,
                            recursive=recursive,
                        )
            elif rel and isinstance(rel, RelationshipManager):
                peers = node_data["node"].get(rel_name, None)
                if peers and peers["edges"]:
                    for peer in peers["edges"]:
                        related_node = await InfrahubNode.from_graphql(
                            client=self._client,
                            branch=branch,
                            data=peer,
                            timeout=timeout,
                        )
                        related_nodes.append(related_node)
                        if recursive:
                            await related_node._process_relationships(
                                node_data=peer,
                                branch=branch,
                                related_nodes=related_nodes,
                                recursive=recursive,
                            )

    async def get_pool_allocated_resources(self, resource: InfrahubNode) -> list[InfrahubNode]:
        """Fetch all nodes that were allocated for the pool and a given resource.

        Args:
            resource (InfrahubNode): The resource from which the nodes were allocated.

        Returns:
            list[InfrahubNode]: The allocated nodes.

        Raises:
            ValueError: If the node is not a resource pool.

        """
        if not self.is_resource_pool():
            raise ValueError("Allocated resources can only be fetched from resource pool nodes.")

        graphql_query_name = "InfrahubResourcePoolAllocated"
        node_ids_per_kind: dict[str, list[str]] = {}

        query = Query(
            query={
                graphql_query_name: {
                    "@filters": {
                        "pool_id": "$pool_id",
                        "resource_id": "$resource_id",
                        "offset": "$offset",
                        "limit": "$limit",
                    },
                    "count": None,
                    "edges": {"node": {"id": None, "kind": None, "branch": None, "identifier": None}},
                }
            },
            name="GetAllocatedResourceForPool",
            variables={"pool_id": str, "resource_id": str, "offset": int, "limit": int},
        )
        query_str = query.render()

        has_remaining_items = True
        page_number = 1
        while has_remaining_items:
            page_offset = (page_number - 1) * self._client.pagination_size

            response = await self._client.execute_graphql(
                query=query_str,
                variables={
                    "pool_id": self.id,
                    "resource_id": resource.id,
                    "offset": page_offset,
                    "limit": self._client.pagination_size,
                },
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

        Raises:
            ValueError: If the node is not a resource pool.

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

    def _get_relationship_many(self, name: str) -> RelationshipManager:
        if name in self._relationship_cardinality_many_data:
            return self._relationship_cardinality_many_data[name]

        raise ResourceNotDefinedError(message=f"The node doesn't have a cardinality=many relationship for {name}")

    def _get_relationship_one(self, name: str) -> RelatedNode:
        if name in self._relationship_cardinality_one_data:
            return self._relationship_cardinality_one_data[name]

        raise ResourceNotDefinedError(message=f"The node doesn't have a cardinality=one relationship for {name}")

    async def get_flat_value(self, key: str, separator: str = "__") -> Any:
        """Resolve a value addressed by a flat key over this node and its related nodes.

        Walks attributes on this node, descending through cardinality-one relationships
        (which are fetched on demand) until the final component is reached. Each
        relationship hop incurs a backend call, so this is intended for ad-hoc lookups
        rather than bulk traversal.

        Args:
            key (str): The flat key to resolve (for example ``"name__value"`` or
                ``"site__name__value"``).
            separator (str, optional): Component separator in ``key``. Defaults to ``"__"``.

        Returns:
            Any: The resolved value.

        Raises:
            ValueError: If a component does not match an attribute or relationship, or if
                a relationship hop targets a non cardinality-one relationship.

        Examples:
            name__value
            module.object.value

        """
        if separator not in key:
            return getattr(self, key)

        first, remaining = key.split(separator, maxsplit=1)

        if first in self._schema.attribute_names:
            attr = getattr(self, first)
            for part in remaining.split(separator):
                attr = getattr(attr, part)
            return attr

        try:
            rel = self._schema.get_relationship(name=first)
        except ValueError as exc:
            raise ValueError(f"No attribute or relationship named '{first}' for '{self._schema.kind}'") from exc

        if rel.cardinality != RelationshipCardinality.ONE:
            raise ValueError(
                f"Can only look up flat value for relationships of cardinality {RelationshipCardinality.ONE.value}"
            )

        related_node: RelatedNode = getattr(self, first)
        await related_node.fetch()
        return await related_node.peer.get_flat_value(key=remaining, separator=separator)

    async def extract(self, params: dict[str, str]) -> dict[str, Any]:
        """Extract several values addressed by flat keys into a labeled dict.

        Each value in ``params`` is resolved with :meth:`get_flat_value`, and the
        corresponding key is preserved as the output label.

        Args:
            params (dict[str, str]): A mapping of output label to flat key to resolve.

        Returns:
            dict[str, Any]: The resolved values keyed by their output label.

        """
        result: dict[str, Any] = {}
        for key, value in params.items():
            result[key] = await self.get_flat_value(key=value)

        return result

    def __dir__(self) -> Iterable[str]:
        base = list(super().__dir__())
        return sorted(
            base
            + list(self._attribute_data.keys())
            + list(self._relationship_cardinality_many_data.keys())
            + list(self._relationship_cardinality_one_data.keys())
        )


class InfrahubNodeSync(InfrahubNodeBase):
    """Synchronous Infrahub node bound to an :class:`InfrahubClientSync`.

    Synchronous counterpart of :class:`InfrahubNode`. Provides full CRUD against the
    backend (:meth:`save`, :meth:`create`, :meth:`update`, :meth:`delete`) along with
    relationship traversal (:meth:`get_flat_value`, :meth:`extract`), feature-gated
    artifact and resource-pool helpers (:meth:`artifact_generate`,
    :meth:`get_pool_allocated_resources`), and file upload or download for nodes
    inheriting from ``CoreFileObject``.

    Attributes and relationships defined on the schema are exposed as instance
    attributes via attribute-style access (``node.name.value``, ``node.parent``).
    """

    def __init__(
        self,
        client: InfrahubClientSync,
        schema: MainSchemaTypesAPI,
        branch: str | None = None,
        data: dict | None = None,
    ) -> None:
        """Initialize the sync node.

        Args:
            client (InfrahubClientSync): The client used to interact with the backend synchronously.
            schema (MainSchemaTypes): The schema of the node.
            branch (Optional[str]): The branch where the node resides.
            data (Optional[dict]): Optional data to initialize the node.

        """
        self._client = client
        self._file_handler = FileHandlerSync(client=client)

        # Extract node_metadata before extracting node data (node_metadata is sibling to node in edges)
        node_metadata_data: dict | None = None
        if isinstance(data, dict):
            node_metadata_data = data.get("node_metadata")
            if isinstance(data.get("node"), dict):
                data = data.get("node")

        self._relationship_cardinality_many_data: dict[str, RelationshipManagerSync] = {}
        self._relationship_cardinality_one_data: dict[str, RelatedNodeSync] = {}
        self._hierarchical_data: dict[str, RelatedNodeSync | RelationshipManagerSync] = {}

        super().__init__(schema=schema, branch=branch or client.default_branch, data=data)

        # Initialize metadata after base class init
        if node_metadata_data:
            self._metadata = NodeMetadata(node_metadata_data)

    @classmethod
    def from_graphql(
        cls,
        client: InfrahubClientSync,
        branch: str,
        data: dict,
        schema: MainSchemaTypesAPI | None = None,
        timeout: int | None = None,
    ) -> Self:
        """Build an :class:`InfrahubNodeSync` from a raw GraphQL response.

        When no ``schema`` is provided, the node kind is read from ``__typename`` in the
        payload and the schema is fetched from the client.

        Args:
            client (InfrahubClientSync): The client used to interact with the backend.
            branch (str): The branch the node belongs to.
            data (dict): The GraphQL payload describing the node.
            schema (MainSchemaTypesAPI, optional): Pre-fetched schema for the node kind.
                Skips the schema lookup when provided.
            timeout (int, optional): Overrides the default timeout used when fetching the
                schema. Specified in seconds.

        Returns:
            InfrahubNodeSync: The hydrated node instance.

        Raises:
            ValueError: If ``__typename`` is missing from ``data`` and no ``schema`` was provided.

        """
        if not schema:
            node_kind = data.get("__typename") or data.get("node", {}).get("__typename", None)
            if not node_kind:
                raise ValueError("Unable to determine the type of the node, __typename not present in data")
            schema = client.schema.get(kind=node_kind, branch=branch, timeout=timeout)

        return cls(client=client, schema=schema, branch=branch, data=cls._strip_alias(data))

    def _init_relationships(self, data: dict | RelatedNodeSync | None = None) -> None:
        for rel_schema in self._schema.relationships:
            rel_data = data.get(rel_schema.name, None) if isinstance(data, dict) else None

            if rel_schema.cardinality == RelationshipCardinality.ONE:
                if isinstance(rel_data, RelatedNodeSync):
                    peer_id_data: dict[str, Any] = {
                        key: value
                        for key, value in (
                            ("id", rel_data.id),
                            ("hfid", rel_data.hfid),
                            ("__typename", rel_data.typename),
                            ("kind", rel_data.kind),
                            ("display_label", rel_data.display_label),
                        )
                        if value is not None
                    }
                    rel_data = peer_id_data or None
                self._relationship_cardinality_one_data[rel_schema.name] = RelatedNodeSync(
                    name=rel_schema.name, branch=self._branch, client=self._client, schema=rel_schema, data=rel_data
                )
            else:
                self._relationship_cardinality_many_data[rel_schema.name] = RelationshipManagerSync(
                    name=rel_schema.name,
                    client=self._client,
                    node=self,
                    branch=self._branch,
                    schema=rel_schema,
                    data=rel_data,
                )

        # Initialize parent, children, ancestors and descendants for hierarchical nodes
        for rel_schema in self._schema.hierarchical_relationship_schemas:
            rel_data = data.get(rel_schema.name, None) if isinstance(data, dict) else None
            if rel_schema.cardinality_is_one:
                self._hierarchical_data[rel_schema.name] = RelatedNodeSync(
                    name=rel_schema.name,
                    client=self._client,
                    branch=self._branch,
                    schema=rel_schema,
                    data=rel_data,
                )
            else:
                self._hierarchical_data[rel_schema.name] = RelationshipManagerSync(
                    name=rel_schema.name,
                    client=self._client,
                    node=self,
                    branch=self._branch,
                    schema=rel_schema,
                    data=rel_data,
                )

    def __getattr__(self, name: str) -> Attribute | RelationshipManagerSync | RelatedNodeSync:
        if "_attribute_data" in self.__dict__ and name in self._attribute_data:
            return self._attribute_data[name]
        if "_relationship_cardinality_many_data" in self.__dict__ and name in self._relationship_cardinality_many_data:
            return self._relationship_cardinality_many_data[name]
        if "_relationship_cardinality_one_data" in self.__dict__ and name in self._relationship_cardinality_one_data:
            return self._relationship_cardinality_one_data[name]
        if "_hierarchical_data" in self.__dict__ and name in self._hierarchical_data:
            return self._hierarchical_data[name]

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        """Set values for relationship names that exist or revert to normal behaviour.

        Raises:
            SchemaNotFoundError: If a matching relationship schema cannot be found for ``name``.

        """
        if "_relationship_cardinality_one_data" in self.__dict__ and name in self._relationship_cardinality_one_data:
            rel_schemas = [rel_schema for rel_schema in self._schema.relationships if rel_schema.name == name]
            if not rel_schemas:
                raise SchemaNotFoundError(
                    identifier=self._schema.kind,
                    message=f"Unable to find relationship schema for '{name}' on {self._schema.kind}",
                )
            rel_schema = rel_schemas[0]
            new_rel = RelatedNodeSync(
                name=rel_schema.name, branch=self._branch, client=self._client, schema=rel_schema, data=value
            )
            new_rel._peer_has_been_mutated = True
            self._relationship_cardinality_one_data[name] = new_rel
            return

        super().__setattr__(name, value)

    def generate(self, nodes: list[str] | None = None) -> None:
        """Trigger artifact generation for this artifact definition.

        Only available on nodes whose kind is ``CoreArtifactDefinition``.

        Args:
            nodes (list[str], optional): The IDs of target nodes to generate artifacts
                for. When omitted, generation runs for all targets matched by the
                definition.

        Raises:
            FeatureNotSupportedError: If this node is not a ``CoreArtifactDefinition``.

        """
        self._validate_artifact_definition_support(ARTIFACT_DEFINITION_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE)
        nodes = nodes or []
        payload = {"nodes": nodes}
        resp = self._client._post(f"{self._client.address}/api/artifact/generate/{self.id}", payload=payload)
        resp.raise_for_status()

    def artifact_generate(self, name: str) -> None:
        """Regenerate a named artifact targeting this node.

        Looks up the ``CoreArtifact`` named ``name`` for this node, then calls
        :meth:`generate` on the related definition with this artifact's ID.

        Args:
            name (str): The name of the artifact to regenerate.

        Raises:
            FeatureNotSupportedError: If this node does not inherit from ``CoreArtifactTarget``.

        """
        self._validate_artifact_support(ARTIFACT_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE)
        artifact = self._client.get(kind="CoreArtifact", name__value=name, object__ids=[self.id])
        artifact._get_relationship_one(name="definition").fetch()
        artifact._get_relationship_one(name="definition").peer.generate([artifact.id])

    def artifact_fetch(self, name: str) -> str | dict[str, Any]:
        """Fetch the stored content of a named artifact for this node.

        Args:
            name (str): The name of the artifact to fetch.

        Returns:
            str | dict[str, Any]: The artifact content. Returns a parsed object for
            JSON-typed artifacts and a string for text-typed artifacts.

        Raises:
            FeatureNotSupportedError: If this node does not inherit from ``CoreArtifactTarget``.

        """
        self._validate_artifact_support(ARTIFACT_FETCH_FEATURE_NOT_SUPPORTED_MESSAGE)
        artifact = self._client.get(kind="CoreArtifact", name__value=name, object__ids=[self.id])
        return self._client.object_store.get(identifier=artifact._get_attribute(name="storage_id").value)

    @overload
    def download_file(self, dest: None = None, skip_if_unchanged: bool = ...) -> bytes: ...

    @overload
    def download_file(self, dest: Path, skip_if_unchanged: bool = ...) -> int: ...

    def download_file(
        self,
        dest: Path | None = None,
        skip_if_unchanged: bool = False,
    ) -> bytes | int:
        """Download the file content from this FileObject node.

        This method is only available for nodes that inherit from CoreFileObject.
        The node must have been saved (have an id) before calling this method.

        Args:
            dest: Optional destination path. If provided, the file will be streamed
                  directly to this path (memory-efficient for large files) and the
                  number of bytes written will be returned. If not provided, the
                  file content will be returned as bytes.
            skip_if_unchanged: When ``True``, compute the SHA-1 of the file at
                  ``dest`` (which must be provided) and compare against the
                  node's ``checksum`` attribute. If they match, return ``0``
                  without hitting the network. The ``checksum`` is the value
                  loaded when this node was fetched — a later server-side
                  change to the file will not be detected unless the caller
                  re-fetches the node first.

        Returns:
            If ``dest`` is None: The file content as bytes.
            If ``dest`` is provided: The number of bytes written to the file.
            If ``skip_if_unchanged=True`` and the local file matches the server checksum: ``0``.

        Raises:
            FeatureNotSupportedError: If this node doesn't inherit from CoreFileObject.
            ValueError: If the node hasn't been saved yet, file not found, or
                  ``skip_if_unchanged=True`` was passed without a ``dest``.
            AuthenticationError: If authentication fails.

        Examples:
            >>> # Download to memory
            >>> content = contract.download_file()

            >>> # Stream to file (memory-efficient for large files)
            >>> bytes_written = contract.download_file(dest=Path("/tmp/contract.pdf"))

            >>> # Skip download if local file already matches server checksum
            >>> bytes_written = contract.download_file(
            ...     dest=Path("/tmp/contract.pdf"), skip_if_unchanged=True
            ... )

        """
        self._validate_file_object_support(message=FILE_DOWNLOAD_FEATURE_NOT_SUPPORTED_MESSAGE)

        if not self.id:
            raise ValueError("Cannot download file for a node that hasn't been saved yet.")

        if skip_if_unchanged:
            if dest is None:
                raise ValueError("skip_if_unchanged requires dest to be provided")
            if dest.exists() and dest.is_file():
                server_checksum = self.checksum  # type: ignore[attr-defined]
                if server_checksum.value is not None and sha1_of_source(dest) == server_checksum.value:  # type: ignore[union-attr]
                    return 0

        return self._file_handler.download(node_id=self.id, branch=self._branch, dest=dest)

    def matches_local_checksum(self, source: bytes | Path | BinaryIO) -> bool:
        """Return True if ``source``'s SHA-1 matches this node's server checksum.

        Only available for nodes inheriting from ``CoreFileObject``. Callers
        that want to branch on the comparison without invoking a transfer
        should use this primitive instead of reading ``node.checksum.value``
        and hashing ``source`` themselves, so the hashing convention stays
        centralised in the SDK.

        The comparison is against the ``checksum`` attribute as loaded
        when this node was retrieved from the server. If the server's
        file has been replaced since the node was fetched, this method
        will not see that change — re-fetch the node to refresh the
        checksum before comparing.

        Args:
            source: Local content to hash and compare. Accepts the same
                shapes as :func:`infrahub_sdk.file_handler.sha1_of_source`.

        Returns:
            True if the local digest equals the server's stored checksum.

        Raises:
            FeatureNotSupportedError: Node is not a ``CoreFileObject``.
            ValueError: Node has no server-side checksum yet (unsaved or
                file never attached).

        """
        self._validate_file_object_support(message=MATCHES_LOCAL_CHECKSUM_FEATURE_NOT_SUPPORTED_MESSAGE)

        server_checksum = self.checksum  # type: ignore[attr-defined]
        if server_checksum.value is None:  # type: ignore[union-attr]
            raise ValueError(
                f"{self._schema.kind} node has no server-side checksum; "
                "ensure the node has been saved with file content attached before comparing."
            )

        return sha1_of_source(source) == server_checksum.value  # type: ignore[union-attr]

    def upload_if_changed(
        self,
        source: bytes | Path | BinaryIO,
        name: str | None = None,
    ) -> UploadResult:
        """Upload ``source`` only if its SHA-1 differs from the server checksum.

        Composes :meth:`matches_local_checksum` with :meth:`upload_from_path`
        (or :meth:`upload_from_bytes`) and :meth:`save`. For unsaved nodes or
        nodes that have no prior server-side file, the upload is always
        performed — there is nothing to compare against.

        Idempotency is content-only: when the local SHA-1 matches the server
        checksum the upload is skipped even if ``name`` differs from the
        server-side filename. Use a regular :meth:`upload_from_path` /
        :meth:`save` round-trip if you need to rename without changing
        content.

        Args:
            source: Content to upload. ``bytes`` and ``BinaryIO`` sources
                must supply ``name``; for a ``Path`` the filename is derived
                from ``source.name`` when ``name`` is omitted.
            name: Filename to use on the server. Required for ``bytes`` /
                ``BinaryIO`` sources.

        Returns:
            :class:`UploadResult` with ``was_uploaded=False`` (skipped) or
            ``was_uploaded=True`` (transfer occurred), and the resulting server
            checksum (``None`` only when no server checksum was available
            after the operation).

        Raises:
            FeatureNotSupportedError: Node is not a ``CoreFileObject``.
            ValueError: ``source`` is ``bytes`` or ``BinaryIO`` and no
                ``name`` was supplied.

        """
        self._validate_file_object_support(message=UPLOAD_IF_CHANGED_FEATURE_NOT_SUPPORTED_MESSAGE)

        resolved_name: str | None = name
        if resolved_name is None and isinstance(source, Path):
            resolved_name = source.name
        if resolved_name is None:
            raise ValueError("name is required when source is bytes or BinaryIO")

        # Short-circuit only if we have a server checksum to compare against.
        server_checksum = self.checksum  # type: ignore[attr-defined]
        have_server_state = bool(self.id) and server_checksum.value is not None  # type: ignore[union-attr]

        # Compute digest before staging — source may only be readable once.
        local_digest = sha1_of_source(source)

        if have_server_state and local_digest == server_checksum.value:  # type: ignore[union-attr]
            return UploadResult(was_uploaded=False, checksum=server_checksum.value)  # type: ignore[union-attr]

        # Either no server state, or checksum mismatched — stage + save.
        if isinstance(source, Path):
            self.upload_from_path(path=source)
        else:
            self.upload_from_bytes(content=source, name=resolved_name)

        self.save()

        return UploadResult(was_uploaded=True, checksum=local_digest)

    def delete(
        self,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Delete this node on the backend.

        Args:
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.
            request_context (RequestContext, optional): Request-level context passed through
                to the mutation. When omitted, the client's request context is used.
            priority (Priority, optional): Per-request priority emitted as the X-Priority header,
                overriding the client default for this request only.

        """
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
            priority=priority,
        )

    def save(
        self,
        allow_upsert: bool = False,
        update_group_context: bool | None = None,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Persist this node to the backend, creating or updating it as appropriate.

        New nodes are created (or upserted when ``allow_upsert`` is set), and existing
        nodes are updated with only the modified fields. After a successful save, the
        node is added to the client store and, when applicable, to the active group
        context for tracking.

        Args:
            allow_upsert (bool, optional): When ``True``, an existing node is upserted
                instead of failing with a duplicate. Defaults to ``False``.
            update_group_context (bool, optional): Whether to update the group context
                with this node. When ``None`` and the client is in tracking mode, defaults
                to ``True``.
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.
            request_context (RequestContext, optional): Request-level context passed through
                to the mutation. When omitted, the client's request context is used.
            priority (Priority, optional): Per-request priority emitted as the X-Priority header,
                overriding the client default for this request only.

        """
        if self._existing is False or allow_upsert is True:
            self.create(allow_upsert=allow_upsert, timeout=timeout, request_context=request_context, priority=priority)
        else:
            self.update(timeout=timeout, request_context=request_context, priority=priority)

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

    def _process_hierarchical_fields(
        self,
        data: dict[str, Any],
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        prefetch_relationships: bool = False,
        insert_alias: bool = False,
        property: bool = False,
    ) -> None:
        """Process hierarchical fields (parent, children, ancestors, descendants) for hierarchical nodes."""
        if not self._hierarchy_support:
            return

        for hierarchical_name in ["parent", "children", "ancestors", "descendants"]:
            if exclude and hierarchical_name in exclude:
                continue

            # Only include if explicitly requested or if prefetch_relationships is True
            should_fetch = prefetch_relationships or (include is not None and hierarchical_name in include)
            if not should_fetch:
                continue

            peer_schema = self._client.schema.get(kind=self._schema.hierarchy, branch=self._branch)  # type: ignore[union-attr, arg-type]
            peer_node = InfrahubNodeSync(client=self._client, schema=peer_schema, branch=self._branch)
            # Exclude hierarchical fields from peer data to prevent infinite recursion
            peer_exclude = list(exclude) if exclude else []
            peer_exclude.extend(["parent", "children", "ancestors", "descendants"])
            peer_data = peer_node.generate_query_data_node(
                exclude=peer_exclude,
                property=property,
            )

            # Parent is cardinality one, others are cardinality many
            if hierarchical_name == "parent":
                hierarchical_data = RelatedNodeSync._generate_query_data(peer_data=peer_data, property=property)
                # Use fragment for hierarchical fields similar to hierarchy relationships
                data_node = hierarchical_data["node"]
                hierarchical_data["node"] = {}
                hierarchical_data["node"][f"...on {self._schema.hierarchy}"] = data_node  # type: ignore[union-attr]
            else:
                hierarchical_data = RelationshipManagerSync._generate_query_data(peer_data=peer_data, property=property)
                # Use fragment for hierarchical fields similar to hierarchy relationships
                data_node = hierarchical_data["edges"]["node"]
                hierarchical_data["edges"]["node"] = {}
                hierarchical_data["edges"]["node"][f"...on {self._schema.hierarchy}"] = data_node  # type: ignore[union-attr]

            data[hierarchical_name] = hierarchical_data

            if insert_alias:
                data[hierarchical_name]["@alias"] = f"__alias__{self._schema.kind}__{hierarchical_name}"

    def generate_query_data(
        self,
        filters: dict[str, Any] | None = None,
        offset: int | str | None = None,
        limit: int | str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        partial_match: bool = False,
        property: bool = False,
        order: Order | None = None,
        include_metadata: bool = False,
    ) -> dict[str, Any | dict]:
        """Generate the full GraphQL query payload for this node kind.

        The returned dict combines :meth:`generate_query_data_init` with
        :meth:`generate_query_data_node`. When the node is a generic and ``fragment`` is
        ``True``, ``...on Kind`` fragments are added for every implementing kind so the
        relevant attributes are returned alongside the generic fields.

        Args:
            filters (dict[str, Any], optional): Filters to apply to the query.
            offset (int | str, optional): Pagination offset, either a literal value or a
                GraphQL variable placeholder such as ``"$offset"``.
            limit (int | str, optional): Pagination limit, either a literal value or a
                GraphQL variable placeholder such as ``"$limit"``.
            include (list[str], optional): Attributes or relationships to include.
            exclude (list[str], optional): Attributes or relationships to exclude.
            fragment (bool, optional): When ``True`` and the schema is a generic, emit
                ``...on Kind`` fragments for each implementing kind. Defaults to ``False``.
            prefetch_relationships (bool, optional): When ``True``, pre-fetch related node
                data instead of returning only their identifiers. Defaults to ``False``.
            partial_match (bool, optional): When ``True``, allow partial matches on filter
                criteria. Defaults to ``False``.
            property (bool, optional): When ``True``, include attribute and relationship
                properties (``source``, ``owner``, ``is_protected``, ...). Defaults to ``False``.
            order (Order, optional): Ordering options to apply to the query.
            include_metadata (bool, optional): When ``True``, include ``node_metadata`` and
                ``relationship_metadata`` in the result. Defaults to ``False``.

        Returns:
            dict[str, Any | dict]: A query payload keyed by the node kind, ready to be
            rendered as GraphQL.

        """
        data = self.generate_query_data_init(
            filters=filters,
            offset=offset,
            limit=limit,
            include=include,
            exclude=exclude,
            partial_match=partial_match,
            order=order,
            include_metadata=include_metadata,
        )
        data["edges"]["node"].update(
            self.generate_query_data_node(
                include=include,
                exclude=exclude,
                prefetch_relationships=prefetch_relationships,
                inherited=True,
                property=property,
                include_metadata=include_metadata,
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
                    include_metadata=include_metadata,
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
        include_metadata: bool = False,
    ) -> dict[str, Any | dict]:
        """Generate the node part of a GraphQL Query with attributes and nodes.

        Args:
            include (Optional[list[str]], optional): List of attributes or relationships to include. Defaults to None.
            exclude (Optional[list[str]], optional): List of attributes or relationships to exclude. Defaults to None.
            inherited (bool, optional): Indicated of the attributes and the relationships inherited from generics should be included as well.
                                        Defaults to True.
            insert_alias (bool, optional): If True, inserts aliases in the query for each attribute or relationship.
            prefetch_relationships (bool, optional): If True, pre-fetches relationship data as part of the query.
            include_metadata (bool, optional): If True, includes node_metadata and relationship_metadata in the query.

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

            attr_data = attr._generate_query_data(property=property, include_metadata=include_metadata)
            if attr_data:
                data[attr_name] = attr_data
                if insert_alias:
                    data[attr_name]["@alias"] = f"__alias__{self._schema.kind}__{attr_name}"
            elif insert_alias:
                data[attr_name] = {"@alias": f"__alias__{self._schema.kind}__{attr_name}"}

        for rel_name in self._relationships:
            if exclude and rel_name in exclude:
                continue

            rel_schema = self._schema.get_relationship(name=rel_name)

            if not rel_schema or (not inherited and rel_schema.inherited):
                continue

            if (
                rel_schema.cardinality == RelationshipCardinality.MANY  # type: ignore[union-attr]
                and rel_schema.kind not in {RelationshipKind.ATTRIBUTE, RelationshipKind.PARENT}  # type: ignore[union-attr]
                and not (include and rel_name in include)
            ):
                continue

            peer_data: dict[str, Any] = {}
            should_fetch_relationship = prefetch_relationships or (include is not None and rel_name in include)
            if rel_schema and should_fetch_relationship:
                peer_schema = self._client.schema.get(kind=rel_schema.peer, branch=self._branch)
                peer_node = InfrahubNodeSync(client=self._client, schema=peer_schema, branch=self._branch)
                peer_data = peer_node.generate_query_data_node(
                    property=property,
                    include_metadata=include_metadata,
                )

            rel_data = self._build_rel_query_data(rel_schema, peer_data, property, include_metadata)
            if rel_data is None:
                continue

            data[rel_name] = rel_data

            if insert_alias:
                data[rel_name]["@alias"] = f"__alias__{self._schema.kind}__{rel_name}"

        # Add parent, children, ancestors and descendants for hierarchical nodes
        self._process_hierarchical_fields(
            data=data,
            include=include,
            exclude=exclude,
            prefetch_relationships=prefetch_relationships,
            insert_alias=insert_alias,
            property=property,
        )

        return data

    def add_relationships(
        self,
        relation_to_update: str,
        related_nodes: list[str],
    ) -> None:
        """Add peers to a cardinality-many relationship through a dedicated mutation.

        Unlike :meth:`save`, this method targets a single relationship and only adds
        peers, leaving every other field untouched.

        Args:
            relation_to_update (str): The name of the relationship to update.
            related_nodes (list[str]): The IDs of the peers to add.

        """
        query = self._relationship_mutation(
            action="Add", relation_to_update=relation_to_update, related_nodes=related_nodes
        )
        tracker = f"mutation-{str(self._schema.kind).lower()}-relationshipadd-{relation_to_update}"
        self._client.execute_graphql(query=query, branch_name=self._branch, tracker=tracker)

    def remove_relationships(self, relation_to_update: str, related_nodes: list[str]) -> None:
        """Remove peers from a cardinality-many relationship through a dedicated mutation.

        Unlike :meth:`save`, this method targets a single relationship and only removes
        the listed peers, leaving every other field untouched.

        Args:
            relation_to_update (str): The name of the relationship to update.
            related_nodes (list[str]): The IDs of the peers to remove.

        """
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
        self,
        mutation_name: str,
        response: dict[str, Any],
        timeout: int | None = None,
        priority: Priority | None = None,
    ) -> None:
        object_response: dict[str, Any] = response[mutation_name]["object"]
        self.id = object_response["id"]
        self._existing = True

        for attr_name in self._attributes:
            attr = getattr(self, attr_name)
            if attr_name not in object_response or not attr.is_from_pool_attribute():
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
            related_node.fetch(timeout=timeout, priority=priority)
            setattr(self, rel_name, related_node)

    def create(
        self,
        allow_upsert: bool = False,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Create this node on the backend.

        For nodes inheriting from ``CoreFileObject``, the file content set with
        :meth:`upload_from_path` or :meth:`upload_from_bytes` is uploaded as part of the
        mutation and cleared from the node afterward.

        Prefer :meth:`save` over calling ``create()`` directly so existing-vs-new logic
        is handled for you.

        Args:
            allow_upsert (bool, optional): When ``True``, the operation upserts instead of
                erroring on a duplicate. Defaults to ``False``.
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.
            request_context (RequestContext, optional): Request-level context passed through
                to the mutation. When omitted, the client's request context is used.
            priority (Priority, optional): Per-request priority emitted as the X-Priority header,
                overriding the client default for this request only.

        Raises:
            ValueError: If this is a file-object node and no file content has been set.

        """
        self._validate_upsert(allow_upsert=allow_upsert)

        if self._file_object_support and self._file_content is None:
            raise ValueError(
                f"Cannot create {self._schema.kind} without file content. Use upload_from_path() or upload_from_bytes() to provide "
                "file content before saving."
            )

        mutation_query = self._generate_mutation_query()

        # Upserting means we may want to create, meaning payload contains all mandatory fields required for a creation,
        # so hfid is just redundant information. Currently, upsert mutation has performance overhead if `hfid` is filled.
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

        if "file" in input_data["mutation_variables"]:
            prepared = self._get_file_for_upload_sync()
            try:
                response = self._client._execute_graphql_with_file(
                    query=query.render(),
                    variables=input_data["variables"],
                    file_content=prepared.file_object,
                    file_name=prepared.filename,
                    branch_name=self._branch,
                    tracker=tracker,
                    timeout=timeout,
                    priority=priority,
                )
            finally:
                if prepared.should_close and prepared.file_object:
                    prepared.file_object.close()
            # Clear the file content after successful upload
            self.clear_file()
        else:
            response = self._client.execute_graphql(
                query=query.render(),
                branch_name=self._branch,
                tracker=tracker,
                variables=input_data["variables"],
                timeout=timeout,
                priority=priority,
            )
        self._process_mutation_result(
            mutation_name=mutation_name, response=response, timeout=timeout, priority=priority
        )

    def update(
        self,
        do_full_update: bool = False,
        timeout: int | None = None,
        request_context: RequestContext | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Update this node on the backend.

        By default only the modified attributes and relationships are sent so the server
        can compute a minimal diff. Setting ``do_full_update`` re-sends every field even
        when unchanged, which is useful when forcing relationship reconciliation.

        Prefer :meth:`save` over calling ``update()`` directly so existing-vs-new logic
        is handled for you.

        Args:
            do_full_update (bool, optional): When ``True``, send every field even when
                unmodified. Defaults to ``False``.
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.
            request_context (RequestContext, optional): Request-level context passed through
                to the mutation. When omitted, the client's request context is used.
            priority (Priority, optional): Per-request priority emitted as the X-Priority header,
                overriding the client default for this request only.

        """
        input_data = self._generate_input_data(exclude_unmodified=not do_full_update, request_context=request_context)
        mutation_query = self._generate_mutation_query()
        mutation_name = f"{self._schema.kind}Update"
        tracker = f"mutation-{str(self._schema.kind).lower()}-update"

        query = Mutation(
            mutation=mutation_name,
            input_data=input_data["data"],
            query=mutation_query,
            variables=input_data["mutation_variables"],
        )

        if "file" in input_data["mutation_variables"]:
            prepared = self._get_file_for_upload_sync()
            try:
                response = self._client._execute_graphql_with_file(
                    query=query.render(),
                    variables=input_data["variables"],
                    file_content=prepared.file_object,
                    file_name=prepared.filename,
                    branch_name=self._branch,
                    tracker=tracker,
                    timeout=timeout,
                    priority=priority,
                )
            finally:
                if prepared.should_close and prepared.file_object:
                    prepared.file_object.close()
            # Clear the file content after successful upload
            self.clear_file()
        else:
            response = self._client.execute_graphql(
                query=query.render(),
                branch_name=self._branch,
                tracker=tracker,
                variables=input_data["variables"],
                timeout=timeout,
                priority=priority,
            )
        self._process_mutation_result(
            mutation_name=mutation_name, response=response, timeout=timeout, priority=priority
        )

    def _process_relationships(
        self,
        node_data: dict[str, Any],
        branch: str,
        related_nodes: list[InfrahubNodeSync],
        timeout: int | None = None,
        recursive: bool = False,
    ) -> None:
        """Processes the Relationships of a InfrahubNodeSync and add Related Nodes to a list.

        Args:
            node_data (dict[str, Any]): The item from the GraphQL response corresponding to the node.
            branch (str): The branch name.
            related_nodes (list[InfrahubNodeSync]): The list to which related nodes will be appended.
            timeout (int, optional): Overrides default timeout used when querying the graphql API. Specified in seconds.
            recursive:(bool): Whether to recursively process relationships of related nodes.

        """
        for rel_name in self._relationships:
            rel = getattr(self, rel_name)
            if rel and isinstance(rel, RelatedNodeSync):
                relation = node_data["node"].get(rel_name, None)
                if relation and relation.get("node", None):
                    related_node = InfrahubNodeSync.from_graphql(
                        client=self._client,
                        branch=branch,
                        data=relation,
                        timeout=timeout,
                    )
                    related_nodes.append(related_node)
                    if recursive:
                        related_node._process_relationships(
                            node_data=relation,
                            branch=branch,
                            related_nodes=related_nodes,
                            recursive=recursive,
                        )
            elif rel and isinstance(rel, RelationshipManagerSync):
                peers = node_data["node"].get(rel_name, None)
                if peers and peers["edges"]:
                    for peer in peers["edges"]:
                        related_node = InfrahubNodeSync.from_graphql(
                            client=self._client,
                            branch=branch,
                            data=peer,
                            timeout=timeout,
                        )
                        related_nodes.append(related_node)
                        if recursive:
                            related_node._process_relationships(
                                node_data=peer,
                                branch=branch,
                                related_nodes=related_nodes,
                                recursive=recursive,
                            )

    def get_pool_allocated_resources(self, resource: InfrahubNodeSync) -> list[InfrahubNodeSync]:
        """Fetch all nodes that were allocated for the pool and a given resource.

        Args:
            resource (InfrahubNodeSync): The resource from which the nodes were allocated.

        Returns:
            list[InfrahubNodeSync]: The allocated nodes.

        Raises:
            ValueError: If the node is not a resource pool.

        """
        if not self.is_resource_pool():
            raise ValueError("Allocated resources can only be fetched from resource pool nodes.")

        graphql_query_name = "InfrahubResourcePoolAllocated"
        node_ids_per_kind: dict[str, list[str]] = {}

        query = Query(
            query={
                graphql_query_name: {
                    "@filters": {
                        "pool_id": "$pool_id",
                        "resource_id": "$resource_id",
                        "offset": "$offset",
                        "limit": "$limit",
                    },
                    "count": None,
                    "edges": {"node": {"id": None, "kind": None, "branch": None, "identifier": None}},
                }
            },
            name="GetAllocatedResourceForPool",
            variables={"pool_id": str, "resource_id": str, "offset": int, "limit": int},
        )
        query_str = query.render()

        has_remaining_items = True
        page_number = 1
        while has_remaining_items:
            page_offset = (page_number - 1) * self._client.pagination_size

            response = self._client.execute_graphql(
                query=query_str,
                variables={
                    "pool_id": self.id,
                    "resource_id": resource.id,
                    "offset": page_offset,
                    "limit": self._client.pagination_size,
                },
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

        Raises:
            ValueError: If the node is not a resource pool.

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

    def _get_relationship_many(self, name: str) -> RelationshipManagerSync:
        if name in self._relationship_cardinality_many_data:
            return self._relationship_cardinality_many_data[name]

        raise ResourceNotDefinedError(message=f"The node doesn't have a cardinality=many relationship for {name}")

    def _get_relationship_one(self, name: str) -> RelatedNodeSync:
        if name in self._relationship_cardinality_one_data:
            return self._relationship_cardinality_one_data[name]

        raise ResourceNotDefinedError(message=f"The node doesn't have a cardinality=one relationship for {name}")

    def get_flat_value(self, key: str, separator: str = "__") -> Any:
        """Resolve a value addressed by a flat key over this node and its related nodes.

        Walks attributes on this node, descending through cardinality-one relationships
        (which are fetched on demand) until the final component is reached. Each
        relationship hop incurs a backend call, so this is intended for ad-hoc lookups
        rather than bulk traversal.

        Args:
            key (str): The flat key to resolve (for example ``"name__value"`` or
                ``"site__name__value"``).
            separator (str, optional): Component separator in ``key``. Defaults to ``"__"``.

        Returns:
            Any: The resolved value.

        Raises:
            ValueError: If a component does not match an attribute or relationship, or if
                a relationship hop targets a non cardinality-one relationship.

        Examples:
            name__value
            module.object.value

        """
        if separator not in key:
            return getattr(self, key)

        first, remaining = key.split(separator, maxsplit=1)

        if first in self._schema.attribute_names:
            attr = getattr(self, first)
            for part in remaining.split(separator):
                attr = getattr(attr, part)
            return attr

        try:
            rel = self._schema.get_relationship(name=first)
        except ValueError as exc:
            raise ValueError(f"No attribute or relationship named '{first}' for '{self._schema.kind}'") from exc

        if rel.cardinality != RelationshipCardinality.ONE:
            raise ValueError(
                f"Can only look up flat value for relationships of cardinality {RelationshipCardinality.ONE.value}"
            )

        related_node: RelatedNodeSync = getattr(self, first)
        related_node.fetch()
        return related_node.peer.get_flat_value(key=remaining, separator=separator)

    def extract(self, params: dict[str, str]) -> dict[str, Any]:
        """Extract several values addressed by flat keys into a labeled dict.

        Each value in ``params`` is resolved with :meth:`get_flat_value`, and the
        corresponding key is preserved as the output label.

        Args:
            params (dict[str, str]): A mapping of output label to flat key to resolve.

        Returns:
            dict[str, Any]: The resolved values keyed by their output label.

        """
        result: dict[str, Any] = {}
        for key, value in params.items():
            result[key] = self.get_flat_value(key=value)

        return result

    def __dir__(self) -> Iterable[str]:
        base = list(super().__dir__())
        return sorted(
            base
            + list(self._attribute_data.keys())
            + list(self._relationship_cardinality_many_data.keys())
            + list(self._relationship_cardinality_one_data.keys())
        )
