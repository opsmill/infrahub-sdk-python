from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ADocContentGenMethod

if TYPE_CHECKING:
    from docs.docs_generation.content_gen_methods.mdx.mdx_code_doc import MdxFile


class FilePrintingDocContentGenMethod(ADocContentGenMethod):
    """Return the content of an already-generated file as-is.

    Args:
        file: The ``MdxFile`` whose content will be returned.

    """

    def __init__(self, file: MdxFile) -> None:
        self.file = file

    def apply(self) -> str:
        return self.file.content
