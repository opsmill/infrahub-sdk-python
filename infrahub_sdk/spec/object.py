from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ..yaml import InfrahubFile, InfrahubFileKind

if TYPE_CHECKING:
    from ..client import InfrahubClient
    from ..schema import MainSchemaTypesAPI


class InfrahubObjectFileData(BaseModel):
    kind: str
    data: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def enrich_node(cls, data: dict, context: dict) -> dict:  # noqa: ARG003
        return data

    @classmethod
    async def create_node(
        cls,
        client: InfrahubClient,
        schema: MainSchemaTypesAPI,
        data: dict,
        context: dict | None = None,
        branch: str | None = None,
        default_schema_kind: str | None = None,
    ) -> None:
        # First validate of all mandatory fields are present
        for element in schema.mandatory_attribute_names + schema.mandatory_relationship_names:
            if element not in data.keys():
                raise ValueError(f"{element} is mandatory")

        clean_data: dict[str, Any] = {}

        remaining_rels = []
        for key, value in data.items():
            if key in schema.attribute_names:
                clean_data[key] = value

            if key in schema.relationship_names:
                rel_schema = schema.get_relationship(name=key)

                if isinstance(value, dict) and "data" not in value:
                    raise ValueError(f"Relationship {key} must be a dict with 'data'")

                # This is a simple implementation for now, need to revisit once we have the integration tests
                if isinstance(value, (list)):
                    clean_data[key] = value
                elif rel_schema.cardinality == "one" and isinstance(value, str):
                    clean_data[key] = [value]
                else:
                    remaining_rels.append(key)

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
            # identify what is the name of the relationship on the other side
            if not isinstance(data[rel], dict) and "data" in data[rel]:
                raise ValueError(f"relationship {rel} must be a dict with 'data'")

            rel_schema = schema.get_relationship(name=rel)
            peer_kind = data[rel].get("kind", default_schema_kind) or rel_schema.peer
            peer_schema = await client.schema.get(kind=peer_kind, branch=branch)

            if rel_schema.identifier is None:
                raise ValueError("identifier must be defined")

            peer_rel = peer_schema.get_matching_relationship(id=rel_schema.identifier, direction=rel_schema.direction)

            rel_data = data[rel]["data"]
            context = {}
            if peer_rel:
                context[peer_rel.name] = node.id

            if rel_schema.cardinality == "one" and isinstance(rel_data, dict):
                await cls.create_node(
                    client=client,
                    schema=peer_schema,
                    data=rel_data,
                    context=context,
                    branch=branch,
                    default_schema_kind=default_schema_kind,
                )

            elif rel_schema.cardinality == "many" and isinstance(rel_data, list):
                for idx, peer_data in enumerate(rel_data):
                    context["list_index"] = idx
                    await cls.create_node(
                        client=client,
                        schema=peer_schema,
                        data=peer_data,
                        context=context,
                        branch=branch,
                        default_schema_kind=default_schema_kind,
                    )
            else:
                raise ValueError(
                    f"Relationship {rel_schema.name} doesn't have the right format {rel_schema.cardinality} / {type(rel_data)}"
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
