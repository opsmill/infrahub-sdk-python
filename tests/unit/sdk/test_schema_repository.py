import tempfile
from pathlib import Path

import pytest

from infrahub_sdk.exceptions import FragmentFileNotFoundError, ResourceNotDefinedError
from infrahub_sdk.schema.repository import InfrahubRepositoryConfig, InfrahubRepositoryFragmentConfig


@pytest.fixture
def repo_config() -> InfrahubRepositoryConfig:
    return InfrahubRepositoryConfig.model_validate(
        {
            "jinja2_transforms": [{"name": "j2_transform", "query": "q1", "template_path": "templates/foo.j2"}],
            "check_definitions": [{"name": "my_check", "file_path": "check.py"}],
            "artifact_definitions": [
                {
                    "name": "my_artifact",
                    "parameters": {},
                    "content_type": "text/plain",
                    "targets": "group",
                    "transformation": "t",
                }
            ],
            "generator_definitions": [{"name": "my_generator", "file_path": "g.py", "query": "q", "targets": "grp"}],
            "python_transforms": [{"name": "my_python_transform", "file_path": "pt.py"}],
            "queries": [{"name": "my_query", "file_path": "q.gql"}],
        }
    )


# --- Duplicate name validation ---


def test_duplicate_jinja2_transforms_raises() -> None:
    with pytest.raises(ValueError, match="same names"):
        InfrahubRepositoryConfig.model_validate(
            {
                "jinja2_transforms": [
                    {"name": "dup", "query": "q", "template_path": "t.j2"},
                    {"name": "dup", "query": "q2", "template_path": "t2.j2"},
                ]
            }
        )


def test_duplicate_check_definitions_raises() -> None:
    with pytest.raises(ValueError, match="same names"):
        InfrahubRepositoryConfig.model_validate(
            {
                "check_definitions": [
                    {"name": "dup", "file_path": "check.py"},
                    {"name": "dup", "file_path": "check2.py"},
                ]
            }
        )


def test_duplicate_artifact_definitions_raises() -> None:
    with pytest.raises(ValueError, match="same names"):
        InfrahubRepositoryConfig.model_validate(
            {
                "artifact_definitions": [
                    {
                        "name": "dup",
                        "parameters": {},
                        "content_type": "text/plain",
                        "targets": "g",
                        "transformation": "t",
                    },
                    {
                        "name": "dup",
                        "parameters": {},
                        "content_type": "text/plain",
                        "targets": "g",
                        "transformation": "t",
                    },
                ]
            }
        )


def test_duplicate_python_transforms_raises() -> None:
    with pytest.raises(ValueError, match="same names"):
        InfrahubRepositoryConfig.model_validate(
            {
                "python_transforms": [
                    {"name": "dup", "file_path": "t.py"},
                    {"name": "dup", "file_path": "t2.py"},
                ]
            }
        )


def test_duplicate_generator_definitions_raises() -> None:
    with pytest.raises(ValueError, match="same names"):
        InfrahubRepositoryConfig.model_validate(
            {
                "generator_definitions": [
                    {"name": "dup", "file_path": "g.py", "query": "q", "targets": "grp"},
                    {"name": "dup", "file_path": "g2.py", "query": "q", "targets": "grp"},
                ]
            }
        )


def test_duplicate_queries_raises() -> None:
    with pytest.raises(ValueError, match="same names"):
        InfrahubRepositoryConfig.model_validate(
            {
                "queries": [
                    {"name": "dup", "file_path": "q.gql"},
                    {"name": "dup", "file_path": "q2.gql"},
                ]
            }
        )


# --- has_jinja2_transform / get_jinja2_transform ---


def test_has_jinja2_transform_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_jinja2_transform("j2_transform") is True


def test_has_jinja2_transform_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_jinja2_transform("missing") is False


def test_get_jinja2_transform_found(repo_config: InfrahubRepositoryConfig) -> None:
    result = repo_config.get_jinja2_transform("j2_transform")
    assert result.name == "j2_transform"


def test_get_jinja2_transform_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    with pytest.raises(ResourceNotDefinedError):
        repo_config.get_jinja2_transform("missing")


# --- has_check_definition / get_check_definition ---


def test_has_check_definition_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_check_definition("my_check") is True


def test_has_check_definition_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_check_definition("missing") is False


def test_get_check_definition_found(repo_config: InfrahubRepositoryConfig) -> None:
    result = repo_config.get_check_definition("my_check")
    assert result.name == "my_check"


def test_get_check_definition_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    with pytest.raises(ResourceNotDefinedError):
        repo_config.get_check_definition("missing")


# --- has_artifact_definition / get_artifact_definition ---


def test_has_artifact_definition_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_artifact_definition("my_artifact") is True


def test_has_artifact_definition_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_artifact_definition("missing") is False


