from __future__ import annotations

from typing import TYPE_CHECKING, Any

import ujson

if TYPE_CHECKING:
    from typing import BinaryIO


class MultipartBuilder:
    """Builds multipart form data payloads for GraphQL file uploads.

    This class implements the GraphQL Multipart Request Spec for uploading files via GraphQL mutations. The spec defines a standard way to send files
    alongside GraphQL operations using multipart/form-data.

    The payload structure follows the spec:
    - operations: JSON containing the GraphQL query and variables
    - map: JSON mapping file keys to variable paths
    - 0, 1, ...: The actual file contents

    Example payload:
        {
            "operations": '{"query": "mutation($file: Upload!) {...}", "variables": {"file": null}}',
            "map": '{"0": ["variables.file"]}',
            "0": (filename, file_content)
        }
    """

    @staticmethod
    def build_operations(query: str, variables: dict[str, Any]) -> str:
        """Build the operations JSON string.

        Args:
            query: The GraphQL query string.
            variables: The variables dict (file variable should be null).

        Returns:
            JSON string containing the query and variables.
        """
        return ujson.dumps({"query": query, "variables": variables})

    @staticmethod
    def build_file_map(file_key: str = "0", variable_path: str = "variables.file") -> str:
        """Build the file map JSON string.

        Args:
            file_key: The key used for the file in the multipart payload.
            variable_path: The path to the file variable in the GraphQL variables.

        Returns:
            JSON string mapping the file key to the variable path.
        """
        return ujson.dumps({file_key: [variable_path]})

    @staticmethod
    def build_payload(
        query: str,
        variables: dict[str, Any],
        file_content: BinaryIO | None = None,
        file_name: str = "upload",
    ) -> dict[str, Any]:
        """Build the complete multipart form data payload.

        Constructs the payload according to the GraphQL Multipart Request Spec. The returned dict can be passed directly to httpx as the `files`
        parameter.

        Args:
            query: The GraphQL query string containing $file: Upload! variable.
            variables: The variables dict. The 'file' key will be set to null.
            file_content: The file content as a file-like object (BinaryIO).
                          If None, only the operations and map will be included.
            file_name: The filename to use for the upload.

        Returns:
            A dict suitable for httpx's `files` parameter in a POST request.

        Example:
            >>> builder = MultipartBuilder()
            >>> payload = builder.build_payload(
            ...     query="mutation($file: Upload!) { upload(file: $file) { id } }",
            ...     variables={"other": "value"},
            ...     file_content=open("file.pdf", "rb"),
            ...     file_name="document.pdf",
            ... )
            >>> # payload can be passed to httpx.post(..., files=payload)
        """
        # Ensure file variable is null (spec requirement)
        variables = {**variables, "file": None}

        operations = MultipartBuilder.build_operations(query=query, variables=variables)
        file_map = MultipartBuilder.build_file_map()

        files: dict[str, Any] = {"operations": (None, operations), "map": (None, file_map)}

        if file_content is not None:
            # httpx streams from file-like objects automatically
            files["0"] = (file_name, file_content)

        return files
