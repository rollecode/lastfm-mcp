"""Every documented Last.fm method must be reachable from a tool.

This is the test that fails when the API grows a method and the server does
not, which is the whole point of the server.
"""

import ast
import pathlib

import pytest

SERVER = pathlib.Path(__file__).parent.parent / "src" / "lastfm_mcp" / "server.py"

# The full method list from https://www.last.fm/api, minus auth.getMobileSession
# (password auth, retired for new API accounts) and auth.getToken/auth.getSession
# which the auth tools drive rather than expose.
DOCUMENTED = {
    "album.addTags",
    "album.getInfo",
    "album.getTags",
    "album.getTopTags",
    "album.removeTag",
    "album.search",
    "artist.addTags",
    "artist.getCorrection",
    "artist.getInfo",
    "artist.getSimilar",
    "artist.getTags",
    "artist.getTopAlbums",
    "artist.getTopTags",
    "artist.getTopTracks",
    "artist.removeTag",
    "artist.search",
    "chart.getTopArtists",
    "chart.getTopTags",
    "chart.getTopTracks",
    "geo.getTopArtists",
    "geo.getTopTracks",
    "library.getArtists",
    "tag.getInfo",
    "tag.getSimilar",
    "tag.getTopAlbums",
    "tag.getTopArtists",
    "tag.getTopTags",
    "tag.getTopTracks",
    "tag.getWeeklyChartList",
    "track.addTags",
    "track.getCorrection",
    "track.getInfo",
    "track.getSimilar",
    "track.getTags",
    "track.getTopTags",
    "track.love",
    "track.removeTag",
    "track.scrobble",
    "track.search",
    "track.unlove",
    "track.updateNowPlaying",
    "user.getFriends",
    "user.getInfo",
    "user.getLovedTracks",
    "user.getPersonalTags",
    "user.getRecentTracks",
    "user.getTopAlbums",
    "user.getTopArtists",
    "user.getTopTags",
    "user.getTopTracks",
    "user.getWeeklyAlbumChart",
    "user.getWeeklyArtistChart",
    "user.getWeeklyChartList",
    "user.getWeeklyTrackChart",
}


def called_methods() -> set[str]:
    """Collect every string literal the server passes to a client call."""
    tree = ast.parse(SERVER.read_text())
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        named_call = isinstance(target, ast.Attribute) and target.attr in (
            "call",
            "call_signed_unauthenticated",
        )
        if named_call and node.args and isinstance(node.args[0], ast.Constant):
            found.add(node.args[0].value)
    # track.scrobble goes through the batching helper, not a literal call site.
    found.add("track.scrobble")
    return found


@pytest.mark.parametrize("method", sorted(DOCUMENTED))
def test_method_has_a_tool(method):
    assert method in called_methods(), f"{method} is not reachable from any tool"


def test_no_undocumented_methods():
    assert called_methods() - DOCUMENTED == set()


def test_coverage_is_total():
    assert len(DOCUMENTED) == 54
