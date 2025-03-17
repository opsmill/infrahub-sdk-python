"""Integration tests for infrahubctl commands."""

import sys
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

requires_python_310 = pytest.mark.skipif(sys.version_info < (3, 10), reason="Requires Python 3.10 or higher")


@pytest.fixture
def mock_client() -> mock.Mock:
    """Fixture for a mocked InfrahubClient."""
    client = mock.create_autospec(InfrahubClient)
    return client


# ---------------------------------------------------------
# infrahubctl  repository command tests
# ---------------------------------------------------------
class TestInfrahubctlRepository:
    """Groups the 'infrahubctl repository' test cases."""

    @requires_python_310
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
            commit: {
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
            branch_name="main",
            tracker="mutation-repository-create",
        )

    @requires_python_310
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
            commit: {
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
            branch_name="main",
            tracker="mutation-repository-create",
        )

    @requires_python_310
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
                "https://gitlab.com/FragmentedPacket/nautobot-plugin-ansible-filters.git",
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
                value: "https://gitlab.com/FragmentedPacket/nautobot-plugin-ansible-filters.git"
            }
            description: {
                value: ""
            }
            commit: {
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
            branch_name="main",
            tracker="mutation-repository-create",
        )

    @requires_python_310
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
                "https://gitlab.com/FragmentedPacket/nautobot-plugin-ansible-filters.git",
                "--password",
                "mySup3rSecureP@ssw0rd",
                "--username",
                "opsmill",
                "--description",
                "This is a test description",
                "--commit",
                "myHashCommit",
                "--branch",
                "develop",
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
                value: "This is a test description"
            }
            commit: {
                value: "myHashCommit"
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
            branch_name="develop",
            tracker="mutation-repository-create",
        )

    def test_repo_list(self, mock_repositories_list) -> None:
        result = runner.invoke(app, ["repository", "list", "--branch", "main"])
        assert result.exit_code == 0
        assert strip_color(result.stdout) == read_fixture("output.txt", "integration/test_infrahubctl/repository_list")

    def test_repo_init(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dst, tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as temp_yaml:
            dst = Path(temp_dst)
            yaml_path = Path(temp_yaml.name)

            answers = {
                "generators": True,
                "menus": True,
                "project_name": "test",
                "queries": True,
                "scripts": True,
                "tests": True,
                "transforms": True,
                "package_mode": False,
            }

            yaml.safe_dump(answers, temp_yaml)
            temp_yaml.close()
            runner.invoke(app, ["repository", "init", str(dst), "--data", str(yaml_path)])
            coppied_answers = yaml.safe_load((dst / ".copier-answers.yml").read_text())
            coppied_answers.pop("_src_path")

            assert coppied_answers == answers
            assert (dst / "generators").is_dir()
            assert (dst / "queries").is_dir()
            assert (dst / "scripts").is_dir()
            assert (dst / "pyproject.toml").is_file()
