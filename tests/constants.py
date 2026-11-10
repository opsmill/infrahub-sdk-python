from pathlib import Path

CLIENT_TYPE_ASYNC = "standard"
CLIENT_TYPE_SYNC = "sync"
CLIENT_TYPES = [CLIENT_TYPE_ASYNC, CLIENT_TYPE_SYNC]

TEST_DIR = Path(__file__).parent
FIXTURES_DIR = TEST_DIR / "fixtures"
FIXTURE_REPOS_DIR = FIXTURES_DIR / "repos"

REPO_ROOT = TEST_DIR.parent
PACKAGE_DIR = REPO_ROOT / "infrahub_sdk"
PYPROJECT_FILE = REPO_ROOT / "pyproject.toml"
