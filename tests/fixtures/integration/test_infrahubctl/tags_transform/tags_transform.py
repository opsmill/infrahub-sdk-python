from typing import Any

from infrahub_sdk.transforms import InfrahubTransform


class TagsTransform(InfrahubTransform):
    query = "tags_query"
    url = "my-tags"

    async def transform(self, data: dict[str, Any]) -> dict[str, str]:
        tag = data["BuiltinTag"]["edges"][0]["node"]
        tag_name = tag["name"]["value"]
        tag_description = tag["description"]["value"]

        return {"tag_title": tag_name.title(), "bold_description": f"*{tag_description}*".upper()}
