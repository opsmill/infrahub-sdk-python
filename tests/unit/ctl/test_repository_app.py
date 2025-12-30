"""Integration tests for infrahubctl commands."""

from unittest import mock

import pytest
from pytest_httpx import HTTPXMock
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
    def test_repo_no_username_or_password(self, mock_init_client: mock.Mock, mock_client: mock.Mock) -> None:
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
    def test_repo_no_username(self, mock_init_client: mock.Mock, mock_client: mock.Mock) -> None:
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
    def test_repo_username(self, mock_init_client: mock.Mock, mock_client: mock.Mock) -> None:
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
    def test_repo_readonly_true(self, mock_init_client: mock.Mock, mock_client: mock.Mock) -> None:
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
    def test_repo_description_commit_branch(self, mock_init_client: mock.Mock, mock_client: mock.Mock) -> None:
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

    def test_repo_list(self, mock_repositories_list: HTTPXMock) -> None:
        result = runner.invoke(app, ["repository", "list"])
        assert result.exit_code == 0
        assert strip_color(result.stdout) == read_fixture("output.txt", "integration/test_infrahubctl/repository_list")

    def test_repo_init(self) -> None:
        """Test the repository init command."""
        output = runner.invoke(app, ["repository", "init"])
        raw = strip_color(output.stdout)
        assert "uv tool run --from 'copier' copier copy https://github.com/opsmill/infrahub-template" in raw
