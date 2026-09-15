"""MCP server for Last.fm, covering every documented API method."""

import importlib.metadata
import json
import logging
import os

from mcp.server.fastmcp import FastMCP
from mcp.types import Icon

from .client import LastfmClient, LastfmError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    __version__ = importlib.metadata.version("lastfm-mcp")
except importlib.metadata.PackageNotFoundError:  # running from a source tree
    __version__ = "0.0.0"

_ICON_BASE = os.getenv("MCP_PUBLIC_URL", "").rstrip("/")
_ICON_SIZES = (48, 96, 256)

mcp = FastMCP(
    "lastfm",
    icons=(
        [
            Icon(
                src=f"{_ICON_BASE}/icon.png"
                if size == 256
                else f"{_ICON_BASE}/icon-{size}.png",
                mimeType="image/png",
                sizes=[f"{size}x{size}"],
            )
            for size in _ICON_SIZES
        ]
        if _ICON_BASE
        else None
    ),
    website_url=_ICON_BASE or None,
    instructions=(
        "Read and write Last.fm: listening history, charts, loved tracks, "
        "tags, and music metadata for artists, albums and tracks. User tools "
        "default to the authenticated account when no user is given. "
        "Scrobbling, loving and tagging need a session: run "
        "start_authentication, open the URL it returns, then "
        "finish_authentication. Reads work with only an API key. "
        "Use search_tracks or search_artists to resolve a name before asking "
        "for details, and prefer get_user_recent_tracks for what was played."
    ),
)

mcp._mcp_server.version = __version__

_READ = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
_WRITE = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
_DESTRUCTIVE = {**_WRITE, "destructiveHint": True}

_client: LastfmClient | None = None


def _get_client() -> LastfmClient:
    global _client
    if _client is None:
        _client = LastfmClient()
    return _client


def _ok(data: dict) -> str:
    return json.dumps({"status": "success", **data}, indent=2)


def _err(e: Exception) -> str:
    """Turn a failure into an actionable message rather than a traceback."""
    import httpx

    if isinstance(e, LastfmError):
        hints = {
            # Ref: https://www.last.fm/api/errorcodes
            4: "Authentication failed. The session key is no longer valid -- "
            "run start_authentication again.",
            6: "Invalid parameters. Check the artist, album or track name.",
            9: "The session key has expired. Run start_authentication again.",
            10: "Invalid API key. Check LASTFM_API_KEY.",
            11: "Last.fm is offline for maintenance. Try again later.",
            13: "Invalid method signature. Check LASTFM_API_SECRET.",
            16: "Last.fm is temporarily unavailable. Try again.",
            26: "This API key is suspended.",
            29: "Rate limit exceeded. Wait before retrying.",
        }
        msg = hints.get(e.code, str(e))
    elif isinstance(e, httpx.TimeoutException):
        msg = "Request timed out. Last.fm may be slow -- try again."
    elif isinstance(e, httpx.ConnectError):
        msg = "Could not connect to Last.fm. Check network connectivity."
    elif isinstance(e, httpx.HTTPStatusError):
        msg = f"Last.fm API error (HTTP {e.response.status_code})."
    else:
        msg = f"{type(e).__name__}: {e}"

    return json.dumps({"status": "error", "message": msg})


# ------------------------------------------------------------------
# Authentication
# ------------------------------------------------------------------


