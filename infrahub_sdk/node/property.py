from __future__ import annotations


class NodeProperty:
    """Represents a property of a node, typically used for metadata like display labels."""

    def __init__(self, data: dict | str):
        """
        Args:
            data (Union[dict, str]): Data representing the node property.
        """
        self.id = None
        self.display_label = None
        self.typename = None

        if isinstance(data, str):
            self.id = data
        elif isinstance(data, dict):
            self.id = data.get("id", None)
            self.display_label = data.get("display_label", None)
            self.typename = data.get("__typename", None)

    def _generate_input_data(self) -> str | None:
        return self.id
