from __future__ import annotations


class NodeProperty:
    """Represents a property of a node, typically used for metadata like display labels.

    A ``NodeProperty`` is a lightweight pointer to another node, used to expose attribute and
    relationship metadata such as ``source``, ``owner``, ``created_by``, or ``updated_by``
    without loading the full peer node.

    Attributes:
        id (str | None): The identifier of the referenced node.
        display_label (str | None): A human-readable label for the referenced node.
        typename (str | None): The GraphQL ``__typename`` of the referenced node.

    """

    def __init__(self, data: dict | str) -> None:
        """Build a ``NodeProperty`` from raw GraphQL data.

        Args:
            data (dict | str): Either a node identifier as a string, or a dict with
                ``id``, ``display_label``, and ``__typename`` keys.

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

    def __repr__(self) -> str:
        return f"NodeProperty({{'id': {self.id!r}, 'display_label': {self.display_label!r}, '__typename': {self.typename!r}}})"

    def _generate_input_data(self) -> str | None:
        return self.id