@mcp.tool(annotations=_WRITE)
def start_authentication() -> str:
    """Begin the Last.fm desktop auth flow.

    Returns a token and the URL to open in a browser. Approve the request
    there, then call finish_authentication with the same token. Only needed
    for writes: scrobbling, loving and tagging.
    """
    try:
        client = _get_client()
        token = client.request_token()
        return _ok(
            {
                "token": token,
                "authorize_url": client.authorize_url(token),
                "next_step": "Open authorize_url, approve, then call "
                "finish_authentication with this token.",
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def finish_authentication(token: str) -> str:
    """Exchange an approved token for a stored session key.

    Args:
        token: The token returned by start_authentication, after approving it
            in the browser.
    """
    try:
        session = _get_client().complete_authentication(token)
        return _ok({"user": session["name"], "authenticated": True})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_authentication_status() -> str:
    """Report whether a write-capable session is stored, and for which user."""
    try:
        client = _get_client()
        return _ok(
            {
                "authenticated": bool(client.session_key),
                "user": client.username or None,
                "can_write": bool(client.session_key and client.api_secret),
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def clear_authentication() -> str:
    """Forget the stored session key, disabling writes until re-authenticated."""
    try:
        removed = _get_client().clear_session()
        return _ok({"cleared": removed})
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------
# Album
# ------------------------------------------------------------------


@mcp.tool(annotations=_READ)
def get_album(
    artist: str | None = None,
    album: str | None = None,
    mbid: str | None = None,
    username: str | None = None,
    autocorrect: bool = True,
    lang: str | None = None,
) -> str:
    """Get album metadata: tracklist, listeners, playcount, tags, wiki.

    Args:
        artist: Artist name. Required unless mbid is given.
        album: Album name. Required unless mbid is given.
        mbid: MusicBrainz id for the album, used instead of the names.
        username: Include this user's playcount for the album.
        autocorrect: Let Last.fm fix a misspelled artist name.
        lang: ISO 639 alpha-2 language for the wiki text.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "album.getInfo",
                    artist=artist,
                    album=album,
                    mbid=mbid,
                    username=username,
                    autocorrect=autocorrect,
                    lang=lang,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_album_tags(
    artist: str | None = None,
    album: str | None = None,
    mbid: str | None = None,
    user: str | None = None,
    autocorrect: bool = True,
) -> str:
    """Get the tags one user applied to an album.

    Args:
        artist: Artist name. Required unless mbid is given.
        album: Album name. Required unless mbid is given.
        mbid: MusicBrainz id for the album.
        user: Whose tags to read. Defaults to the authenticated account.
        autocorrect: Let Last.fm fix a misspelled artist name.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "album.getTags",
                    artist=artist,
                    album=album,
                    mbid=mbid,
                    user=client.default_user(user),
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_album_top_tags(
    artist: str | None = None,
    album: str | None = None,
    mbid: str | None = None,
    autocorrect: bool = True,
) -> str:
    """Get the tags the whole community applied to an album, by popularity.

    Args:
        artist: Artist name. Required unless mbid is given.
        album: Album name. Required unless mbid is given.
        mbid: MusicBrainz id for the album.
        autocorrect: Let Last.fm fix a misspelled artist name.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "album.getTopTags",
                    artist=artist,
                    album=album,
                    mbid=mbid,
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def search_albums(album: str, limit: int = 30, page: int = 1) -> str:
    """Search albums by name, best match first.

    Args:
        album: The album name to search for.
        limit: Results per page (default 30, maximum 1000).
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "album.search", album=album, limit=limit, page=page
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def add_album_tags(artist: str, album: str, tags: str) -> str:
    """Apply your own tags to an album. Needs authentication.

    Args:
        artist: Artist name.
        album: Album name.
        tags: Up to 10 tags, comma separated.
    """
    try:
        _get_client().call("album.addTags", artist=artist, album=album, tags=tags)
        return _ok({"tagged": f"{artist} - {album}", "tags": tags})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_album_tag(artist: str, album: str, tag: str) -> str:
    """Remove one of your tags from an album. Needs authentication.

    Args:
        artist: Artist name.
        album: Album name.
        tag: The single tag to remove.
    """
    try:
        _get_client().call("album.removeTag", artist=artist, album=album, tag=tag)
        return _ok({"untagged": f"{artist} - {album}", "tag": tag})
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------
# Artist
# ------------------------------------------------------------------


@mcp.tool(annotations=_READ)
def get_artist(
    artist: str | None = None,
    mbid: str | None = None,
    username: str | None = None,
    autocorrect: bool = True,
    lang: str | None = None,
) -> str:
    """Get artist metadata: listeners, playcount, similar artists, bio.

    Args:
        artist: Artist name. Required unless mbid is given.
        mbid: MusicBrainz id for the artist.
        username: Include this user's playcount for the artist.
        autocorrect: Let Last.fm fix a misspelled artist name.
        lang: ISO 639 alpha-2 language for the biography text.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "artist.getInfo",
                    artist=artist,
                    mbid=mbid,
                    username=username,
                    autocorrect=autocorrect,
                    lang=lang,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_artist_correction(artist: str) -> str:
    """Get Last.fm's canonical spelling for a misspelled artist name.

    Args:
        artist: The name as written, possibly misspelled.
    """
    try:
        return _ok({"result": _get_client().call("artist.getCorrection", artist=artist)})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_similar_artists(
    artist: str | None = None,
    mbid: str | None = None,
    limit: int = 30,
    autocorrect: bool = True,
) -> str:
    """Get artists similar to this one, most similar first.

    Args:
        artist: Artist name. Required unless mbid is given.
        mbid: MusicBrainz id for the artist.
        limit: How many similar artists to return.
        autocorrect: Let Last.fm fix a misspelled artist name.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "artist.getSimilar",
                    artist=artist,
                    mbid=mbid,
                    limit=limit,
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_artist_tags(
    artist: str | None = None,
    mbid: str | None = None,
    user: str | None = None,
    autocorrect: bool = True,
) -> str:
    """Get the tags one user applied to an artist.

    Args:
        artist: Artist name. Required unless mbid is given.
        mbid: MusicBrainz id for the artist.
        user: Whose tags to read. Defaults to the authenticated account.
        autocorrect: Let Last.fm fix a misspelled artist name.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "artist.getTags",
                    artist=artist,
                    mbid=mbid,
                    user=client.default_user(user),
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_artist_top_albums(
    artist: str | None = None,
    mbid: str | None = None,
    limit: int = 50,
    page: int = 1,
    autocorrect: bool = True,
) -> str:
    """Get an artist's most played albums.

    Args:
        artist: Artist name. Required unless mbid is given.
        mbid: MusicBrainz id for the artist.
        limit: Results per page.
        page: Which page of results to fetch.
        autocorrect: Let Last.fm fix a misspelled artist name.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "artist.getTopAlbums",
                    artist=artist,
                    mbid=mbid,
                    limit=limit,
                    page=page,
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_artist_top_tags(
    artist: str | None = None, mbid: str | None = None, autocorrect: bool = True
) -> str:
    """Get the tags the community applied to an artist, by popularity.

    Args:
        artist: Artist name. Required unless mbid is given.
        mbid: MusicBrainz id for the artist.
        autocorrect: Let Last.fm fix a misspelled artist name.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "artist.getTopTags",
                    artist=artist,
                    mbid=mbid,
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_artist_top_tracks(
    artist: str | None = None,
    mbid: str | None = None,
    limit: int = 50,
    page: int = 1,
    autocorrect: bool = True,
) -> str:
    """Get an artist's most played tracks.

    Args:
        artist: Artist name. Required unless mbid is given.
        mbid: MusicBrainz id for the artist.
        limit: Results per page.
        page: Which page of results to fetch.
        autocorrect: Let Last.fm fix a misspelled artist name.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "artist.getTopTracks",
                    artist=artist,
                    mbid=mbid,
                    limit=limit,
                    page=page,
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def search_artists(artist: str, limit: int = 30, page: int = 1) -> str:
    """Search artists by name, best match first.

    Args:
        artist: The artist name to search for.
        limit: Results per page (default 30, maximum 1000).
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "artist.search", artist=artist, limit=limit, page=page
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def add_artist_tags(artist: str, tags: str) -> str:
    """Apply your own tags to an artist. Needs authentication.

    Args:
        artist: Artist name.
        tags: Up to 10 tags, comma separated.
    """
    try:
        _get_client().call("artist.addTags", artist=artist, tags=tags)
        return _ok({"tagged": artist, "tags": tags})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_artist_tag(artist: str, tag: str) -> str:
    """Remove one of your tags from an artist. Needs authentication.

    Args:
        artist: Artist name.
        tag: The single tag to remove.
    """
    try:
        _get_client().call("artist.removeTag", artist=artist, tag=tag)
        return _ok({"untagged": artist, "tag": tag})
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------
# Track
# ------------------------------------------------------------------


@mcp.tool(annotations=_READ)
def get_track(
    artist: str | None = None,
    track: str | None = None,
    mbid: str | None = None,
    username: str | None = None,
    autocorrect: bool = True,
) -> str:
    """Get track metadata: duration, listeners, playcount, album, tags, wiki.

    Args:
        artist: Artist name. Required unless mbid is given.
        track: Track name. Required unless mbid is given.
        mbid: MusicBrainz id for the track.
        username: Include this user's playcount and loved status.
        autocorrect: Let Last.fm fix a misspelled artist or track name.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "track.getInfo",
                    artist=artist,
                    track=track,
                    mbid=mbid,
                    username=username,
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_track_correction(artist: str, track: str) -> str:
    """Get Last.fm's canonical spelling for a misspelled artist and track.

    Args:
        artist: The artist name as written.
        track: The track name as written.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "track.getCorrection", artist=artist, track=track
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_similar_tracks(
    artist: str | None = None,
    track: str | None = None,
    mbid: str | None = None,
    limit: int = 30,
    autocorrect: bool = True,
) -> str:
    """Get tracks similar to this one, most similar first.

    Args:
        artist: Artist name. Required unless mbid is given.
        track: Track name. Required unless mbid is given.
        mbid: MusicBrainz id for the track.
        limit: How many similar tracks to return.
        autocorrect: Let Last.fm fix a misspelled artist or track name.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "track.getSimilar",
                    artist=artist,
                    track=track,
                    mbid=mbid,
                    limit=limit,
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_track_tags(
    artist: str | None = None,
    track: str | None = None,
    mbid: str | None = None,
    user: str | None = None,
    autocorrect: bool = True,
) -> str:
    """Get the tags one user applied to a track.

    Args:
        artist: Artist name. Required unless mbid is given.
        track: Track name. Required unless mbid is given.
        mbid: MusicBrainz id for the track.
        user: Whose tags to read. Defaults to the authenticated account.
        autocorrect: Let Last.fm fix a misspelled artist or track name.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "track.getTags",
                    artist=artist,
                    track=track,
                    mbid=mbid,
                    user=client.default_user(user),
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_track_top_tags(
    artist: str | None = None,
    track: str | None = None,
    mbid: str | None = None,
    autocorrect: bool = True,
) -> str:
    """Get the tags the community applied to a track, by popularity.

    Args:
        artist: Artist name. Required unless mbid is given.
        track: Track name. Required unless mbid is given.
        mbid: MusicBrainz id for the track.
        autocorrect: Let Last.fm fix a misspelled artist or track name.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "track.getTopTags",
                    artist=artist,
                    track=track,
                    mbid=mbid,
                    autocorrect=autocorrect,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def search_tracks(
    track: str, artist: str | None = None, limit: int = 30, page: int = 1
) -> str:
    """Search tracks by name, best match first.

    Args:
        track: The track name to search for.
        artist: Narrow the search to one artist.
        limit: Results per page (default 30, maximum 1000).
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "track.search", track=track, artist=artist, limit=limit, page=page
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def love_track(artist: str, track: str) -> str:
    """Mark a track as loved. Needs authentication.

    Args:
        artist: Artist name.
        track: Track name.
    """
    try:
        _get_client().call("track.love", artist=artist, track=track)
        return _ok({"loved": f"{artist} - {track}"})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def unlove_track(artist: str, track: str) -> str:
    """Remove a track from your loved tracks. Needs authentication.

    Args:
        artist: Artist name.
        track: Track name.
    """
    try:
        _get_client().call("track.unlove", artist=artist, track=track)
        return _ok({"unloved": f"{artist} - {track}"})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def add_track_tags(artist: str, track: str, tags: str) -> str:
    """Apply your own tags to a track. Needs authentication.

    Args:
        artist: Artist name.
        track: Track name.
        tags: Up to 10 tags, comma separated.
    """
    try:
        _get_client().call("track.addTags", artist=artist, track=track, tags=tags)
        return _ok({"tagged": f"{artist} - {track}", "tags": tags})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_track_tag(artist: str, track: str, tag: str) -> str:
    """Remove one of your tags from a track. Needs authentication.

    Args:
        artist: Artist name.
        track: Track name.
        tag: The single tag to remove.
    """
    try:
        _get_client().call("track.removeTag", artist=artist, track=track, tag=tag)
        return _ok({"untagged": f"{artist} - {track}", "tag": tag})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def scrobble_tracks(tracks: list[dict]) -> str:
    """Scrobble one or more plays. Needs authentication.

    Args:
        tracks: Up to 50 plays. Each needs artist and track; timestamp (Unix
            seconds the play started) defaults to now, and album, albumArtist,
            mbid, duration and trackNumber are optional. Scrobble only what was
            really played: Last.fm rejects timestamps far in the future, and a
            play should be at least half the track or four minutes long.
    """
    try:
        return _ok({"result": _get_client().scrobble_batch(tracks)})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def update_now_playing(
    artist: str,
    track: str,
    album: str | None = None,
    album_artist: str | None = None,
    duration: int | None = None,
    track_number: int | None = None,
    mbid: str | None = None,
) -> str:
    """Set what is playing right now. Needs authentication.

    This does not scrobble; it only updates the "now playing" line on your
    profile, which Last.fm clears on its own shortly after.

    Args:
        artist: Artist name.
        track: Track name.
        album: Album name.
        album_artist: Album artist, when it differs from the track artist.
        duration: Track length in seconds.
        track_number: Position of the track on the album.
        mbid: MusicBrainz id for the track.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "track.updateNowPlaying",
                    artist=artist,
                    track=track,
                    album=album,
                    albumArtist=album_artist,
                    duration=duration,
                    trackNumber=track_number,
                    mbid=mbid,
                )
            }
        )
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------
# User
# ------------------------------------------------------------------


@mcp.tool(annotations=_READ)
def get_user_info(user: str | None = None) -> str:
    """Get a user's profile: playcount, registration date, country, subscriber.

    Args:
        user: Whose profile to read. Defaults to the authenticated account.
    """
    try:
        client = _get_client()
        return _ok(
            {"result": client.call("user.getInfo", user=client.default_user(user))}
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_recent_tracks(
    user: str | None = None,
    limit: int = 50,
    page: int = 1,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    extended: bool = False,
) -> str:
    """Get a user's listening history, most recent first.

    This is the tool for "what have I been listening to". A currently playing
    track appears first with a nowplaying flag and no play date.

    Args:
        user: Whose history to read. Defaults to the authenticated account.
        limit: Results per page (maximum 200).
        page: Which page of results to fetch.
        from_timestamp: Only plays at or after this Unix timestamp.
        to_timestamp: Only plays at or before this Unix timestamp.
        extended: Also return artist images and whether you loved each track.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getRecentTracks",
                    user=client.default_user(user),
                    limit=limit,
                    page=page,
                    **{"from": from_timestamp, "to": to_timestamp},
                    extended=extended,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_loved_tracks(
    user: str | None = None, limit: int = 50, page: int = 1
) -> str:
    """Get the tracks a user has loved, most recent first.

    Args:
        user: Whose loved tracks to read. Defaults to the authenticated account.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getLovedTracks",
                    user=client.default_user(user),
                    limit=limit,
                    page=page,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_friends(
    user: str | None = None,
    limit: int = 50,
    page: int = 1,
    recenttracks: bool = False,
) -> str:
    """Get a user's friends.

    Args:
        user: Whose friends to read. Defaults to the authenticated account.
        limit: Results per page.
        page: Which page of results to fetch.
        recenttracks: Also include each friend's latest scrobble.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getFriends",
                    user=client.default_user(user),
                    limit=limit,
                    page=page,
                    recenttracks=recenttracks,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_top_artists(
    user: str | None = None, period: str = "overall", limit: int = 50, page: int = 1
) -> str:
    """Get a user's most played artists over a period.

    Args:
        user: Whose chart to read. Defaults to the authenticated account.
        period: One of overall, 7day, 1month, 3month, 6month, 12month.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getTopArtists",
                    user=client.default_user(user),
                    period=period,
                    limit=limit,
                    page=page,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_top_albums(
    user: str | None = None, period: str = "overall", limit: int = 50, page: int = 1
) -> str:
    """Get a user's most played albums over a period.

    Args:
        user: Whose chart to read. Defaults to the authenticated account.
        period: One of overall, 7day, 1month, 3month, 6month, 12month.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getTopAlbums",
                    user=client.default_user(user),
                    period=period,
                    limit=limit,
                    page=page,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_top_tracks(
    user: str | None = None, period: str = "overall", limit: int = 50, page: int = 1
) -> str:
    """Get a user's most played tracks over a period.

    Args:
        user: Whose chart to read. Defaults to the authenticated account.
        period: One of overall, 7day, 1month, 3month, 6month, 12month.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getTopTracks",
                    user=client.default_user(user),
                    period=period,
                    limit=limit,
                    page=page,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_top_tags(user: str | None = None, limit: int = 50) -> str:
    """Get the tags a user uses most.

    Args:
        user: Whose tags to read. Defaults to the authenticated account.
        limit: How many tags to return.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getTopTags", user=client.default_user(user), limit=limit
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_personal_tags(
    tag: str,
    tagging_type: str,
    user: str | None = None,
    limit: int = 50,
    page: int = 1,
) -> str:
    """Get everything a user tagged with one tag.

    Args:
        tag: The tag to look up.
        tagging_type: What was tagged -- artist, album or track.
        user: Whose tags to read. Defaults to the authenticated account.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getPersonalTags",
                    user=client.default_user(user),
                    tag=tag,
                    taggingtype=tagging_type,
                    limit=limit,
                    page=page,
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_weekly_chart_list(user: str | None = None) -> str:
    """Get the week ranges a user has weekly charts for.

    Each entry is a from/to Unix timestamp pair to pass to the weekly chart
    tools.

    Args:
        user: Whose chart list to read. Defaults to the authenticated account.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getWeeklyChartList", user=client.default_user(user)
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_weekly_artist_chart(
    user: str | None = None,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
) -> str:
    """Get a user's artist chart for one week.

    Args:
        user: Whose chart to read. Defaults to the authenticated account.
        from_timestamp: Week start, from get_user_weekly_chart_list. Defaults
            to the most recent week.
        to_timestamp: Week end, from get_user_weekly_chart_list.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getWeeklyArtistChart",
                    user=client.default_user(user),
                    **{"from": from_timestamp, "to": to_timestamp},
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_weekly_album_chart(
    user: str | None = None,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
) -> str:
    """Get a user's album chart for one week.

    Args:
        user: Whose chart to read. Defaults to the authenticated account.
        from_timestamp: Week start, from get_user_weekly_chart_list. Defaults
            to the most recent week.
        to_timestamp: Week end, from get_user_weekly_chart_list.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getWeeklyAlbumChart",
                    user=client.default_user(user),
                    **{"from": from_timestamp, "to": to_timestamp},
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_user_weekly_track_chart(
    user: str | None = None,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
) -> str:
    """Get a user's track chart for one week.

    Args:
        user: Whose chart to read. Defaults to the authenticated account.
        from_timestamp: Week start, from get_user_weekly_chart_list. Defaults
            to the most recent week.
        to_timestamp: Week end, from get_user_weekly_chart_list.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "user.getWeeklyTrackChart",
                    user=client.default_user(user),
                    **{"from": from_timestamp, "to": to_timestamp},
                )
            }
        )
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------
# Library
# ------------------------------------------------------------------


