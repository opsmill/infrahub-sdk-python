from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .._importer import import_module
from ..checks import InfrahubCheck
from ..exceptions import (
    ModuleImportError,
    ResourceNotDefinedError,
)
from ..generator import InfrahubGenerator
from ..transforms import InfrahubTransform
from ..utils import duplicates

if TYPE_CHECKING:
    from ..node import InfrahubNode, InfrahubNodeSync

    InfrahubNodeTypes = Union[InfrahubNode, InfrahubNodeSync]

ResourceClass = TypeVar("ResourceClass")


class InfrahubRepositoryConfigElement(BaseModel):
    """Class to regroup all elements of the infrahub configuration for a repository for typing purpose."""


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
        default_factory=dict, description="The input parameters required to run this check"
    )
    targets: str = Field(..., description="The group to target when running this generator")
    class_name: str = Field(default="Generator", description="The name of the generator class to run.")
    convert_query_response: bool = Field(
        default=False,
        description="Decide if the generator should convert the result of the GraphQL query to SDK InfrahubNode objects.",
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
        with file_name.open("r", encoding="UTF-8") as file:
            return file.read()


RESOURCE_MAP: dict[Any, str] = {
    InfrahubJinja2TransformConfig: "jinja2_transforms",
    InfrahubCheckDefinitionConfig: "check_definitions",
    InfrahubRepositoryArtifactDefinitionConfig: "artifact_definitions",
    InfrahubPythonTransformConfig: "python_transforms",
    InfrahubGeneratorDefinitionConfig: "generator_definitions",
    InfrahubRepositoryGraphQLConfig: "queries",
}


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

    @field_validator(
        "check_definitions",
        "jinja2_transforms",
        "artifact_definitions",
        "python_transforms",
        "generator_definitions",
        "queries",
    )
    @classmethod
    def unique_items(cls, v: list[Any]) -> list[Any]:
        names = [item.name for item in v]
        if dups := duplicates(names):
            raise ValueError(f"Found multiples element with the same names: {dups}")
        return v

    def _has_resource(self, resource_id: str, resource_type: type[ResourceClass], resource_field: str = "name") -> bool:
        for item in getattr(self, RESOURCE_MAP[resource_type]):
            if getattr(item, resource_field) == resource_id:
                return True
        return False

    def _get_resource(
        self, resource_id: str, resource_type: type[ResourceClass], resource_field: str = "name"
    ) -> ResourceClass:
        for item in getattr(self, RESOURCE_MAP[resource_type]):
            if getattr(item, resource_field) == resource_id:
                return item
        raise ResourceNotDefinedError(f"Unable to find {resource_id!r} in {RESOURCE_MAP[resource_type]!r}")

    def has_jinja2_transform(self, name: str) -> bool:
        return self._has_resource(resource_id=name, resource_type=InfrahubJinja2TransformConfig)

    def get_jinja2_transform(self, name: str) -> InfrahubJinja2TransformConfig:
        return self._get_resource(resource_id=name, resource_type=InfrahubJinja2TransformConfig)

    def has_check_definition(self, name: str) -> bool:
        return self._has_resource(resource_id=name, resource_type=InfrahubCheckDefinitionConfig)

    def get_check_definition(self, name: str) -> InfrahubCheckDefinitionConfig:
        return self._get_resource(resource_id=name, resource_type=InfrahubCheckDefinitionConfig)

    def has_artifact_definition(self, name: str) -> bool:
        return self._has_resource(resource_id=name, resource_type=InfrahubRepositoryArtifactDefinitionConfig)

    def get_artifact_definition(self, name: str) -> InfrahubRepositoryArtifactDefinitionConfig:
        return self._get_resource(resource_id=name, resource_type=InfrahubRepositoryArtifactDefinitionConfig)

    def has_generator_definition(self, name: str) -> bool:
        return self._has_resource(resource_id=name, resource_type=InfrahubGeneratorDefinitionConfig)

    def get_generator_definition(self, name: str) -> InfrahubGeneratorDefinitionConfig:
        return self._get_resource(resource_id=name, resource_type=InfrahubGeneratorDefinitionConfig)

    def has_python_transform(self, name: str) -> bool:
        return self._has_resource(resource_id=name, resource_type=InfrahubPythonTransformConfig)

    def get_python_transform(self, name: str) -> InfrahubPythonTransformConfig:
        return self._get_resource(resource_id=name, resource_type=InfrahubPythonTransformConfig)

    def has_query(self, name: str) -> bool:
        return self._has_resource(resource_id=name, resource_type=InfrahubRepositoryGraphQLConfig)

    def get_query(self, name: str) -> InfrahubRepositoryGraphQLConfig:
        return self._get_resource(resource_id=name, resource_type=InfrahubRepositoryGraphQLConfig)
