import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from infrahub_sdk.exceptions import FragmentFileNotFoundError, RepositoryFileNotFoundError, ResourceNotDefinedError
from infrahub_sdk.schema.repository import (
    MISSING_WATCH_MESSAGE,
    InfrahubGeneratorDefinitionConfig,
    InfrahubJinja2TransformConfig,
    InfrahubPythonTransformConfig,
    InfrahubRepositoryConfig,
    InfrahubRepositoryFragmentConfig,
    InfrahubRepositoryGraphQLConfig,
    InfrahubWatchConfig,
)


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


def test_load_query_returns_content() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        query_file = Path(tmp) / "my_query.gql"
        query_file.write_text("{ devices { id } }", encoding="UTF-8")
        cfg = InfrahubRepositoryGraphQLConfig(name="my_query", file_path=Path("my_query.gql"))
        result = cfg.load_query(relative_path=tmp)
    assert result == "{ devices { id } }"


def test_load_query_missing_file_raises() -> None:
    cfg = InfrahubRepositoryGraphQLConfig(name="my_query", file_path=Path("does_not_exist.gql"))
    with tempfile.TemporaryDirectory() as tmp, pytest.raises(RepositoryFileNotFoundError) as exc_info:
        cfg.load_query(relative_path=tmp)
    assert "does_not_exist.gql" in exc_info.value.file_path


# --- InfrahubWatchConfig ---


def test_watch_config_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InfrahubWatchConfig.model_validate({"fles": ["utils/"]})


def test_jinja2_transform_watch_parses_object_form() -> None:
    config = InfrahubJinja2TransformConfig.model_validate(
        {
            "name": "DeviceConfig",
            "query": "q",
            "template_path": "templates/device.j2",
            "watch": {"files": ["templates/partials/"]},
        }
    )
    assert config.watch is not None
    assert config.watch.files == ["templates/partials/"]


def test_python_transform_watch_parses_object_form() -> None:
    config = InfrahubPythonTransformConfig.model_validate(
        {
            "name": "DeviceName",
            "file_path": "transforms/name.py",
            "watch": {"files": ["utils/", "shared/helpers.py"]},
        }
    )
    assert config.watch is not None
    assert config.watch.files == ["utils/", "shared/helpers.py"]


def test_jinja2_transform_payload_excludes_absent_watch() -> None:
    config = InfrahubJinja2TransformConfig.model_validate(
        {"name": "DeviceConfig", "query": "q", "template_path": "templates/device.j2"}
    )
    assert "watch" not in config.payload


def test_jinja2_transform_payload_includes_declared_watch() -> None:
    config = InfrahubJinja2TransformConfig.model_validate(
        {
            "name": "DeviceConfig",
            "query": "q",
            "template_path": "templates/device.j2",
            "watch": {"files": ["templates/partials/"]},
        }
    )
    assert config.payload["watch"] == {"files": ["templates/partials/"]}


def test_generator_watch_omitted_defaults_to_none() -> None:
    """A generator definition without a watch block parses, with watch defaulting to None.

    The generator config sets extra="forbid", so this also proves watch is a recognised optional
    field rather than a rejected extra key.
    """
    config = InfrahubGeneratorDefinitionConfig.model_validate(
        {"name": "my_generator", "file_path": "generators/g.py", "query": "q", "targets": "grp"}
    )
    assert config.watch is None


def test_generator_watch_parses_object_form() -> None:
    """The object form `watch: {files: [...]}` parses into an InfrahubWatchConfig with the files preserved."""
    config = InfrahubGeneratorDefinitionConfig.model_validate(
        {
            "name": "my_generator",
            "file_path": "generators/g.py",
            "query": "q",
            "targets": "grp",
            "watch": {"files": ["a", "dir/"]},
        }
    )
    assert config.watch is not None
    assert config.watch.files == ["a", "dir/"]


def test_generator_watch_list_form_rejected() -> None:
    """A bare list `watch: [a, b]` is rejected: the realistic YAML mistake of a list instead of an object.

    Matching the message confirms the rejection is the watch model-type error, not some unrelated failure.
    """
    with pytest.raises(ValidationError, match="valid dictionary or instance of InfrahubWatchConfig"):
        InfrahubGeneratorDefinitionConfig.model_validate(
            {
                "name": "my_generator",
                "file_path": "generators/g.py",
                "query": "q",
                "targets": "grp",
                "watch": ["a", "b"],
            }
        )


# --- Advisory 'watch' warning carried by the generated JSON schema ---
#
# The JSON schema generated from InfrahubRepositoryConfig is published to the infrahub-jsonschema
# repository, where YAML language servers use it to validate .infrahub.yml while it is edited.
# Python transforms and generators declare 'watch' as a required property purely so that editors
# warn when it is absent. The models themselves keep 'watch' optional, so these tests pin the split:
# the JSON schema nudges, the runtime stays permissive.

