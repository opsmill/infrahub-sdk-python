import tempfile

from infrahub_sdk.repository import GitRepoManager


def test_init_repository():
    temp_dir = tempfile.mkdtemp()
    repo = GitRepoManager(temp_dir)
    assert repo.active_branch == "main"
