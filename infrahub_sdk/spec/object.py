from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ..exceptions import ObjectValidationError, ValidationError
from ..schema import RelationshipSchema
from ..yaml import InfrahubFile, InfrahubFileKind

if TYPE_CHECKING:
    from ..client import InfrahubClient
    from ..node import InfrahubNode
    from ..schema import MainSchemaTypesAPI, RelationshipSchema


def validate_list_of_scalars(value: list[Any]) -> bool:
    return all(isinstance(item, (str, int, float, bool)) for item in value)


def validate_list_of_hfids(value: list[Any]) -> bool:
    return all(isinstance(item, (str, list)) for item in value)


def validate_list_of_data_dicts(value: list[Any]) -> bool:
    return all(isinstance(item, dict) and "data" in item for item in value)


def validate_list_of_objects(value: list[Any]) -> bool:
    return all(isinstance(item, dict) for item in value)


class RelationshipDataFormat(str, Enum):
    UNKNOWN = "unknown"

    ONE_REF = "one_ref"
    ONE_OBJ = "one_obj"

    MANY_OBJ_DICT_LIST = "many_obj_dict_list"
    MANY_OBJ_LIST_DICT = "many_obj_list_dict"
    MANY_REF = "many_ref_list"


class RelationshipInfo(BaseModel):
    name: str
    rel_schema: RelationshipSchema
    peer_kind: str
    peer_rel: RelationshipSchema | None = None
    reason_relationship_not_valid: str | None = None
    format: RelationshipDataFormat = RelationshipDataFormat.UNKNOWN

    @property
    def is_bidirectional(self) -> bool:
        """Indicate if a relationship with the same identifier exists on the other side"""
        return bool(self.peer_rel)

    @property
    def is_mandatory(self) -> bool:
        if not self.peer_rel:
            return False
        return not self.peer_rel.optional

    @property
    def is_valid(self) -> bool:
        return not self.reason_relationship_not_valid

    @property
    def is_reference(self) -> bool:
        return self.format in [RelationshipDataFormat.ONE_REF, RelationshipDataFormat.MANY_REF]


async def get_relationship_info(
    client: InfrahubClient, schema: MainSchemaTypesAPI, name: str, value: Any, branch: str | None = None
) -> RelationshipInfo:
    """
    Get the relationship info for a given relationship name.
    """
    rel_schema = schema.get_relationship(name=name)

    info = RelationshipInfo(name=name, peer_kind=rel_schema.peer, rel_schema=rel_schema)

    if isinstance(value, dict) and "data" not in value:
        info.reason_relationship_not_valid = f"Relationship {name} must be a dict with 'data'"
        return info

    if isinstance(value, dict) and "kind" in value:
        info.peer_kind = value["kind"]

    peer_schema = await client.schema.get(kind=info.peer_kind, branch=branch)

    try:
        info.peer_rel = peer_schema.get_matching_relationship(
            id=rel_schema.identifier or "", direction=rel_schema.direction
        )
    except ValueError:
        pass

    if rel_schema.cardinality == "one" and isinstance(value, list):
        # validate the list is composed of string
        if validate_list_of_scalars(value):
            info.format = RelationshipDataFormat.ONE_REF
        else:
            info.reason_relationship_not_valid = "Too many objects provided for a relationship of cardinality one"

    elif rel_schema.cardinality == "one" and isinstance(value, str):
        info.format = RelationshipDataFormat.ONE_REF

    elif rel_schema.cardinality == "one" and isinstance(value, dict) and "data" in value:
        info.format = RelationshipDataFormat.ONE_OBJ

    elif (
        rel_schema.cardinality == "many"
        and isinstance(value, dict)
        and "data" in value
        and validate_list_of_objects(value["data"])
    ):
        # Initial format, we need to support it for backward compatibility for menu
        # it's helpful if there is only one type of object to manage
        info.format = RelationshipDataFormat.MANY_OBJ_DICT_LIST

    elif rel_schema.cardinality == "many" and isinstance(value, dict) and "data" not in value:
        info.reason_relationship_not_valid = "Invalid structure for a relationship of cardinality many,"
        " either provide a dict with data as a list or a list of objects"

    elif rel_schema.cardinality == "many" and isinstance(value, list):
        if validate_list_of_data_dicts(value):
            info.format = RelationshipDataFormat.MANY_OBJ_LIST_DICT
        elif validate_list_of_hfids(value):
            info.format = RelationshipDataFormat.MANY_REF
        else:
            info.reason_relationship_not_valid = "Invalid structure for a relationship of cardinality many,"
            " either provide a list of dict with data or a list of hfids"

    return info