PYTHON_TRANSFORM = {"name": "device_config", "file_path": "transforms/device.py"}
GENERATOR = {"name": "build_interfaces", "file_path": "generators/iface.py", "query": "q", "targets": "grp"}
JINJA2_TRANSFORM = {"name": "device_config", "query": "q", "template_path": "templates/device.j2"}


def missing_watch_paths(document: dict[str, Any]) -> list[str]:
    """Locations in ``document`` the generated JSON schema flags for having no 'watch' block.

    Filtering on ``validator_value`` isolates the advisory requirement from the genuine required
    fields, so an unrelated omission elsewhere in the document cannot be mistaken for a watch warning.
    """
    validator = Draft202012Validator(InfrahubRepositoryConfig.model_json_schema())
    return [
        "/".join(str(part) for part in error.absolute_path)
        for error in validator.iter_errors(document)
        if error.validator == "required" and error.validator_value == ["watch"]
    ]


@dataclass
class WatchWarningCase:
    name: str
    document: dict[str, Any]
    expected_paths: list[str] = field(default_factory=list)


WATCH_WARNING_CASES = [
    WatchWarningCase(
        name="python-transform-without-watch",
        document={"python_transforms": [PYTHON_TRANSFORM]},
        expected_paths=["python_transforms/0"],
    ),
    WatchWarningCase(
        name="generator-without-watch",
        document={"generator_definitions": [GENERATOR]},
        expected_paths=["generator_definitions/0"],
    ),
    WatchWarningCase(
        name="each-entry-flagged-independently",
        document={
            "python_transforms": [PYTHON_TRANSFORM | {"watch": {"files": ["lib/"]}}, PYTHON_TRANSFORM],
            "generator_definitions": [GENERATOR],
        },
        expected_paths=["python_transforms/1", "generator_definitions/0"],
    ),
    WatchWarningCase(
        name="python-transform-with-watch",
        document={"python_transforms": [PYTHON_TRANSFORM | {"watch": {"files": ["lib/helpers.py"]}}]},
    ),
    WatchWarningCase(
        name="generator-with-watch",
        document={"generator_definitions": [GENERATOR | {"watch": {"files": ["lib/"]}}]},
    ),
    WatchWarningCase(
        name="empty-files-list-is-a-deliberate-choice",
        document={"python_transforms": [PYTHON_TRANSFORM | {"watch": {"files": []}}]},
    ),
    WatchWarningCase(
        name="jinja2-transform-is-out-of-scope",
        document={"jinja2_transforms": [JINJA2_TRANSFORM]},
    ),
    WatchWarningCase(
        name="check-definition-has-no-watch-to-warn-about",
        document={"check_definitions": [{"name": "my_check", "file_path": "check.py"}]},
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in WATCH_WARNING_CASES])
def test_missing_watch_flagged_by_json_schema(case: WatchWarningCase) -> None:
    assert missing_watch_paths(case.document) == case.expected_paths


def test_watch_warning_carries_the_guidance_message() -> None:
    """Both definitions ship 'errorMessage', which is what a YAML language server displays.

    Without it editors fall back to a bare `Missing property "watch"`, which does not tell anyone
    why they should care.
    """
    defs = InfrahubRepositoryConfig.model_json_schema()["$defs"]
    for name in ("InfrahubPythonTransformConfig", "InfrahubGeneratorDefinitionConfig"):
        assert defs[name]["allOf"] == [{"required": ["watch"], "errorMessage": MISSING_WATCH_MESSAGE}]


def test_genuine_required_fields_survive_alongside_the_watch_warning() -> None:
    """The advisory requirement must not displace the fields pydantic marks as required.

    Declaring it through a top-level 'required' in json_schema_extra would overwrite the generated
    list, silently making genuinely mandatory fields optional in the published schema.
    """
    defs = InfrahubRepositoryConfig.model_json_schema()["$defs"]
    assert defs["InfrahubPythonTransformConfig"]["required"] == ["name", "file_path"]
    assert defs["InfrahubGeneratorDefinitionConfig"]["required"] == ["name", "file_path", "query", "targets"]


def test_repository_json_schema_is_a_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(InfrahubRepositoryConfig.model_json_schema())


def test_missing_watch_stays_valid_at_runtime() -> None:
    """The warning is editor-only: parsing a config without 'watch' must keep working."""
    config = InfrahubRepositoryConfig.model_validate(
        {"python_transforms": [PYTHON_TRANSFORM], "generator_definitions": [GENERATOR]}
    )
    assert config.python_transforms[0].watch is None
    assert config.generator_definitions[0].watch is None
