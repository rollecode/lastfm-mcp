<center align="center" style="text-align: center;justify-content:center;">
<div align="center" style="text-align: center;justify-content:center;">
<h1 align="center" style="text-align: center;justify-content:center;">

Last.fm MCP server

<img style="justify-content:center;text-align: center;width: 95px; height: auto;" width="793" height="411" alt="image" src="https://github.com/user-attachments/assets/abed1a04-d69b-4ab4-a490-d606064df72d" />
<img style="justify-content:center;text-align: center;width: 194px; height: auto;" alt="Last.fm" src="https://github.com/user-attachments/assets/139ba888-5f87-4ab5-b16e-ae09f0430d0c" />

</h1>


![Version](https://img.shields.io/badge/version-1.0.0-blue.svg?style=for-the-badge) ![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white) ![Last.fm](https://img.shields.io/badge/Last.fm-D51007?style=for-the-badge&logo=lastdotfm&logoColor=white) ![Coverage](https://img.shields.io/badge/API_coverage-54%2F54-brightgreen?style=for-the-badge)

</div>
</center>

<hr>

Read and write Last.fm from Claude.ai and Claude Code. Every documented method of the 2.0 API is a tool: all 44 reads and all 10 writes, scrobbling included. Reads need only an API key. Writes need a session key, which the built-in auth flow fetches once and stores.

<hr>

## Why not the other options

* `kud/mcp-lastfm` covers 41 of the 44 read methods and none of the writes, so it cannot scrobble, love or tag
* `tfmart/ScrobblerContext` can write, but exposes 27 of the 44 reads: no charts, no geo, no tags, no weekly charts. It is also Swift, and has not been touched since June 2025
* Both are complete halves. This one is both halves

## Coverage

A test asserts that every method in the published API list is reachable from a tool, so the server cannot silently fall behind the API.

| Namespace | Methods | Covered |
| --- | --- | --- |
| `album` | 6 | 6 |
| `artist` | 10 | 10 |
| `chart` | 3 | 3 |
| `geo` | 2 | 2 |
| `library` | 1 | 1 |
| `tag` | 7 | 7 |
| `track` | 12 | 12 |
| `user` | 13 | 13 |

`auth.getToken` and `auth.getSession` are driven by the auth tools rather than exposed raw. `auth.getMobileSession` is password auth, which Last.fm no longer issues to new API accounts.

## Tools

### Music metadata

| Tool | What you get |
| --- | --- |
| `get_artist` | Listeners, playcount, similar artists, biography |
| `get_album` | Tracklist, listeners, playcount, tags, wiki |
| `get_track` | Duration, listeners, playcount, album, tags, wiki |
| `search_artists` | Artist search, best match first |
| `search_albums` | Album search, best match first |
| `search_tracks` | Track search, optionally within one artist |
| `get_similar_artists` | Artists similar to one artist |
| `get_similar_tracks` | Tracks similar to one track |
| `get_artist_top_albums` | An artist's most played albums |
| `get_artist_top_tracks` | An artist's most played tracks |
| `get_artist_correction` | Canonical spelling for a misspelled artist |
| `get_track_correction` | Canonical spelling for a misspelled track |

### Listening history

| Tool | What you get |
| --- | --- |
| `get_user_recent_tracks` | Scrobbles, most recent first, with the currently playing track flagged |
| `get_user_info` | Profile: playcount, registration date, country |
| `get_user_loved_tracks` | Loved tracks, most recent first |
| `get_user_friends` | Friends, optionally with their latest scrobble |
| `get_user_top_artists` | Top artists over a period |
| `get_user_top_albums` | Top albums over a period |
| `get_user_top_tracks` | Top tracks over a period |
| `get_user_top_tags` | The tags this user uses most |
| `get_user_personal_tags` | Everything one user tagged with one tag |
| `get_user_weekly_chart_list` | The week ranges weekly charts exist for |
| `get_user_weekly_artist_chart` | One week's artist chart |
| `get_user_weekly_album_chart` | One week's album chart |
| `get_user_weekly_track_chart` | One week's track chart |
| `get_library_artists` | Every artist in the library, with playcounts |

Every user tool defaults to the authenticated account when no user is given.

### Charts and tags

| Tool | What you get |
| --- | --- |
| `get_chart_top_artists` | Most popular artists on Last.fm now |
| `get_chart_top_tracks` | Most popular tracks on Last.fm now |
| `get_chart_top_tags` | Most popular tags on Last.fm now |
| `get_geo_top_artists` | Most popular artists in one country |
| `get_geo_top_tracks` | Most popular tracks in one country, or one city |
| `get_tag_info` | A tag's description, uses and reach |
| `get_similar_tags` | Tags similar to one tag |
| `get_tag_top_artists` | Artists most associated with a tag |
| `get_tag_top_albums` | Albums most associated with a tag |
| `get_tag_top_tracks` | Tracks most associated with a tag |
| `get_top_tags` | The most used tags across Last.fm |
| `get_tag_weekly_chart_list` | Week ranges a tag has charts for |
| `get_artist_tags` | One user's tags on an artist |
| `get_album_tags` | One user's tags on an album |
| `get_track_tags` | One user's tags on a track |
| `get_artist_top_tags` | Community tags on an artist |
| `get_album_top_tags` | Community tags on an album |
| `get_track_top_tags` | Community tags on a track |

### Writing

| Tool | What it does |
| --- | --- |
| `scrobble_tracks` | Scrobble up to 50 plays in one call |
| `update_now_playing` | Set what is playing right now |
| `love_track` | Mark a track as loved |
| `unlove_track` | Remove a track from loved |
| `add_artist_tags` | Apply your own tags to an artist |
| `add_album_tags` | Apply your own tags to an album |
| `add_track_tags` | Apply your own tags to a track |
| `remove_artist_tag` | Remove one of your tags from an artist |
| `remove_album_tag` | Remove one of your tags from an album |
| `remove_track_tag` | Remove one of your tags from a track |

### Authentication

| Tool | What it does |
| --- | --- |
| `start_authentication` | Returns a token and the URL to approve it at |
| `finish_authentication` | Exchanges the approved token for a stored session |
| `get_authentication_status` | Whether writes are possible, and as whom |
| `clear_authentication` | Forgets the stored session |

## Setup

Create an API account at [last.fm/api/account/create](https://www.last.fm/api/account/create), then:

```bash
git clone https://github.com/rollecode/lastfm-mcp.git
cd lastfm-mcp
uv venv && uv pip install -e .
```

Set the credentials:

```bash
export LASTFM_API_KEY=...
export LASTFM_API_SECRET=...
export LASTFM_USERNAME=...      # optional, the default for user tools
```

`LASTFM_API_SECRET` is only needed for writes. A `.env` in the working directory works too.

### Claude Code

```bash
claude mcp add lastfm -- /path/to/lastfm-mcp/.venv/bin/lastfm-mcp
```

### Writes

Run `start_authentication`, open the URL it returns, approve, then run `finish_authentication` with the same token. The session key lands in `~/.cache/lastfm-mcp/session.json` with mode 600 and does not expire.

## Development

```bash
uv pip install -e . pytest ruff
.venv/bin/python -m pytest tests
.venv/bin/ruff check .
```

