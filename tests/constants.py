from pathlib import Path

CLIENT_TYPE_ASYNC = "standard"
CLIENT_TYPE_SYNC = "sync"
CLIENT_TYPES = [CLIENT_TYPE_ASYNC, CLIENT_TYPE_SYNC]

TEST_DIR = Path(__file__).parent
FIXTURES_DIR = TEST_DIR / "fixtures"
FIXTURE_REPOS_DIR = FIXTURES_DIR / "repos"
