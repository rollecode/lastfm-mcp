"""Call real tools and check the requests they build."""

import json

import httpx
import pytest

from lastfm_mcp import server


@pytest.fixture(autouse=True)
def transport(monkeypatch, tmp_path):
    monkeypatch.setenv("LASTFM_API_KEY", "key")
    monkeypatch.setenv("LASTFM_API_SECRET", "secret")
    monkeypatch.setenv("LASTFM_SESSION_KEY", "sk")
    monkeypatch.setenv("LASTFM_USERNAME", "rolle")
    server._client = None
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["query"] = dict(request.url.params)
        if request.content:
            from urllib.parse import parse_qs

            seen["form"] = {
                k: v[0] for k, v in parse_qs(request.content.decode()).items()
            }
        return httpx.Response(200, json={"ok": True})

    client = server._get_client()
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    yield seen
    server._client = None


def test_a_read_names_its_method_and_asks_for_json(transport):
    assert json.loads(server.get_artist(artist="Boris"))["status"] == "success"
    assert transport["method"] == "GET"
    assert transport["query"]["method"] == "artist.getInfo"
    assert transport["query"]["format"] == "json"


def test_booleans_go_out_as_one_and_zero(transport):
    server.get_artist(artist="Boris", autocorrect=False)
    assert transport["query"]["autocorrect"] == "0"


def test_user_tools_default_to_the_signed_in_account(transport):
    server.get_user_recent_tracks()
    assert transport["query"]["user"] == "rolle"


def test_from_and_to_keep_their_reserved_wire_names(transport):
    server.get_user_recent_tracks(from_timestamp=1, to_timestamp=2)
    assert transport["query"]["from"] == "1"
    assert transport["query"]["to"] == "2"


def test_a_write_is_posted_and_signed(transport):
    server.love_track(artist="Boris", track="Farewell")
    assert transport["method"] == "POST"
    assert transport["form"]["method"] == "track.love"
    assert transport["form"]["sk"] == "sk"
    assert len(transport["form"]["api_sig"]) == 32


def test_scrobbling_indexes_each_track(transport):
    server.scrobble_tracks(
        [
            {"artist": "Boris", "track": "Farewell", "timestamp": 100},
            {"artist": "Mono", "track": "Ashes", "timestamp": 200},
        ]
    )
    assert transport["form"]["artist[0]"] == "Boris"
    assert transport["form"]["track[1]"] == "Ashes"
    assert transport["form"]["timestamp[1]"] == "200"


def test_a_lastfm_error_body_becomes_a_readable_message(monkeypatch):
    client = server._get_client()
    client._http = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"error": 10, "message": "Invalid API key"}
            )
        )
    )
    result = json.loads(server.get_artist(artist="Boris"))
    assert result["status"] == "error"
    assert "LASTFM_API_KEY" in result["message"]


def test_annotations_match_what_each_tool_does():
    import asyncio

    registered = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert registered["get_artist"].annotations.readOnlyHint is True
    assert registered["love_track"].annotations.readOnlyHint is False
    assert registered["unlove_track"].annotations.destructiveHint is True
