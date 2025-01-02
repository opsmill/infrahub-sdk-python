"""Integration tests for infrahubctl commands."""

import sys
from unittest import mock

import pytest
from typer.testing import CliRunner

from infrahub_sdk.client import InfrahubClient
from infrahub_sdk.ctl.cli_commands import app

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
@mock.patch("infrahub_sdk.ctl.repository.initialize_client")
class TestInfrahubctlRepository:
    """Groups the 'infrahubctl repository' test cases."""

    @requires_python_310
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