def test_get_artifact_definition_found(repo_config: InfrahubRepositoryConfig) -> None:
    result = repo_config.get_artifact_definition("my_artifact")
    assert result.name == "my_artifact"


def test_get_artifact_definition_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    with pytest.raises(ResourceNotDefinedError):
        repo_config.get_artifact_definition("missing")


# --- has_generator_definition / get_generator_definition ---


def test_has_generator_definition_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_generator_definition("my_generator") is True


def test_has_generator_definition_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_generator_definition("missing") is False


def test_get_generator_definition_found(repo_config: InfrahubRepositoryConfig) -> None:
    result = repo_config.get_generator_definition("my_generator")
    assert result.name == "my_generator"


def test_get_generator_definition_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    with pytest.raises(ResourceNotDefinedError):
        repo_config.get_generator_definition("missing")


# --- has_python_transform / get_python_transform ---


def test_has_python_transform_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_python_transform("my_python_transform") is True


def test_has_python_transform_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_python_transform("missing") is False


def test_get_python_transform_found(repo_config: InfrahubRepositoryConfig) -> None:
    result = repo_config.get_python_transform("my_python_transform")
    assert result.name == "my_python_transform"


def test_get_python_transform_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    with pytest.raises(ResourceNotDefinedError):
        repo_config.get_python_transform("missing")


# --- has_query / get_query ---


def test_has_query_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_query("my_query") is True


def test_has_query_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    assert repo_config.has_query("missing") is False


def test_get_query_found(repo_config: InfrahubRepositoryConfig) -> None:
    result = repo_config.get_query("my_query")
    assert result.name == "my_query"


def test_get_query_not_found(repo_config: InfrahubRepositoryConfig) -> None:
    with pytest.raises(ResourceNotDefinedError):
        repo_config.get_query("missing")


# --- InfrahubRepositoryFragmentConfig / graphql_fragments ---


def test_parse_infrahub_yml_with_graphql_fragments() -> None:
    config = InfrahubRepositoryConfig(
        graphql_fragments=[
            InfrahubRepositoryFragmentConfig(name="interfaces", file_path=Path("fragments/interfaces.gql")),
            InfrahubRepositoryFragmentConfig(name="devices", file_path=Path("fragments/devices.gql")),
        ]
    )
    assert len(config.graphql_fragments) == 2
    assert config.graphql_fragments[0].name == "interfaces"
    assert str(config.graphql_fragments[0].file_path) == "fragments/interfaces.gql"


def test_graphql_fragments_defaults_to_empty() -> None:
    config = InfrahubRepositoryConfig()
    assert config.graphql_fragments == []


def test_has_fragment_found() -> None:
    config = InfrahubRepositoryConfig(
        graphql_fragments=[InfrahubRepositoryFragmentConfig(name="ifaces", file_path=Path("frags/ifaces.gql"))]
    )
    assert config.has_fragment("ifaces") is True


def test_has_fragment_not_found() -> None:
    config = InfrahubRepositoryConfig()
    assert config.has_fragment("missing") is False


def test_get_fragment_found() -> None:
    config = InfrahubRepositoryConfig(
        graphql_fragments=[InfrahubRepositoryFragmentConfig(name="ifaces", file_path=Path("frags/ifaces.gql"))]
    )
    result = config.get_fragment("ifaces")
    assert result.name == "ifaces"


def test_get_fragment_not_found() -> None:
    config = InfrahubRepositoryConfig()
    with pytest.raises(ResourceNotDefinedError):
        config.get_fragment("missing")


def test_load_fragments_single_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        frag_file = Path(tmp) / "ifaces.gql"
        frag_file.write_text("fragment F on T { id }", encoding="UTF-8")
        cfg = InfrahubRepositoryFragmentConfig(name="ifaces", file_path=Path("ifaces.gql"))
        result = cfg.load_fragments(relative_path=tmp)
    assert len(result) == 1
    assert "fragment F on T" in result[0]


def test_load_fragments_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a.gql").write_text("fragment A on T { id }", encoding="UTF-8")
        (Path(tmp) / "b.gql").write_text("fragment B on T { id }", encoding="UTF-8")
        (Path(tmp) / "not_a_gql.txt").write_text("ignored", encoding="UTF-8")
        cfg = InfrahubRepositoryFragmentConfig(name="all", file_path=Path())
        result = cfg.load_fragments(relative_path=tmp)
    assert len(result) == 2
    combined = "".join(result)
    assert "fragment A" in combined
    assert "fragment B" in combined


def test_load_fragments_missing_file_raises() -> None:
    cfg = InfrahubRepositoryFragmentConfig(name="ifaces", file_path=Path("does_not_exist.gql"))
    with tempfile.TemporaryDirectory() as tmp, pytest.raises(FragmentFileNotFoundError) as exc_info:
        cfg.load_fragments(relative_path=tmp)
    assert "does_not_exist.gql" in exc_info.value.file_path
