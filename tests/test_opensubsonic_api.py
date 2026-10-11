"""Contract tests for the OpenSubsonic method dispatch.

These tests pin the JSON response shapes that Music Assistant (via
libopensonic) expects for endpoints this bridge answers with empty
containers. A "Method not found" reply for any of them makes MA raise
inside recommendation rows or library sync tasks.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path


INTEGRATION_DIR = Path(__file__).parents[1] / "custom_components" / "lx_opensubsonic"
sys.path.insert(0, str(INTEGRATION_DIR.parent))

# Register a stub package so importing the API module does not execute
# __init__.py (which needs Home Assistant).
_package = types.ModuleType("lx_opensubsonic")
_package.__path__ = [str(INTEGRATION_DIR)]  # type: ignore[attr-defined]
sys.modules.setdefault("lx_opensubsonic", _package)

from lx_opensubsonic.opensubsonic_api import OpenSubsonicAPI  # noqa: E402


AUTH = {"u": "admin", "p": "password"}


def call(method: str, **extra: str) -> dict:
    api = OpenSubsonicAPI(backend=None, username="admin", password="password")  # type: ignore[arg-type]
    params = {**AUTH, **extra}
    response = asyncio.run(api.handle(method, params))
    assert isinstance(response, dict)
    return response["subsonic-response"]


def test_newest_podcasts_returns_empty_container() -> None:
    payload = call("getNewestPodcasts", count="5")
    assert payload["status"] == "ok"
    assert payload["podcasts"]["channel"] == []


def test_podcasts_returns_empty_container() -> None:
    payload = call("getPodcasts", inc_episodes="true")
    assert payload["status"] == "ok"
    assert payload["podcasts"]["channel"] == []


def test_internet_radio_stations_returns_empty_container() -> None:
    payload = call("getInternetRadioStations")
    assert payload["status"] == "ok"
    assert payload["internetRadioStations"]["internetRadioStation"] == []


def test_bookmarks_returns_empty_container() -> None:
    payload = call("getBookmarks")
    assert payload["status"] == "ok"
    assert payload["bookmarks"]["bookmark"] == []


def test_genres_returns_empty_container() -> None:
    payload = call("getGenres")
    assert payload["status"] == "ok"
    assert payload["genres"]["genre"] == []


def test_songs_by_genre_uses_documented_key() -> None:
    payload = call("getSongsByGenre", genre="pop")
    assert payload["status"] == "ok"
    assert payload["songsByGenre"]["song"] == []
    assert "randomSongs" not in payload


def test_random_songs_uses_documented_key() -> None:
    payload = call("getRandomSongs", size="5")
    assert payload["status"] == "ok"
    assert payload["randomSongs"]["song"] == []


def test_unknown_method_still_reports_failure() -> None:
    payload = call("getDefinitelyNotAMethod")
    assert payload["status"] == "failed"
    assert "Method not found" in payload["error"]["message"]
