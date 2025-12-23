from operator import itemgetter
from typing import Any

from infrahub_sdk.transforms import InfrahubTransform


class ConvertedAnimalPerson(InfrahubTransform):
    query = "animal_person"

    async def transform(self, data: dict[str, Any]) -> dict[str, Any]:
        response_person = data["TestingPerson"]["edges"][0]["node"]
        name: str = response_person["name"]["value"]
        person = self.store.get(key=name, kind="TestingPerson")

        animals = [{"type": animal.peer.typename, "name": animal.peer.name.value} for animal in person.animals.peers]
        animals.sort(key=itemgetter("name"))

        return {"person": person.name.value, "herd_size": len(animals), "animals": animals}
