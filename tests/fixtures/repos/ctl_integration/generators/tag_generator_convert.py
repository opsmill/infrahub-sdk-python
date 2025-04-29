from infrahub_sdk.generator import InfrahubGenerator


class Generator(InfrahubGenerator):
    async def generate(self, data: dict) -> None:
        response_person = data["TestingPerson"]["edges"][0]["node"]
        name: str = response_person["name"]["value"]
        person = self.store.get(key=name, kind="TestingPerson")

        for animal in person.animals.peers:
            payload = {
                "name": f"converted-{name.lower().replace(' ', '-')}-{animal.peer.name.value.lower()}",
                "description": "Using convert_query_response",
            }
            obj = await self.client.create(kind="BuiltinTag", data=payload)
            await obj.save(allow_upsert=True)
