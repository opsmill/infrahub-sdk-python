from __future__ import annotations

from typing import Any

from .renderers import render_input_block, render_query_block, render_variables_to_string


class BaseGraphQLQuery:
    query_type: str = "not-defined"
    indentation: int = 4

    def __init__(self, query: dict, variables: dict | None = None, name: str | None = None) -> None:
        self.query = query
        self.variables = variables
        self.name = name or ""

    def render_first_line(self) -> str:
        first_line = self.query_type

        if self.name:
            first_line += " " + self.name

        if self.variables:
            first_line += f" ({render_variables_to_string(self.variables)})"

        first_line += " {"

        return first_line


class Query(BaseGraphQLQuery):
    query_type = "query"

    def render(self, convert_enum: bool = False) -> str:
        lines = [self.render_first_line()]
        lines.extend(
            render_query_block(
                data=self.query, indentation=self.indentation, offset=self.indentation, convert_enum=convert_enum
            )
        )
        lines.append("}")

        return "\n" + "\n".join(lines) + "\n"


class Mutation(BaseGraphQLQuery):
    query_type = "mutation"

    def __init__(self, *args: Any, mutation: str, input_data: dict, **kwargs: Any) -> None:
        self.input_data = input_data
        self.mutation = mutation
        super().__init__(*args, **kwargs)

    def render(self, convert_enum: bool = False) -> str:
        lines = [self.render_first_line()]
        lines.append(" " * self.indentation + f"{self.mutation}(")
        lines.extend(
            render_input_block(
                data=self.input_data,
                indentation=self.indentation,
                offset=self.indentation * 2,
                convert_enum=convert_enum,
            )
        )
        lines.append(" " * self.indentation + "){")
        lines.extend(
            render_query_block(
                data=self.query,
                indentation=self.indentation,
                offset=self.indentation * 2,
                convert_enum=convert_enum,
            )
        )
        lines.append(" " * self.indentation + "}")
        lines.append("}")

        return "\n" + "\n".join(lines) + "\n"
