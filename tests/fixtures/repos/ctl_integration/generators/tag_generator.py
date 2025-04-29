from infrahub_sdk.generator import InfrahubGenerator


class Generator(InfrahubGenerator):
    async def generate(self, data: dict) -> None:
        response_person = data["TestingPerson"]["edges"][0]["node"]
        name: str = response_person["name"]["value"]

        for animal in data["TestingPerson"]["edges"][0]["node"]["animals"]["edges"]:
            payload = {
                "name": f"raw-{name.lower().replace(' ', '-')}-{animal['node']['name']['value'].lower()}",
                "description": "Without converting query response",
            }
            obj = await self.client.create(kind="BuiltinTag", data=payload)
            await obj.save(allow_upsert=True)
