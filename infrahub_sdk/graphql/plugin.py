from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from ariadne_codegen.plugins.base import Plugin

if TYPE_CHECKING:
    from graphql import ExecutableDefinitionNode


class FutureAnnotationPlugin(Plugin):
    @staticmethod
    def insert_future_annotation(module: ast.Module) -> ast.Module:
        # First check if the future annotation is already present
        for item in module.body:
            if isinstance(item, ast.ImportFrom) and item.module == "__future__":
                if any(alias.name == "annotations" for alias in item.names):
                    return module

        module.body.insert(0, ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0))
        return module

    def generate_result_types_module(
        self,
        module: ast.Module,
        operation_definition: ExecutableDefinitionNode,  # noqa: ARG002
    ) -> ast.Module:
        return self.insert_future_annotation(module)


class StandardTypeHintPlugin(Plugin):
    @classmethod
    def replace_list_in_subscript(cls, subscript: ast.Subscript) -> ast.Subscript:
        if isinstance(subscript.value, ast.Name) and subscript.value.id == "List":
            subscript.value.id = "list"
        if isinstance(subscript.slice, ast.Subscript):
            subscript.slice = cls.replace_list_in_subscript(subscript.slice)

        return subscript

    @classmethod
    def replace_list_annotations(cls, module: ast.Module) -> ast.Module:
        for item in module.body:
            if not isinstance(item, ast.ClassDef):
                continue

            # replace List with list in the annotations when list is used as a type
            for class_item in item.body:
                if not isinstance(class_item, ast.AnnAssign):
                    continue
                if isinstance(class_item.annotation, ast.Subscript):
                    class_item.annotation = cls.replace_list_in_subscript(class_item.annotation)

        return module

    def generate_result_types_module(
        self,
        module: ast.Module,
        operation_definition: ExecutableDefinitionNode,  # noqa: ARG002
    ) -> ast.Module:
        module = FutureAnnotationPlugin.insert_future_annotation(module)
        return self.replace_list_annotations(module)


class PydanticBaseModelPlugin(Plugin):
    @staticmethod
    def find_base_model_index(module: ast.Module) -> int:
        for idx, item in enumerate(module.body):
            if isinstance(item, ast.ImportFrom) and item.module == "base_model":
                return idx
        raise ValueError("BaseModel not found in module")

    @classmethod
    def replace_base_model_import(cls, module: ast.Module) -> ast.Module:
        base_model_index = cls.find_base_model_index(module)
        module.body[base_model_index] = ast.ImportFrom(module="pydantic", names=[ast.alias(name="BaseModel")], level=0)
        return module

    def generate_result_types_module(
        self,
        module: ast.Module,
        operation_definition: ExecutableDefinitionNode,  # noqa: ARG002
    ) -> ast.Module:
        return self.replace_base_model_import(module)
