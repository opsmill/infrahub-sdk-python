from pathlib import Path

import httpx
import orjson

from infrahub_sdk.playback import JSONPlayback
from infrahub_sdk.recorder import JSONRecorder
from infrahub_sdk.types import HTTPMethod


def test_recorder_playback_round_trip(tmp_path: Path) -> None:
    """A response written by the recorder is read back by playback to the same decoded object."""
    payload = {"query": "query { BuiltinTag { edges { node { id } } } }"}
    request_content = orjson.dumps(payload)
    request = httpx.Request("POST", "http://localhost:8000/graphql", content=request_content)

    response_body = {"data": {"BuiltinTag": {"edges": [{"node": {"id": "abc-123"}}]}}}
    response = httpx.Response(status_code=200, content=orjson.dumps(response_body), request=request)

    JSONRecorder(directory=str(tmp_path)).record(response)

    playback = JSONPlayback(directory=str(tmp_path))
    played_back = playback.sync_request(
        url="http://localhost:8000/graphql",
        method=HTTPMethod.POST,
        headers={},
        timeout=10,
        payload=payload,
    )

    assert orjson.loads(played_back.content) == response_body
