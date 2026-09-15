import hashlib

import pytest

from lastfm_mcp.client import WRITE_METHODS, LastfmClient, _stringify


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("LASTFM_API_KEY", "key")
    monkeypatch.setenv("LASTFM_API_SECRET", "secret")
    monkeypatch.setenv("LASTFM_SESSION_KEY", "sk")
    monkeypatch.setenv("LASTFM_USERNAME", "rolle")
    return LastfmClient()


def test_signature_sorts_and_excludes_format(client):
    params = {"method": "track.love", "artist": "Boris", "format": "json"}
    expected = hashlib.md5(
        ("artistBorismethodtrack.love" + "secret").encode("utf-8")
    ).hexdigest()
    assert client.sign(params) == expected


def test_signature_changes_with_parameters(client):
    a = client.sign({"method": "track.love", "track": "Farewell"})
    b = client.sign({"method": "track.love", "track": "Rainbow"})
    assert a != b


def test_booleans_become_one_and_zero():
    assert _stringify(True) == "1"
    assert _stringify(False) == "0"


def test_default_user_falls_back_to_account(client):
    assert client.default_user(None) == "rolle"
    assert client.default_user("someoneelse") == "someoneelse"


def test_default_user_without_account_explains(monkeypatch, tmp_path):
    monkeypatch.setenv("LASTFM_API_KEY", "key")
    monkeypatch.delenv("LASTFM_USERNAME", raising=False)
    monkeypatch.setenv("LASTFM_SESSION_KEY", "sk")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="No user given"):
        LastfmClient().default_user(None)


def test_scrobble_rejects_more_than_fifty(client):
    tracks = [{"artist": "a", "track": str(i)} for i in range(51)]
    with pytest.raises(ValueError, match="at most 50"):
        client.scrobble_batch(tracks)


def test_scrobble_rejects_empty(client):
    with pytest.raises(ValueError, match="No tracks"):
        client.scrobble_batch([])


def test_scrobble_requires_artist_and_track(client):
    with pytest.raises(ValueError, match="needs both"):
        client.scrobble_batch([{"artist": "Boris"}])


def test_missing_api_key_explains_where_to_get_one(monkeypatch, tmp_path):
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="LASTFM_API_KEY"):
        LastfmClient()


def test_write_methods_are_the_ten_documented_ones():
    assert len(WRITE_METHODS) == 10
    assert "track.scrobble" in WRITE_METHODS
    assert "track.getInfo" not in WRITE_METHODS
