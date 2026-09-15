"""Client for the Last.fm 2.0 API.

Covers every documented method: reads need only an API key, writes need a
signed session key obtained through the desktop auth flow.

Ref: https://www.last.fm/api
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://ws.audioscrobbler.com/2.0/"

# Write methods sign their parameters and carry a session key. Everything else
# is an unauthenticated read against the same endpoint.
WRITE_METHODS = frozenset(
    {
        "album.addTags",
        "album.removeTag",
        "artist.addTags",
        "artist.removeTag",
        "track.addTags",
        "track.removeTag",
        "track.love",
        "track.unlove",
        "track.scrobble",
        "track.updateNowPlaying",
    }
)

_SESSION_PATH = (
    Path(os.getenv("XDG_CACHE_HOME") or Path.home() / ".cache")
    / "lastfm-mcp"
    / "session.json"
)


class LastfmError(RuntimeError):
    """A Last.fm error response, carrying the numeric code it returned."""

    def __init__(self, code: int, message: str):
        super().__init__(f"Last.fm error {code}: {message}")
        self.code = code


class LastfmClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        session_key: str | None = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("LASTFM_API_KEY") or ""
        self.api_secret = api_secret or os.getenv("LASTFM_API_SECRET") or ""
        self._session_key = session_key or os.getenv("LASTFM_SESSION_KEY") or ""
        self._username = os.getenv("LASTFM_USERNAME") or ""
        self._http = httpx.Client(
            timeout=timeout, headers={"User-Agent": "lastfm-mcp"}
        )

        if not self.api_key:
            raise RuntimeError(
                "LASTFM_API_KEY is not set. Create an API account at "
                "https://www.last.fm/api/account/create"
            )

        if not self._session_key:
            self._load_session()

    # -- session ---------------------------------------------------------

    def _load_session(self) -> None:
        try:
            stored = json.loads(_SESSION_PATH.read_text())
        except (OSError, ValueError):
            return
        self._session_key = stored.get("key") or ""
        self._username = self._username or stored.get("name") or ""

    def _store_session(self, key: str, name: str) -> None:
        _SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_PATH.write_text(json.dumps({"key": key, "name": name}))
        _SESSION_PATH.chmod(0o600)
        self._session_key = key
        self._username = name

    @property
    def session_key(self) -> str:
        return self._session_key

    @property
    def username(self) -> str:
        return self._username

    def default_user(self, user: str | None) -> str:
        """Resolve a user argument, falling back to the signed-in account."""
        resolved = user or self._username
        if not resolved:
            raise RuntimeError(
                "No user given and no authenticated account. Pass user, set "
                "LASTFM_USERNAME, or authenticate first."
            )
        return resolved

    # -- signing ---------------------------------------------------------

    def sign(self, params: dict[str, str]) -> str:
        """Build the api_sig Last.fm expects: sorted key+value pairs, then the
        secret, hashed with MD5.

        Ref: https://www.last.fm/api/authspec#_8-signing-calls
        """
        if not self.api_secret:
            raise RuntimeError(
                "LASTFM_API_SECRET is not set, so writes cannot be signed."
            )
        joined = "".join(
            f"{k}{params[k]}" for k in sorted(params) if k not in ("format", "callback")
        )
        return hashlib.md5((joined + self.api_secret).encode("utf-8")).hexdigest()

    # -- transport -------------------------------------------------------

    def call(self, method: str, **params) -> dict:
        """Call one API method, dropping unset parameters.

        Writes are signed and POSTed; reads are GET. Both ask for JSON.
        """
        payload = {k: v for k, v in params.items() if v is not None}
        payload = {k: _stringify(v) for k, v in payload.items()}
        payload["method"] = method
        payload["api_key"] = self.api_key

        write = method in WRITE_METHODS
        if write:
            if not self._session_key:
                raise RuntimeError(
                    f"{method} needs an authenticated session. Run "
                    "start_authentication then finish_authentication."
                )
            payload["sk"] = self._session_key
            payload["api_sig"] = self.sign(payload)

        payload["format"] = "json"

        if write:
            response = self._http.post(BASE_URL, data=payload)
        else:
            response = self._http.get(BASE_URL, params=payload)

        return self._unwrap(response)

    def call_signed_unauthenticated(self, method: str, **params) -> dict:
        """Call a signed method that establishes the session itself.

        auth.getToken and auth.getSession are signed but cannot carry a session
        key, because obtaining one is the point.
        """
        payload = {k: _stringify(v) for k, v in params.items() if v is not None}
        payload["method"] = method
        payload["api_key"] = self.api_key
        payload["api_sig"] = self.sign(payload)
        payload["format"] = "json"
        return self._unwrap(self._http.get(BASE_URL, params=payload))

    def _unwrap(self, response: httpx.Response) -> dict:
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise LastfmError(0, "Last.fm returned a non-JSON body") from None

        # Last.fm reports its own failures in a 200 body as often as by status,
        # so the payload is authoritative and checked before the status code.
        if isinstance(data, dict) and "error" in data:
            raise LastfmError(int(data["error"]), data.get("message", "unknown"))

        response.raise_for_status()
        return data

    # -- auth flow -------------------------------------------------------

    def request_token(self) -> str:
        data = self.call_signed_unauthenticated("auth.getToken")
        return data["token"]

    def authorize_url(self, token: str) -> str:
        return f"https://www.last.fm/api/auth/?api_key={self.api_key}&token={token}"

    def complete_authentication(self, token: str) -> dict:
        data = self.call_signed_unauthenticated("auth.getSession", token=token)
        session = data["session"]
        self._store_session(session["key"], session["name"])
        return session

    def clear_session(self) -> bool:
        self._session_key = ""
        try:
            _SESSION_PATH.unlink()
        except FileNotFoundError:
            return False
        return True

    # -- scrobbling ------------------------------------------------------

    def scrobble_batch(self, tracks: list[dict]) -> dict:
        """Scrobble up to 50 plays in one call, the API's per-request maximum.

        Ref: https://www.last.fm/api/show/track.scrobble
        """
        if not tracks:
            raise ValueError("No tracks to scrobble.")
        if len(tracks) > 50:
            raise ValueError(
                f"track.scrobble accepts at most 50 tracks per call, got {len(tracks)}."
            )

        params: dict[str, object] = {}
        for index, track in enumerate(tracks):
            if not track.get("artist") or not track.get("track"):
                raise ValueError(f"Track {index} needs both artist and track.")
            params[f"artist[{index}]"] = track["artist"]
            params[f"track[{index}]"] = track["track"]
            params[f"timestamp[{index}]"] = int(
                track.get("timestamp") or time.time()
            )
            for field in ("album", "albumArtist", "mbid", "duration", "trackNumber"):
                if track.get(field) is not None:
                    params[f"{field}[{index}]"] = track[field]
        return self.call("track.scrobble", **params)

    def close(self) -> None:
        self._http.close()


def _stringify(value) -> str:
    """Render a parameter the way Last.fm expects it on the wire."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)
