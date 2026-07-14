#!/usr/bin/env python3
"""Smoke test LX OpenSubsonic endpoints against a running Home Assistant instance."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from typing import Any


def request_json(base: str, method: str, params: dict[str, str], timeout: int) -> dict[str, Any]:
    url = f"{base.rstrip('/')}/rest/{method}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request_bytes(base: str, method: str, params: dict[str, str], timeout: int) -> tuple[str, bytes]:
    url = f"{base.rstrip('/')}/rest/{method}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.headers.get("content-type", ""), resp.read(16)


def subsonic_response(data: dict[str, Any]) -> dict[str, Any]:
    resp = data.get("subsonic-response") or {}
    if resp.get("status") != "ok":
        raise RuntimeError(json.dumps(resp, ensure_ascii=False))
    return resp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8123/api/lx_opensubsonic")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--query", default="周杰伦")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    salt = "smoketest"
    token = hashlib.md5(f"{args.password}{salt}".encode("utf-8")).hexdigest()
    common = {
        "u": args.username,
        "t": token,
        "s": salt,
        "v": "1.16.1",
        "c": "lx-opensubsonic-smoke-test",
        "f": "json",
    }

    ping = subsonic_response(request_json(args.base, "ping", common, args.timeout))
    print(f"ping: {ping['status']} serverVersion={ping.get('serverVersion')}")

    search = subsonic_response(
        request_json(
            args.base,
            "search3",
            common | {"query": args.query, "songCount": "3", "albumCount": "1", "artistCount": "1"},
            args.timeout,
        )
    )
    result = search.get("searchResult3") or {}
    songs = result.get("song") or []
    albums = result.get("album") or []
    artists = result.get("artist") or []
    print(f"search3: songs={len(songs)} albums={len(albums)} artists={len(artists)}")
    if not songs:
        raise RuntimeError("search3 returned no songs")

    song = songs[0]
    song_id = song["id"]
    cover_id = song.get("coverArt") or ""
    print(f"first_song: id={song_id} coverArt={cover_id} coverArtUrl={bool(song.get('coverArtUrl'))}")

    got_song = subsonic_response(request_json(args.base, "getSong", common | {"id": song_id}, args.timeout))
    print(f"getSong: id={got_song['song']['id']} coverArt={got_song['song'].get('coverArt')}")

    album_id = got_song["song"].get("albumId") or song.get("albumId") or cover_id
    got_album = subsonic_response(request_json(args.base, "getAlbum", common | {"id": album_id}, args.timeout))
    print(f"getAlbum: id={got_album['album']['id']} songs={len(got_album['album'].get('song') or [])}")

    if cover_id:
        content_type, first_bytes = request_bytes(args.base, "getCoverArt", common | {"id": cover_id}, args.timeout)
        if not first_bytes:
            raise RuntimeError("getCoverArt returned empty body")
        print(f"getCoverArt: content_type={content_type} first_bytes={first_bytes[:4].hex()}")

    playlists = subsonic_response(request_json(args.base, "getPlaylists", common, args.timeout))
    count = len((playlists.get("playlists") or {}).get("playlist") or [])
    print(f"getPlaylists: count={count}")
    print("ok")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as err:
        print(f"failed: {err}", file=sys.stderr)
        raise SystemExit(1)
