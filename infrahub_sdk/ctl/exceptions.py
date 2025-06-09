class Error(Exception):
    """Infrahub CTL Base exception."""


class QueryNotFoundError(Error):
    """Exception raised when a GraphQL query is not found in the repository."""
    def __init__(self, name: str, message: str = ""):
        """
        Initializes QueryNotFoundError.

        Args:
            name: The name of the query that was not found.
            message: Optional custom message. If not provided, a default message is generated.
        """
        self.message = message or f"The requested query '{name}' was not found."
        super().__init__(self.message)