@mcp.tool(annotations=_READ)
def get_library_artists(
    user: str | None = None, limit: int = 50, page: int = 1
) -> str:
    """Get every artist in a user's library, with playcounts.

    Args:
        user: Whose library to read. Defaults to the authenticated account.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        client = _get_client()
        return _ok(
            {
                "result": client.call(
                    "library.getArtists",
                    user=client.default_user(user),
                    limit=limit,
                    page=page,
                )
            }
        )
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------
# Charts
# ------------------------------------------------------------------


@mcp.tool(annotations=_READ)
def get_chart_top_artists(limit: int = 50, page: int = 1) -> str:
    """Get the most popular artists on Last.fm right now.

    Args:
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "chart.getTopArtists", limit=limit, page=page
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_chart_top_tracks(limit: int = 50, page: int = 1) -> str:
    """Get the most popular tracks on Last.fm right now.

    Args:
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "chart.getTopTracks", limit=limit, page=page
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_chart_top_tags(limit: int = 50, page: int = 1) -> str:
    """Get the most popular tags on Last.fm right now.

    Args:
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {"result": _get_client().call("chart.getTopTags", limit=limit, page=page)}
        )
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------
# Geo
# ------------------------------------------------------------------


@mcp.tool(annotations=_READ)
def get_geo_top_artists(country: str, limit: int = 50, page: int = 1) -> str:
    """Get the most popular artists in one country.

    Args:
        country: Country name in ISO 3166-1 form, such as Finland.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "geo.getTopArtists", country=country, limit=limit, page=page
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_geo_top_tracks(
    country: str, location: str | None = None, limit: int = 50, page: int = 1
) -> str:
    """Get the most popular tracks in one country.

    Args:
        country: Country name in ISO 3166-1 form, such as Finland.
        location: Narrow to a city within that country.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "geo.getTopTracks",
                    country=country,
                    location=location,
                    limit=limit,
                    page=page,
                )
            }
        )
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------
# Tag
# ------------------------------------------------------------------


