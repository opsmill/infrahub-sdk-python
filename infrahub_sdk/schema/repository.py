from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .._importer import import_module
from ..checks import InfrahubCheck
from ..exceptions import (
    FragmentFileNotFoundError,
    ModuleImportError,
    RepositoryFileNotFoundError,
    ResourceNotDefinedError,
)
from ..generator import InfrahubGenerator
from ..transforms import InfrahubTransform
from ..utils import duplicates

if TYPE_CHECKING:
    from ..node import InfrahubNode, InfrahubNodeSync

    InfrahubNodeTypes = InfrahubNode | InfrahubNodeSync


class InfrahubRepositoryConfigElement(BaseModel):
    """Class to regroup all elements of the Infrahub configuration for a repository for typing purpose."""


class InfrahubRepositoryArtifactDefinitionConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="The name of the artifact definition")
    artifact_name: str | None = Field(default=None, description="Name of the artifact created from this definition")
    parameters: dict[str, Any] = Field(..., description="The input parameters required to render this artifact")
    content_type: str = Field(..., description="The content type of the rendered artifact")
    targets: str = Field(..., description="The group to target when creating artifacts")
    transformation: str = Field(..., description="The transformation to use.")


class InfrahubJinja2TransformConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="The name of the transform")
    query: str = Field(..., description="The name of the GraphQL Query")
    template_path: Path = Field(..., description="The path within the repository of the template file")
    description: str | None = Field(default=None, description="Description for this transform")

    @property
    def template_path_value(self) -> str:
        return str(self.template_path)

    @property
    def payload(self) -> dict[str, str]:
        data = self.model_dump(exclude_none=True)
        data["template_path"] = self.template_path_value
        return data


class InfrahubCheckDefinitionConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="The name of the Check Definition")
    file_path: Path = Field(..., description="The file within the repository with the check code.")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="The input parameters required to run this check"
    )
    targets: str | None = Field(
        default=None, description="The group to target when running this check, leave blank for global checks"
    )
    class_name: str = Field(default="Check", description="The name of the check class to run.")

    def load_class(self, import_root: str | None = None, relative_path: str | None = None) -> type[InfrahubCheck]:
        module = import_module(module_path=self.file_path, import_root=import_root, relative_path=relative_path)

        if self.class_name not in dir(module):
            raise ModuleImportError(message=f"The specified class {self.class_name} was not found within the module")

        check_class = getattr(module, self.class_name)

        if not issubclass(check_class, InfrahubCheck):
            raise ModuleImportError(message=f"The specified class {self.class_name} is not an Infrahub Check")

        return check_class


class InfrahubGeneratorDefinitionConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="The name of the Generator Definition")
    file_path: Path = Field(..., description="The file within the repository with the generator code.")
    query: str = Field(..., description="The GraphQL query to use as input.")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Maps GraphQL query variable names to target object attribute paths using double-underscore notation.",
    )
    targets: str = Field(
        ...,
        description="Name of the CoreStandardGroup whose members become individual Generator targets. One run is created per group member.",
    )
    class_name: str = Field(
        default="Generator",
        description="The name of the Python class within file_path that extends InfrahubGenerator.",
    )
    convert_query_response: bool = Field(
        default=False,
        description="When true, converts the raw GraphQL dict into SDK InfrahubNode objects accessible via self.nodes and self.store.",
    )
    execute_in_proposed_change: bool = Field(
        default=True,
        description="When true (default), the Generator runs as a CI check during proposed changes.",
    )
    execute_after_merge: bool = Field(
        default=True,
        description="When true (default), the Generator runs after a branch merge. Set to false for Generators that only run via event triggers.",
    )

    def load_class(self, import_root: str | None = None, relative_path: str | None = None) -> type[InfrahubGenerator]:
        module = import_module(module_path=self.file_path, import_root=import_root, relative_path=relative_path)

        if self.class_name not in dir(module):
            raise ModuleImportError(message=f"The specified class {self.class_name} was not found within the module")

        generator_class = getattr(module, self.class_name)

        if not issubclass(generator_class, InfrahubGenerator):
            raise ModuleImportError(message=f"The specified class {self.class_name} is not an Infrahub Generator")

        return generator_class


class InfrahubPythonTransformConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="The name of the Transform")
    file_path: Path = Field(..., description="The file within the repository with the transform code.")
    class_name: str = Field(default="Transform", description="The name of the transform class to run.")
    convert_query_response: bool = Field(
        default=False,
        description="Decide if the transform should convert the result of the GraphQL query to SDK InfrahubNode objects.",
    )
    description: str | None = Field(default=None, description="Description for this transform")

    def load_class(self, import_root: str | None = None, relative_path: str | None = None) -> type[InfrahubTransform]:
        module = import_module(module_path=self.file_path, import_root=import_root, relative_path=relative_path)

        if self.class_name not in dir(module):
            raise ModuleImportError(message=f"The specified class {self.class_name} was not found within the module")

        transform_class = getattr(module, self.class_name)

        if not issubclass(transform_class, InfrahubTransform):
            raise ModuleImportError(message=f"The specified class {self.class_name} is not an Infrahub Transform")

        return transform_class


class InfrahubRepositoryGraphQLConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="The name of the GraphQL Query")
    file_path: Path = Field(..., description="The file within the repository with the query code.")

    def load_query(self, relative_path: str = ".") -> str:
        file_name = Path(f"{relative_path}/{self.file_path}")
        try:
            return file_name.read_text(encoding="UTF-8")
        except FileNotFoundError as exc:
            raise RepositoryFileNotFoundError(file_path=str(self.file_path)) from exc


class InfrahubRepositoryFragmentConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Logical name for this fragment file or directory")
    file_path: Path = Field(
        ..., description="Path to a .gql fragment file or a directory of .gql files, relative to repo root"
    )

    def load_fragments(self, relative_path: str = ".") -> list[str]:
        """Return raw content of all fragment files at file_path.

        If file_path is a .gql file, returns a single-element list.
        If file_path is a directory, returns one entry per .gql file found (sorted alphabetically).
        Raises FragmentFileNotFoundError if file_path does not exist.
        """
        resolved = Path(f"{relative_path}/{self.file_path}")
        if not resolved.exists():
            raise FragmentFileNotFoundError(file_path=str(self.file_path))
        if resolved.is_dir():
            return [f.read_text(encoding="UTF-8") for f in sorted(resolved.glob("*.gql"))]
        return [resolved.read_text(encoding="UTF-8")]


class InfrahubObjectConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="The name associated to the object file")
    file_path: Path = Field(..., description="The file within the repository containing object data.")


class InfrahubMenuConfig(InfrahubRepositoryConfigElement):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="The name of the menu")
    file_path: Path = Field(..., description="The file within the repository containing menu data.")


class InfrahubRepositoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check_definitions: list[InfrahubCheckDefinitionConfig] = Field(
        default_factory=list, description="User defined checks"
    )
    schemas: list[Path] = Field(default_factory=list, description="Schema files")
    jinja2_transforms: list[InfrahubJinja2TransformConfig] = Field(
        default_factory=list, description="Jinja2 data transformations"
    )
    artifact_definitions: list[InfrahubRepositoryArtifactDefinitionConfig] = Field(
        default_factory=list, description="Artifact definitions"
    )
    python_transforms: list[InfrahubPythonTransformConfig] = Field(
        default_factory=list, description="Python data transformations"
    )
    generator_definitions: list[InfrahubGeneratorDefinitionConfig] = Field(
        default_factory=list, description="Generator definitions"
    )
    queries: list[InfrahubRepositoryGraphQLConfig] = Field(default_factory=list, description="GraphQL Queries")
    graphql_fragments: list[InfrahubRepositoryFragmentConfig] = Field(
        default_factory=list, description="GraphQL fragment files declared for this repository"
    )
    objects: list[Path] = Field(default_factory=list, description="Objects")
    menus: list[Path] = Field(default_factory=list, description="Menus")

    @field_validator(
        "check_definitions",
        "jinja2_transforms",
        "artifact_definitions",
        "python_transforms",
        "generator_definitions",
        "queries",
        "graphql_fragments",
    )
    @classmethod
    def unique_items(cls, v: list[Any]) -> list[Any]:
        names = [item.name for item in v]
        if dups := duplicates(names):
            raise ValueError(f"Found multiples element with the same names: {dups}")
        return v

    def has_jinja2_transform(self, name: str) -> bool:
        return any(item.name == name for item in self.jinja2_transforms)

    def get_jinja2_transform(self, name: str) -> InfrahubJinja2TransformConfig:
        for item in self.jinja2_transforms:
            if item.name == name:
                return item
        raise ResourceNotDefinedError(f"Unable to find {name!r} in 'jinja2_transforms'")

    def has_check_definition(self, name: str) -> bool:
        return any(item.name == name for item in self.check_definitions)

    def get_check_definition(self, name: str) -> InfrahubCheckDefinitionConfig:
        for item in self.check_definitions:
            if item.name == name:
                return item
        raise ResourceNotDefinedError(f"Unable to find {name!r} in 'check_definitions'")

    def has_artifact_definition(self, name: str) -> bool:
        return any(item.name == name for item in self.artifact_definitions)

    def get_artifact_definition(self, name: str) -> InfrahubRepositoryArtifactDefinitionConfig:
        for item in self.artifact_definitions:
            if item.name == name:
                return item
        raise ResourceNotDefinedError(f"Unable to find {name!r} in 'artifact_definitions'")

    def has_generator_definition(self, name: str) -> bool:
        return any(item.name == name for item in self.generator_definitions)

    def get_generator_definition(self, name: str) -> InfrahubGeneratorDefinitionConfig:
        for item in self.generator_definitions:
            if item.name == name:
                return item
        raise ResourceNotDefinedError(f"Unable to find {name!r} in 'generator_definitions'")

    def has_python_transform(self, name: str) -> bool:
        return any(item.name == name for item in self.python_transforms)

    def get_python_transform(self, name: str) -> InfrahubPythonTransformConfig:
        for item in self.python_transforms:
            if item.name == name:
                return item
        raise ResourceNotDefinedError(f"Unable to find {name!r} in 'python_transforms'")

    def has_query(self, name: str) -> bool:
        return any(item.name == name for item in self.queries)

    def get_query(self, name: str) -> InfrahubRepositoryGraphQLConfig:
        for item in self.queries:
            if item.name == name:
                return item
        raise ResourceNotDefinedError(f"Unable to find {name!r} in 'queries'")

    def has_fragment(self, name: str) -> bool:
        return any(item.name == name for item in self.graphql_fragments)

    def get_fragment(self, name: str) -> InfrahubRepositoryFragmentConfig:
        for item in self.graphql_fragments:
            if item.name == name:
                return item
        raise ResourceNotDefinedError(f"Unable to find {name!r} in 'graphql_fragments'")
