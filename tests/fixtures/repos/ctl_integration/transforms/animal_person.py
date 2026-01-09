from typing import Any

from infrahub_sdk.transforms import InfrahubTransform


class AnimalPerson(InfrahubTransform):
    query = "animal_person"

    async def transform(self, data: dict[str, Any]) -> dict[str, Any]:
        response_person = data["TestingPerson"]["edges"][0]["node"]
        name: str = response_person["name"]["value"]
        animal_names = sorted(
            animal["node"]["name"]["value"] for animal in data["TestingPerson"]["edges"][0]["node"]["animals"]["edges"]
        )

        return {"person": name, "pets": animal_names}