@mcp.tool(annotations=_READ)
def get_tag_info(tag: str, lang: str | None = None) -> str:
    """Get a tag's description, total uses and reach.

    Args:
        tag: The tag name.
        lang: ISO 639 alpha-2 language for the description.
    """
    try:
        return _ok({"result": _get_client().call("tag.getInfo", tag=tag, lang=lang)})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_similar_tags(tag: str) -> str:
    """Get tags similar to this one.

    Args:
        tag: The tag name.
    """
    try:
        return _ok({"result": _get_client().call("tag.getSimilar", tag=tag)})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_tag_top_artists(tag: str, limit: int = 50, page: int = 1) -> str:
    """Get the artists most associated with a tag.

    Args:
        tag: The tag name.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "tag.getTopArtists", tag=tag, limit=limit, page=page
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_tag_top_albums(tag: str, limit: int = 50, page: int = 1) -> str:
    """Get the albums most associated with a tag.

    Args:
        tag: The tag name.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "tag.getTopAlbums", tag=tag, limit=limit, page=page
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_tag_top_tracks(tag: str, limit: int = 50, page: int = 1) -> str:
    """Get the tracks most associated with a tag.

    Args:
        tag: The tag name.
        limit: Results per page.
        page: Which page of results to fetch.
    """
    try:
        return _ok(
            {
                "result": _get_client().call(
                    "tag.getTopTracks", tag=tag, limit=limit, page=page
                )
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_top_tags() -> str:
    """Get the tags used most across all of Last.fm."""
    try:
        return _ok({"result": _get_client().call("tag.getTopTags")})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_tag_weekly_chart_list(tag: str) -> str:
    """Get the week ranges a tag has weekly charts for.

    Args:
        tag: The tag name.
    """
    try:
        return _ok({"result": _get_client().call("tag.getWeeklyChartList", tag=tag)})
    except Exception as e:
        return _err(e)


def main() -> None:
    import argparse

    from dotenv import find_dotenv, load_dotenv

    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path and load_dotenv(dotenv_path, override=False):
        logger.info("Loaded .env from %s", dotenv_path)

    parser = argparse.ArgumentParser(prog="lastfm-mcp")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8440")))
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    if args.host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit(
            f"refusing to listen on {args.host}: this server has no login of "
            "its own. Keep it on the local machine and put a proxy in front."
        )

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    logger.info("Listening on http://%s:%d/mcp", args.host, args.port)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