class InfrahubObjectFileData(BaseModel):
    kind: str
    data: list[dict[str, Any]] = Field(default_factory=list)

    async def validate_format(self, client: InfrahubClient, branch: str | None = None) -> list[ObjectValidationError]:
        errors: list[ObjectValidationError] = []
        schema = await client.schema.get(kind=self.kind, branch=branch)
        for idx, item in enumerate(self.data):
            errors.extend(
                await self.validate_object(client=client, position=[idx + 1], schema=schema, data=item, branch=branch)
            )
        return errors

    async def process(self, client: InfrahubClient, branch: str | None = None) -> None:
        schema = await client.schema.get(kind=self.kind, branch=branch)
        for idx, item in enumerate(self.data):
            await self.create_node(client=client, schema=schema, data=item, position=[idx + 1], branch=branch)

    @classmethod
    async def validate_object(
        cls,
        client: InfrahubClient,
        schema: MainSchemaTypesAPI,
        data: dict,
        position: list[int | str],
        context: dict | None = None,
        branch: str | None = None,
    ) -> list[ObjectValidationError]:
        errors: list[ObjectValidationError] = []
        context = context or {}

        # First validate if all mandatory fields are present
        for element in schema.mandatory_input_names:
            if not any([element in data.keys(), element in context.keys()]):
                errors.append(ObjectValidationError(position=position + [element], message=f"{element} is mandatory"))

        # Validate if all attributes are valid
        for key, value in data.items():
            if key not in schema.attribute_names and key not in schema.relationship_names:
                errors.append(
                    ObjectValidationError(
                        position=position + [key],
                        message=f"{key} is not a valid attribute or relationship for {schema.kind}",
                    )
                )

            if key in schema.attribute_names:
                if not isinstance(value, (str, int, float, bool, list, dict)):
                    errors.append(
                        ObjectValidationError(
                            position=position + [key],
                            message=f"{key} must be a string, int, float, bool, list, or dict",
                        )
                    )

            if key in schema.relationship_names:
                rel_info = await get_relationship_info(
                    client=client, schema=schema, name=key, value=value, branch=branch
                )
                if not rel_info.is_valid:
                    errors.append(
                        ObjectValidationError(
                            position=position + [key],
                            message=rel_info.reason_relationship_not_valid or "Invalid relationship",
                        )
                    )

                # If there is a peer relationship, we add a placeholder for the related node
                if rel_info.peer_rel and rel_info.is_mandatory and rel_info.peer_rel.cardinality == "one":
                    context[rel_info.peer_rel.name] = "placeholder"
                elif rel_info.peer_rel and rel_info.is_mandatory and rel_info.peer_rel.cardinality == "many":
                    context[rel_info.peer_rel.name] = ["placeholder"]

                errors.extend(
                    await cls.validate_related_nodes(
                        client=client,
                        position=position + [key],
                        rel_info=rel_info,
                        data=value,
                        context=context,
                        branch=branch,
                    )
                )

        return errors

    @classmethod
    async def validate_related_nodes(
        cls,
        client: InfrahubClient,
        position: list[int | str],
        rel_info: RelationshipInfo,
        data: dict | list[dict],
        context: dict | None = None,
        branch: str | None = None,
    ) -> list[ObjectValidationError]:
        context = context or {}
        errors: list[ObjectValidationError] = []

        if isinstance(data, (list, str)) and rel_info.format == RelationshipDataFormat.ONE_REF:
            return errors

        if isinstance(data, list) and rel_info.format == RelationshipDataFormat.MANY_REF:
            return errors

        if isinstance(data, dict) and rel_info.format == RelationshipDataFormat.ONE_OBJ:
            peer_kind = data.get("kind") or rel_info.peer_kind
            peer_schema = await client.schema.get(kind=peer_kind, branch=branch)
            errors.extend(
                await cls.validate_object(
                    client=client,
                    position=position,
                    schema=peer_schema,
                    data=data["data"],
                    context=context,
                    branch=branch,
                )
            )
            return errors

        if isinstance(data, dict) and rel_info.format == RelationshipDataFormat.MANY_OBJ_DICT_LIST:
            peer_kind = data.get("kind") or rel_info.peer_kind
            peer_schema = await client.schema.get(kind=peer_kind, branch=branch)

            for idx, peer_data in enumerate(data["data"]):
                context["list_index"] = idx
                errors.extend(
                    await cls.validate_object(
                        client=client,
                        position=position + [idx + 1],
                        schema=peer_schema,
                        data=peer_data,
                        context=context,
                        branch=branch,
                    )
                )
            return errors

        if isinstance(data, list) and rel_info.format == RelationshipDataFormat.MANY_OBJ_LIST_DICT:
            for idx, item in enumerate(data):
                context["list_index"] = idx
                peer_kind = item.get("kind") or rel_info.peer_kind
                peer_schema = await client.schema.get(kind=peer_kind, branch=branch)
                errors.extend(
                    await cls.validate_object(
                        client=client,
                        position=position + [idx + 1],
                        schema=peer_schema,
                        data=item["data"],
                        context=context,
                        branch=branch,
                    )
                )
            return errors

        errors.append(
            ObjectValidationError(
                position=position,
                message=f"Relationship {rel_info.rel_schema.name} doesn't have the right format {rel_info.rel_schema.cardinality} / {type(data)}",
            )
        )
        return errors

    @classmethod
    def enrich_node(cls, data: dict, context: dict) -> dict:  # noqa: ARG003
        return data

    @classmethod
    async def create_node(
        cls,
        client: InfrahubClient,
        schema: MainSchemaTypesAPI,
        data: dict,
        position: list[int | str],
        context: dict | None = None,
        branch: str | None = None,
        default_schema_kind: str | None = None,
    ) -> InfrahubNode:
        context = context or {}

        errors = await cls.validate_object(
            client=client, position=position, schema=schema, data=data, context=context, branch=branch
        )
        if errors:
            raise ObjectValidationError(position=position, message="Object is not valid")

        clean_data: dict[str, Any] = {}

        # List of relationships that need to be processed after the current object has been created
        remaining_rels = []
        rels_info: dict[str, RelationshipInfo] = {}

        for key, value in data.items():
            if key in schema.attribute_names:
                clean_data[key] = value
                continue

            if key in schema.relationship_names:
                rel_info = await get_relationship_info(
                    client=client, schema=schema, name=key, value=value, branch=branch
                )
                rels_info[key] = rel_info

                if not rel_info.is_valid:
                    client.log.info(rel_info.reason_relationship_not_valid)
                    continue

                # We need to determine if the related object depend on this object or if this is the other way around.
                #  - if the relationship is bidirectional and is mandatory on the other side, then we need to create this object First
                #  - if the relationship is bidirectional and is not mandatory on the other side, then we need should create the related object First
                #  - if the relationship is not bidirectional, then we need to create the related object First
                if rel_info.is_reference and isinstance(value, list):
                    clean_data[key] = value
                elif rel_info.format == RelationshipDataFormat.ONE_REF and isinstance(value, str):
                    clean_data[key] = [value]
                elif not rel_info.is_reference and rel_info.is_bidirectional and rel_info.is_mandatory:
                    remaining_rels.append(key)
                elif not rel_info.is_reference and not rel_info.is_mandatory:
                    if rel_info.format == RelationshipDataFormat.ONE_OBJ:
                        nodes = await cls.create_related_nodes(
                            client=client,
                            position=position,
                            rel_info=rel_info,
                            data=value,
                            branch=branch,
                            default_schema_kind=default_schema_kind,
                        )
                        clean_data[key] = nodes[0]

                    else:
                        nodes = await cls.create_related_nodes(
                            client=client,
                            position=position,
                            rel_info=rel_info,
                            data=value,
                            branch=branch,
                            default_schema_kind=default_schema_kind,
                        )
                        clean_data[key] = nodes

                else:
                    raise ValueError(f"Situation unaccounted for: {rel_info}")

        if context:
            clean_context = {
                ckey: cvalue
                for ckey, cvalue in context.items()
                if ckey in schema.relationship_names + schema.attribute_names
            }
            clean_data.update(clean_context)

        clean_data = cls.enrich_node(data=clean_data, context=context or {})

        node = await client.create(kind=schema.kind, branch=branch, data=clean_data)
        await node.save(allow_upsert=True)

        display_label = node.get_human_friendly_id_as_string() or f"{node.get_kind()} : {node.id}"
        client.log.info(f"Node: {display_label}")

        for rel in remaining_rels:
            context = {}

            # If there is a peer relationship, we add the node id to the context
            rel_info = rels_info[rel]
            if rel_info.peer_rel:
                # TODO were making the assumption that the peer relationship is of cardinality one
                # we need to check that and not sure how we should handle
                context[rel_info.peer_rel.name] = node.id

            await cls.create_related_nodes(
                client=client,
                rel_info=rel_info,
                position=position,
                data=data[rel],
                context=context,
                branch=branch,
                default_schema_kind=default_schema_kind,
            )

        return node

    @classmethod
    async def create_related_nodes(
        cls,
        client: InfrahubClient,
        rel_info: RelationshipInfo,
        position: list[int | str],
        data: dict | list[dict],
        context: dict | None = None,
        branch: str | None = None,
        default_schema_kind: str | None = None,
    ) -> list[InfrahubNode]:
        nodes: list[InfrahubNode] = []
        context = context or {}

        if isinstance(data, dict) and rel_info.format == RelationshipDataFormat.ONE_OBJ:
            peer_kind = data.get("kind") or rel_info.peer_kind
            peer_schema = await client.schema.get(kind=peer_kind, branch=branch)

            node = await cls.create_node(
                client=client,
                schema=peer_schema,
                position=position,
                data=data["data"],
                context=context,
                branch=branch,
                default_schema_kind=default_schema_kind,
            )
            return [node]

        if isinstance(data, dict) and rel_info.format == RelationshipDataFormat.MANY_OBJ_DICT_LIST:
            peer_kind = data.get("kind") or rel_info.peer_kind
            peer_schema = await client.schema.get(kind=peer_kind, branch=branch)

            for idx, peer_data in enumerate(data["data"]):
                context["list_index"] = idx
                if isinstance(peer_data, dict):
                    node = await cls.create_node(
                        client=client,
                        schema=peer_schema,
                        position=position + [idx + 1],
                        data=peer_data,
                        context=context,
                        branch=branch,
                        default_schema_kind=default_schema_kind,
                    )
                    nodes.append(node)
            return nodes

        if isinstance(data, list) and rel_info.format == RelationshipDataFormat.MANY_OBJ_LIST_DICT:
            for idx, item in enumerate(data):
                context["list_index"] = idx

                peer_kind = item.get("kind") or rel_info.peer_kind
                peer_schema = await client.schema.get(kind=peer_kind, branch=branch)

                node = await cls.create_node(
                    client=client,
                    schema=peer_schema,
                    position=position + [idx + 1],
                    data=item["data"],
                    context=context,
                    branch=branch,
                    default_schema_kind=default_schema_kind,
                )
                nodes.append(node)

            return nodes

        raise ValueError(
            f"Relationship {rel_info.rel_schema.name} doesn't have the right format {rel_info.rel_schema.cardinality} / {type(data)}"
        )


class ObjectFile(InfrahubFile):
    _spec: InfrahubObjectFileData | None = None

    @property
    def spec(self) -> InfrahubObjectFileData:
        if not self._spec:
            self._spec = InfrahubObjectFileData(**self.data.spec)
        return self._spec

    def validate_content(self) -> None:
        super().validate_content()
        if self.kind != InfrahubFileKind.OBJECT:
            raise ValueError("File is not an Infrahub Object file")
        self._spec = InfrahubObjectFileData(**self.data.spec)

    async def validate_format(self, client: InfrahubClient, branch: str | None = None) -> None:
        self.validate_content()
        errors = await self.spec.validate_format(client=client, branch=branch)
        if errors:
            raise ValidationError(identifier=str(self.location), messages=[str(error) for error in errors])

    async def process(self, client: InfrahubClient, branch: str | None = None) -> None:
        await self.spec.process(client=client, branch=branch)
