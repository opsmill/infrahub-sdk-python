"""Integration tests for infrahubctl commands."""

import tempfile
from pathlib import Path
from unittest import mock

import pytest
import yaml
from typer.testing import CliRunner

from infrahub_sdk.client import InfrahubClient
from infrahub_sdk.ctl.cli_commands import app
from tests.helpers.fixtures import read_fixture
from tests.helpers.utils import strip_color

runner = CliRunner()


@pytest.fixture
def mock_client() -> mock.Mock:
    """Fixture for a mocked InfrahubClient."""
    return mock.create_autospec(InfrahubClient)


# ---------------------------------------------------------
# infrahubctl  repository command tests
# ---------------------------------------------------------
class TestInfrahubctlRepository:
    """Groups the 'infrahubctl repository' test cases."""

    @mock.patch("infrahub_sdk.ctl.repository.initialize_client")
    def test_repo_no_username_or_password(self, mock_init_client, mock_client) -> None:
        """Case allow no username to be passed in and set it as None rather than blank string that fails."""
        mock_cred = mock.AsyncMock()
        mock_cred.id = "1234"
        mock_client.create.return_value = mock_cred

        mock_init_client.return_value = mock_client
        output = runner.invoke(
            app,
            [
                "repository",
                "add",
                "Gitlab",
                "https://gitlab.com/opsmill/example-repo.git",
            ],
        )
        assert output.exit_code == 0
        mock_client.create.assert_not_called()
        mock_cred.save.assert_not_called()
        mock_client.execute_graphql.assert_called_once()
        mock_client.execute_graphql.assert_called_with(
            query="""
mutation {
    CoreRepositoryCreate(
        data: {
            name: {
                value: "Gitlab"
            }
            location: {
                value: "https://gitlab.com/opsmill/example-repo.git"
            }
            description: {
                value: ""
            }
            default_branch: {
                value: ""
            }
        }
    ){
        ok
    }
}
""",
            tracker="mutation-repository-create",
        )

    @mock.patch("infrahub_sdk.ctl.repository.initialize_client")
    def test_repo_no_username(self, mock_init_client, mock_client) -> None:
        """Case allow no username to be passed in and set it as None rather than blank string that fails."""
        mock_cred = mock.AsyncMock()
        mock_cred.id = "1234"
        mock_client.create.return_value = mock_cred

        mock_init_client.return_value = mock_client
        output = runner.invoke(
            app,
            [
                "repository",
                "add",
                "Gitlab",
                "https://gitlab.com/FragmentedPacket/nautobot-plugin-ansible-filters.git",
                "--password",
                "mySup3rSecureP@ssw0rd",
            ],
        )
        assert output.exit_code == 0
        mock_client.create.assert_called_once()
        mock_client.create.assert_called_with(
            name="Gitlab",
            kind="CorePasswordCredential",
            password="mySup3rSecureP@ssw0rd",
            username=None,
        )
        mock_cred.save.assert_called_once()
        mock_cred.save.assert_called_with(allow_upsert=True)
        mock_client.execute_graphql.assert_called_once()
        mock_client.execute_graphql.assert_called_with(
            query="""
mutation {
    CoreRepositoryCreate(
        data: {
            name: {
                value: "Gitlab"
            }
            location: {
                value: "https://gitlab.com/FragmentedPacket/nautobot-plugin-ansible-filters.git"
            }
            description: {
                value: ""
            }
            default_branch: {
                value: ""
            }
            credential: {
                id: "1234"
            }
        }
    ){
        ok
    }
}
""",
            tracker="mutation-repository-create",
        )

    @mock.patch("infrahub_sdk.ctl.repository.initialize_client")
    def test_repo_username(self, mock_init_client, mock_client) -> None:
        """Case allow no username to be passed in and set it as None rather than blank string that fails."""
        mock_cred = mock.AsyncMock()
        mock_cred.id = "1234"
        mock_client.create.return_value = mock_cred

        mock_init_client.return_value = mock_client
        output = runner.invoke(
            app,
            [
                "repository",
                "add",
                "Gitlab",
                "https://gitlab.com/FragmentedPacket/nautobot-plugin-ansible-filters.git",
                "--password",
                "mySup3rSecureP@ssw0rd",
                "--username",
                "opsmill",
            ],
        )
        assert output.exit_code == 0
        mock_client.create.assert_called_once()
        mock_client.create.assert_called_with(
            name="Gitlab",
            kind="CorePasswordCredential",
            password="mySup3rSecureP@ssw0rd",
            username="opsmill",
        )
        mock_cred.save.assert_called_once()
        mock_cred.save.assert_called_with(allow_upsert=True)
        mock_client.execute_graphql.assert_called_once()
        mock_client.execute_graphql.assert_called_with(
            query="""
mutation {
    CoreRepositoryCreate(
        data: {
            name: {
                value: "Gitlab"
            }
            location: {
                value: "https://gitlab.com/FragmentedPacket/nautobot-plugin-ansible-filters.git"
            }
            description: {
                value: ""
            }
            default_branch: {
                value: ""
            }
            credential: {
                id: "1234"
            }
        }
    ){
        ok
    }
}
""",
            tracker="mutation-repository-create",
        )

    @mock.patch("infrahub_sdk.ctl.repository.initialize_client")
    def test_repo_readonly_true(self, mock_init_client, mock_client) -> None:
        """Case allow no username to be passed in and set it as None rather than blank string that fails."""
        mock_cred = mock.AsyncMock()
        mock_cred.id = "1234"
        mock_client.create.return_value = mock_cred

        mock_init_client.return_value = mock_client
        output = runner.invoke(
            app,
            [
                "repository",
                "add",
                "Gitlab",
                "https://gitlab.com/opsmill/example-repo.git",
                "--password",
                "mySup3rSecureP@ssw0rd",
                "--read-only",
            ],
        )
        assert output.exit_code == 0
        mock_client.create.assert_called_once()
        mock_client.create.assert_called_with(
            name="Gitlab",
            kind="CorePasswordCredential",
            password="mySup3rSecureP@ssw0rd",
            username=None,
        )
        mock_cred.save.assert_called_once()
        mock_cred.save.assert_called_with(allow_upsert=True)
        mock_client.execute_graphql.assert_called_once()
        mock_client.execute_graphql.assert_called_with(
            query="""
mutation {
    CoreReadOnlyRepositoryCreate(
        data: {
            name: {
                value: "Gitlab"
            }
            location: {
                value: "https://gitlab.com/opsmill/example-repo.git"
            }
            description: {
                value: ""
            }
            ref: {
                value: ""
            }
            credential: {
                id: "1234"
            }
        }
    ){
        ok
    }
}
""",
            tracker="mutation-repository-create",
        )

    @mock.patch("infrahub_sdk.ctl.repository.initialize_client")
    def test_repo_description_commit_branch(self, mock_init_client, mock_client) -> None:
        """Case allow no username to be passed in and set it as None rather than blank string that fails."""
        mock_cred = mock.AsyncMock()
        mock_cred.id = "1234"
        mock_client.create.return_value = mock_cred

        mock_init_client.return_value = mock_client
        output = runner.invoke(
            app,
            [
                "repository",
                "add",
                "Gitlab",
                "https://gitlab.com/opsmill/example-repo.git",
                "--password",
                "mySup3rSecureP@ssw0rd",
                "--username",
                "opsmill",
                "--description",
                "This is a test description",
                "--ref",
                "my-custom-branch",
            ],
        )
        assert output.exit_code == 0
        mock_client.create.assert_called_once()
        mock_client.create.assert_called_with(
            name="Gitlab",
            kind="CorePasswordCredential",
            password="mySup3rSecureP@ssw0rd",
            username="opsmill",
        )
        mock_cred.save.assert_called_once()
        mock_cred.save.assert_called_with(allow_upsert=True)
        mock_client.execute_graphql.assert_called_once()
        mock_client.execute_graphql.assert_called_with(
            query="""
mutation {
    CoreRepositoryCreate(
        data: {
            name: {
                value: "Gitlab"
            }
            location: {
                value: "https://gitlab.com/opsmill/example-repo.git"
            }
            description: {
                value: "This is a test description"
            }
            default_branch: {
                value: "my-custom-branch"
            }
            credential: {
                id: "1234"
            }
        }
    ){
        ok
    }
}
""",
            tracker="mutation-repository-create",
        )

    def test_repo_list(self, mock_repositories_list) -> None:
        result = runner.invoke(app, ["repository", "list"])
        assert result.exit_code == 0
        assert strip_color(result.stdout) == read_fixture("output.txt", "integration/test_infrahubctl/repository_list")

    def test_repo_init(self) -> None:
        """Test the repository init command."""
        with (
            tempfile.TemporaryDirectory() as temp_dst,
            tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as temp_yaml,
        ):
            dst = Path(temp_dst)
            yaml_path = Path(temp_yaml.name)
            commit = "v0.0.1"

            answers = {
                "generators": True,
                "menus": True,
                "project_name": "test",
                "queries": True,
                "scripts": True,
                "tests": True,
                "transforms": True,
                "package_mode": False,
                "_commit": commit,
            }

            yaml.safe_dump(answers, temp_yaml)
            temp_yaml.close()
            runner.invoke(app, ["repository", "init", str(dst), "--data", str(yaml_path), "--vcs-ref", commit])
            coppied_answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
            coppied_answers.pop("_src_path")

            assert coppied_answers == answers
            assert (dst / "generators").is_dir()
            assert (dst / "queries").is_dir()
            assert (dst / "scripts").is_dir()
            assert (dst / "pyproject.toml").is_file()

    def test_repo_init_local_template(self) -> None:
        """Test the repository init command with a local template."""
        with (
            tempfile.TemporaryDirectory() as temp_src,
            tempfile.TemporaryDirectory() as temp_dst,
            tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as temp_yaml,
        ):
            src = Path(temp_src)
            dst = Path(temp_dst)

            # Create a simple copier template
            (src / "copier.yml").write_text("project_name:\n  type: str")
            template_dir = src / "{{project_name}}"
            template_dir.mkdir()
            (template_dir / "file.txt.jinja").write_text("Hello {{ project_name }}")

            # Create answers file
            yaml_path = Path(temp_yaml.name)
            answers = {"project_name": "local-test"}
            yaml.safe_dump(answers, temp_yaml)
            temp_yaml.close()

            # Run the command
            result = runner.invoke(
                app, ["repository", "init", str(dst), "--template", str(src), "--data", str(yaml_path)]
            )

            assert result.exit_code == 0, result.stdout

            # Check the output
            project_dir = dst / "local-test"
            assert project_dir.is_dir()
            output_file = project_dir / "file.txt"
            assert output_file.is_file()
            assert output_file.read_text() == "Hello local-test"
