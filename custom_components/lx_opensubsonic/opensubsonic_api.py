"""OpenSubsonic-compatible API helpers."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl

from .music_backend import MusicBackend, Song, is_valid_cover_url, parse_duration


VERSION = "1.16.1"
SERVER_VERSION = "0.1.0"
SERVER_TYPE = "lx-opensubsonic"


def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def parse_lrc(lrc: str) -> list[dict[str, Any]]:
    if not lrc:
        return []
    lines: list[dict[str, Any]] = []
    time_re = re.compile(r"\[(\d+):(\d+)(?:\.(\d+))?\]")
    for raw in lrc.splitlines():
        text = time_re.sub("", raw).strip()
        matches = list(time_re.finditer(raw))
        if matches:
            for m in matches:
                minutes = int(m.group(1))
                seconds = int(m.group(2))
                ms = int((m.group(3) or "0").ljust(3, "0")[:3])
                start = minutes * 60000 + seconds * 1000 + ms
                lines.append({"value": text, "start": start})
        elif text:
            lines.append({"value": text})
    lines.sort(key=lambda x: x.get("start", 0))
    return lines


class OpenSubsonicAPI:
    def __init__(
        self,
        backend: MusicBackend,
        username: str,
        password: str,
        playlist_song_virtual_album: bool = False,
    ) -> None:
        self.backend = backend
        self.username = username
        self.password = password
        # Only affects online-search playlists (pl_tx_*). Default False.
        self.playlist_song_virtual_album = bool(playlist_song_virtual_album)

    def ok(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        base = {
            "status": "ok",
            "version": VERSION,
            "type": SERVER_TYPE,
            "serverVersion": SERVER_VERSION,
            "openSubsonic": True,
        }
        if data:
            base.update(data)
        return {"subsonic-response": base}

    def fail(self, code: int, message: str) -> dict[str, Any]:
        return {
            "subsonic-response": {
                "status": "failed",
                "version": VERSION,
                "type": SERVER_TYPE,
                "serverVersion": SERVER_VERSION,
                "openSubsonic": True,
                "error": {"code": code, "message": message},
            }
        }

    def verify_auth(self, params: dict[str, str]) -> bool:
        u = params.get("u")
        if not u or u != self.username:
            return False
        t = params.get("t")
        s = params.get("s")
        if t and s:
            return md5(self.password + s).lower() == t.lower()
        p = params.get("p")
        if p:
            if p.startswith("enc:"):
                try:
                    p = bytes.fromhex(p[4:]).decode("utf-8")
                except Exception:
                    return False
            return p == self.password
        return False

    @staticmethod
    def merge_params(query: dict[str, str], body: str | None, content_type: str | None) -> dict[str, str]:
        params = dict(query)
        if body and content_type and "application/x-www-form-urlencoded" in content_type:
            for k, v in parse_qsl(body, keep_blank_values=True):
                params.setdefault(k, v)
        elif body and content_type and "application/json" in content_type:
            # ignore json body for now
            pass
        # also accept raw form without content type
        if body and not content_type:
            for k, v in parse_qsl(body, keep_blank_values=True):
                params.setdefault(k, v)
        return params

    async def handle(self, method: str, params: dict[str, str]) -> dict[str, Any] | tuple[str, Any]:
        method = method.replace(".view", "")
        if not self.verify_auth(params) and method not in ("ping",):
            # ping also requires auth in strict mode; keep same as lxserver
            if method != "ping" or not self.verify_auth(params):
                if method == "ping" and not params.get("u"):
                    return self.fail(40, "Wrong username or password")
                if not self.verify_auth(params):
                    return self.fail(40, "Wrong username or password")

        if method == "ping":
            return self.ok()
        if method == "getLicense":
            return self.ok(
                {
                    "license": {
                        "valid": True,
                        "email": "lx@local",
                        "licenseExpires": "2099-12-31T00:00:00.000Z",
                    }
                }
            )
        if method == "getOpenSubsonicExtensions":
            return self.ok(
                {
                    "openSubsonicExtensions": [
                        {"name": "formPost", "versions": [1]},
                        {"name": "songLyrics", "versions": [1]},
                        {"name": "lyrics", "versions": [1]},
                        {"name": "coverArtScaling", "versions": [1]},
                    ]
                }
            )
        if method == "getMusicFolders":
            return self.ok({"musicFolders": {"musicFolder": [{"id": 1, "name": "LX Music"}]}})
        if method == "getUser":
            return self.ok(
                {
                    "user": {
                        "username": self.username,
                        "email": "",
                        "scrobblingEnabled": False,
                        "adminRole": True,
                        "settingsRole": True,
                        "downloadRole": True,
                        "uploadRole": False,
                        "playlistRole": True,
                        "coverArtRole": True,
                        "commentRole": False,
                        "podcastRole": False,
                        "shareRole": False,
                        "videoConversionRole": False,
                        "folder": [1],
                    }
                }
            )
        if method in ("search", "search2", "search3"):
            return await self._search(params)
        if method == "getSong":
            return await self._get_song(params)
        if method == "getAlbum":
            return await self._get_album(params)
        if method in ("getAlbumInfo", "getAlbumInfo2"):
            return await self._get_album_info(params)
        if method in ("getArtistInfo", "getArtistInfo2"):
            return await self._get_artist_info(params)
        if method == "getArtist":
            return await self._get_artist(params)
        if method in ("getArtists", "getArtistList"):
            return self.ok({"artists": {"ignoredArticles": "The An A", "index": []}})
        if method in ("getAlbumList", "getAlbumList2"):
            return self.ok({"albumList2" if method.endswith("2") else "albumList": {"album": []}})
        if method in ("getPlaylists",):
            return await self._get_playlists(params)
        if method == "getPlaylist":
            return await self._get_playlist(params)
        if method in ("getStarred", "getStarred2"):
            key = "starred2" if method.endswith("2") else "starred"
            return self.ok({key: {"song": [], "album": [], "artist": []}})
        if method in ("getRandomSongs", "getSongsByGenre", "getSongsByGenre2"):
            return self.ok({"randomSongs": {"song": []}})
        if method in ("getSimilarSongs", "getSimilarSongs2"):
            return await self._similar(params, method)
        if method == "getTopSongs":
            return self.ok({"topSongs": {"song": []}})
        if method == "getLyrics":
            return await self._get_lyrics(params)
        if method == "getLyricsBySongId":
            return await self._get_lyrics_by_id(params)
        if method == "getCoverArt":
            return ("cover", params.get("id") or "")
        if method in ("stream", "download"):
            return ("stream", params.get("id") or "")
        if method == "scrobble":
            return self.ok()
        if method == "getScanStatus":
            return self.ok({"scanStatus": {"scanning": False, "count": 0}})
        if method == "getNowPlaying":
            return self.ok({"nowPlaying": {"entry": []}})
        return self.fail(0, f"Method not found: {method}")

    async def _search(self, params: dict[str, str]) -> dict[str, Any]:
        query = (params.get("query") or "").strip().strip('"').strip("'")
        song_count = max(0, int(params.get("songCount") or 20))
        album_count = max(0, int(params.get("albumCount") or 10))
        artist_count = max(0, int(params.get("artistCount") or 10))
        songs = await self.backend.search(query, limit=max(song_count, 20)) if query else []
        song_items = [s.to_child() for s in songs[:song_count]]

        album_map: dict[str, dict[str, Any]] = {}
        artist_map: dict[str, dict[str, Any]] = {}
        for s in songs:
            if s.album_id and s.album_id not in album_map:
                album_map[s.album_id] = {
                    "id": s.album_id,
                    "name": s.album,
                    "title": s.album,
                    "artist": s.artist,
                    "artistId": s.artist_id,
                    "coverArt": s.cover if is_valid_cover_url(s.cover) else s.album_id,
                    "songCount": 1,
                    "duration": s.duration,
                    "created": datetime.now(timezone.utc).isoformat(),
                    "isDir": True,
                }
            else:
                if s.album_id in album_map:
                    album_map[s.album_id]["songCount"] += 1
                    album_map[s.album_id]["duration"] += s.duration
            aid = s.artist_id or f"artist_{s.artist.split('、')[0]}"
            if aid not in artist_map:
                artist_map[aid] = {
                    "id": aid,
                    "name": s.artist.split("、")[0],
                    "coverArt": s.cover if is_valid_cover_url(s.cover) else aid,
                    "artistImageUrl": s.cover if is_valid_cover_url(s.cover) else None,
                    "albumCount": 0,
                    "songCount": 1,
                }
            else:
                artist_map[aid]["songCount"] += 1

        # MA OpenSubsonic search only shows song/album/artist (not playlist).
        # Map TX online playlists into searchResult3.album so they appear in MA online search.
        playlist_albums: list[dict[str, Any]] = []
        if query and getattr(self.backend, "search_source", "tx") == "tx" and album_count > 0:
            try:
                playlists = await self.backend.search_tx_playlists(query, limit=max(album_count, 10))
                for pl in playlists:
                    playlist_albums.append(
                        {
                            "id": pl.id,
                            "name": f"[歌单] {pl.name}",
                            "title": f"[歌单] {pl.name}",
                            "artist": pl.owner or "TX歌单",
                            "artistId": f"artist_{ (pl.owner or 'TX').split('、')[0] }",
                            "coverArt": pl.cover if is_valid_cover_url(pl.cover) else pl.id,
                            "songCount": pl.song_count or 0,
                            "duration": 0,
                            "created": pl.created or datetime.now(timezone.utc).isoformat(),
                            "isDir": True,
                        }
                    )
            except Exception:
                playlist_albums = []

        # Prefer playlists first in album bucket, then real albums.
        albums = (playlist_albums + list(album_map.values()))[:album_count]

        return self.ok(
            {
                "searchResult3": {
                    "song": song_items,
                    "album": albums,
                    "artist": list(artist_map.values())[:artist_count],
                }
            }
        )

    async def _get_playlists(self, params: dict[str, str]) -> dict[str, Any]:
        playlists = await self.backend.list_playlists()
        return self.ok({"playlists": {"playlist": [p.to_subsonic() for p in playlists]}})

    async def _get_playlist(self, params: dict[str, str]) -> dict[str, Any]:
        pid = params.get("id") or ""
        if not pid:
            return self.fail(10, "Required parameter is missing: id")
        pl, songs = await self.backend.get_playlist(pid)
        if not pl:
            return self.fail(70, f"Playlist not found: {pid}")
        return self.ok({"playlist": pl.to_subsonic(songs)})

    async def _get_song(self, params: dict[str, str]) -> dict[str, Any]:
        sid = params.get("id")
        if not sid:
            return self.fail(10, "Required parameter is missing: id")
        song = await self.backend.get_song(sid)
        if not song:
            return self.fail(70, f"Song not found: {sid}")
        return self.ok({"song": song.to_child()})

    async def _get_album(self, params: dict[str, str]) -> dict[str, Any]:
        aid = params.get("id")
        if not aid:
            return self.fail(10, "Required parameter is missing: id")
        # TX online playlist mapped as album in search
        if str(aid).startswith("pl_tx_"):
            pl, songs = await self.backend.get_playlist(str(aid))
            if not pl:
                return self.fail(70, f"Playlist not found: {aid}")
            # Playlist cover only for the album object itself.
            # Optional: remap each song albumId/parent to song-level virtual id (MA cover workaround).
            song_items = []
            for s in songs:
                child = s.to_child()
                # Prefer direct song cover URL; fallback to song id for getCoverArt.
                # Never use playlist cover on tracks.
                if is_valid_cover_url(s.cover):
                    child["coverArt"] = s.cover
                else:
                    child["coverArt"] = s.id
                if self.playlist_song_virtual_album:
                    # MA 2.9.6 ignores song coverArt and inherits album image.
                    # Force every playlist track into its own virtual album id.
                    child["albumId"] = s.id
                    child["parent"] = s.id
                    # Unique album name helps clients not merge all tracks under one album card.
                    child["album"] = s.title
                else:
                    # Default: keep real album ids; only avoid playlist id as parent/albumId
                    if not child.get("albumId") or str(child.get("albumId")).startswith("pl_"):
                        child["albumId"] = s.id
                    if not child.get("parent") or str(child.get("parent")).startswith("pl_"):
                        child["parent"] = child["albumId"]
                song_items.append(child)
            # Album/header cover uses playlist art.
            # Per-track list thumbs in MA 2.9.6 still inherit this album cover (MA ignores song coverArt).
            # Virtual-album mode still helps song detail / now-playing via albumId=song.id.
            album_cover = pl.cover if is_valid_cover_url(pl.cover) else pl.id
            album = {
                "id": pl.id,
                "name": f"[歌单] {pl.name}",
                "title": f"[歌单] {pl.name}",
                "album": pl.name,
                "artist": pl.owner or "TX歌单",
                "artistId": f"artist_{(pl.owner or 'TX').split('、')[0]}",
                "songCount": len(songs),
                "duration": sum(s.duration for s in songs),
                "created": pl.created or datetime.now(timezone.utc).isoformat(),
                "coverArt": album_cover,
                "isDir": True,
                "playCount": 0,
                "song": song_items,
            }
            return self.ok({"album": album})
        # Song-level virtual album (enabled by playlist_song_virtual_album)
        if str(aid).startswith(("tx_", "kg_", "kw_", "mg_", "wy_")):
            song = await self.backend.get_song(str(aid))
            if song:
                child = song.to_child()
                child["coverArt"] = song.id
                child["albumId"] = song.id
                child["parent"] = song.id
                child["album"] = song.title
                album = {
                    "id": song.id,
                    "name": song.title,
                    "title": song.title,
                    "album": song.title,
                    "artist": song.artist,
                    "artistId": song.artist_id,
                    "songCount": 1,
                    "duration": song.duration,
                    "created": datetime.now(timezone.utc).isoformat(),
                    # Important: coverArt id points to song so resolve_image/getCoverArt uses song art
                    "coverArt": song.id,
                    "isDir": True,
                    "playCount": 0,
                    "song": [child],
                }
                return self.ok({"album": album})
        # If album id unknown, try as song id
        name, songs = await self.backend.get_album_songs(aid)
        if not songs:
            song = await self.backend.get_song(aid)
            if song:
                songs = [song]
                name = song.album
                aid = song.album_id or aid
        if not songs and aid.startswith("alb_tx_"):
            # search by album mid indirectly via cache miss
            songs = [s for s in self.backend.song_cache.values() if s.album_id == aid]
            if songs:
                name = songs[0].album
        album = {
            "id": aid,
            "name": name,
            "title": name,
            "album": name,
            "artist": songs[0].artist if songs else "LX Music",
            "artistId": songs[0].artist_id if songs else "artist_lx",
            "songCount": len(songs),
            "duration": sum(s.duration for s in songs),
            "created": datetime.now(timezone.utc).isoformat(),
            "coverArt": songs[0].cover if songs and is_valid_cover_url(songs[0].cover) else aid,
            "isDir": True,
            "playCount": 0,
            "song": [s.to_child() for s in songs],
        }
        return self.ok({"album": album})

    async def _get_album_info(self, params: dict[str, str]) -> dict[str, Any]:
        aid = params.get("id") or ""
        pic = self.backend.cover_cache.get(aid, "")
        if not pic and aid.startswith("alb_tx_"):
            mid = aid.replace("alb_tx_", "", 1)
            pic = f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{mid}.jpg"
        if not pic and aid.startswith("pl_tx_"):
            pl, _ = await self.backend.get_playlist(aid)
            if pl and is_valid_cover_url(pl.cover):
                pic = pl.cover
        if not pic and str(aid).startswith(("tx_", "kg_", "kw_", "mg_", "wy_")):
            song = await self.backend.get_song(str(aid))
            if song and is_valid_cover_url(song.cover):
                pic = song.cover
        if not is_valid_cover_url(pic):
            pic = ""
        return self.ok(
            {
                "albumInfo": {
                    "notes": "",
                    "musicBrainzId": "",
                    "lastFmUrl": "",
                    "smallImageUrl": pic,
                    "mediumImageUrl": pic,
                    "largeImageUrl": pic,
                }
            }
        )

    async def _get_artist_info(self, params: dict[str, str]) -> dict[str, Any]:
        return self.ok(
            {
                "artistInfo2": {
                    "biography": "",
                    "musicBrainzId": "",
                    "lastFmUrl": "",
                    "smallImageUrl": "",
                    "mediumImageUrl": "",
                    "largeImageUrl": "",
                }
            }
        )

    async def _get_artist(self, params: dict[str, str]) -> dict[str, Any]:
        aid = params.get("id") or "artist_unknown"
        name = aid.replace("artist_", "") if aid.startswith("artist_") else aid
        # songs from cache matching artist
        songs = [s for s in self.backend.song_cache.values() if name in s.artist]
        albums_map: dict[str, dict[str, Any]] = {}
        for s in songs:
            if s.album_id and s.album_id not in albums_map:
                albums_map[s.album_id] = {
                    "id": s.album_id,
                    "name": s.album,
                    "title": s.album,
                    "artist": s.artist,
                    "artistId": aid,
                    "songCount": 1,
                    "duration": s.duration,
                    "created": datetime.now(timezone.utc).isoformat(),
                    "coverArt": s.cover if is_valid_cover_url(s.cover) else s.album_id,
                    "isDir": True,
                }
        return self.ok(
            {
                "artist": {
                    "id": aid,
                    "name": name,
                    "albumCount": len(albums_map),
                    "songCount": len(songs),
                    "coverArt": next((s.cover for s in songs if is_valid_cover_url(s.cover)), aid),
                    "album": list(albums_map.values()),
                    "song": [s.to_child() for s in songs[:50]],
                }
            }
        )

    async def _similar(self, params: dict[str, str], method: str) -> dict[str, Any]:
        sid = params.get("id")
        count = max(1, min(int(params.get("count") or 10), 50))
        songs = list(self.backend.song_cache.values())
        target = self.backend.song_cache.get(sid or "")
        if target:
            same = [s for s in songs if s.artist == target.artist and s.id != target.id]
            other = [s for s in songs if s.artist != target.artist]
            ordered = same + other
        else:
            ordered = [s for s in songs if s.id != sid]
        key = "similarSongs" if method == "getSimilarSongs" else "similarSongs2"
        return self.ok({key: {"song": [s.to_child() for s in ordered[:count]]}})

    async def _get_lyrics_by_id(self, params: dict[str, str]) -> dict[str, Any]:
        sid = params.get("id")
        if not sid:
            return self.fail(10, "Required parameter is missing: id")
        # IMPORTANT: MA calls this once per track when opening albums/playlists.
        # Live lyric fetch here makes 100~300 track lists take many seconds.
        # Return empty success instantly; do not fan-out to QQ lyric APIs.
        song = self.backend.song_cache.get(sid)
        artist = song.artist if song else (params.get("artist") or "")
        title = song.title if song else (params.get("title") or "")
        return self.ok(
            {
                "lyrics": {"artist": artist, "title": title, "value": ""},
                "lyricsList": {"structuredLyrics": []},
            }
        )

    async def _get_lyrics(self, params: dict[str, str]) -> dict[str, Any]:
        # Same bulk-load concern as getLyricsBySongId: keep it instant.
        if params.get("id"):
            return await self._get_lyrics_by_id(params)
        title = (params.get("title") or "").strip()
        artist = (params.get("artist") or "").strip()
        return self.ok({"lyrics": {"artist": artist, "title": title, "value": ""}})
