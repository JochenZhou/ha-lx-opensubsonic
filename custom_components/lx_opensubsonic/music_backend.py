"""Minimal online music backend for OpenSubsonic bridge.

- Search: configurable platform source (tx/wy/kg/kw/mg)
- Stream: third-party music source JS URL (parse API at runtime; no hard-coded paid key)
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def parse_duration(interval: Any) -> int:
    if interval is None:
        return 0
    if isinstance(interval, (int, float)):
        return int(interval)
    s = str(interval).strip()
    if not s:
        return 0
    if ":" in s:
        parts = [int(x) for x in s.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    try:
        return int(float(s))
    except Exception:
        return 0


def is_valid_cover_url(url: Any) -> bool:
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return False
    if re.search(r"T00[12]R\d+x\d+M000\.jpg(?:\?.*)?$", url, re.I):
        return False
    if re.search(r"M000\.jpg(?:\?.*)?$", url, re.I):
        return False
    return True


def parse_music_source_js(script: str) -> dict[str, str]:
    """Extract API_URL / API_KEY style endpoints from a LX music source script.

    Does not execute JS. Supports clear-text scripts (e.g. 聆澜).
    Obfuscated scripts without extractable constants return empty.
    """
    out: dict[str, str] = {}
    if not script:
        return out

    m = re.search(r"""(?:const|let|var)\s+API_URL\s*=\s*["']([^"']+)["']""", script)
    if m:
        out["api_url"] = m.group(1).rstrip("/")
    m = re.search(r"""(?:const|let|var)\s+API_KEY\s*=\s*["']([^"']*)["']""", script)
    if m:
        out["api_key"] = m.group(1)

    # fallback: common request patterns
    if "api_url" not in out:
        m = re.search(r"""(["'])(https?://[^"']+/api/music)\1""", script)
        if m:
            out["api_url"] = m.group(2).rstrip("/")
    if "api_url" not in out:
        # generic .../url?source=
        m = re.search(r"""(["'])(https?://[^"']+?/url)\1""", script)
        if m:
            base = m.group(2)
            out["api_url"] = base[:-4] if base.endswith("/url") else base.rstrip("/")

    # X-API-Key string literals
    if "api_key" not in out:
        m = re.search(r"""X-API-Key["']?\s*[,:]\s*["']([^"']+)["']""", script)
        if m:
            out["api_key"] = m.group(1)
    if "api_key" not in out:
        m = re.search(r"""(?:CERU_KEY|API_KEY)[-_A-Za-z0-9]{8,}""", script)
        # don't invent; only capture explicit quoted keys above
        pass

    name = re.search(r"@name\s+(.+)", script)
    if name:
        out["name"] = name.group(1).strip()
    return out


@dataclass
class Song:
    id: str
    title: str
    artist: str
    album: str = "Unknown Album"
    album_id: str = ""
    artist_id: str = ""
    cover: str = ""
    duration: int = 0
    source: str = "tx"
    songmid: str = ""
    parent: str = ""
    bitrate: int = 320
    suffix: str = "mp3"
    content_type: str = "audio/mpeg"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_child(self) -> dict[str, Any]:
        # Always use song id as coverArt so MA resolves per-track art via getCoverArt,
        # instead of inheriting playlist/album cover.
        cover = self.id or "logo"
        # Keep song under its own album id, but avoid parent=playlist id.
        parent = self.album_id or self.id
        return {
            "id": self.id,
            "parent": parent,
            "isDir": False,
            "title": self.title,
            "name": self.title,
            "album": self.album,
            "albumId": self.album_id or self.id,
            "artist": self.artist,
            "artistId": self.artist_id or f"artist_{self.artist.split('、')[0]}",
            "track": 0,
            "year": 0,
            "coverArt": cover,
            "duration": self.duration,
            "bitRate": self.bitrate,
            "suffix": self.suffix,
            "contentType": self.content_type,
            "size": 0,
            "isVideo": False,
            "type": "music",
            "mediaType": "song",
        }


@dataclass
class Playlist:
    id: str
    name: str
    owner: str = "TX"
    cover: str = ""
    song_count: int = 0
    created: str = ""
    comment: str = ""
    source: str = "tx"
    dissid: str = ""

    def to_subsonic(self, songs: list[Song] | None = None) -> dict[str, Any]:
        cover = self.cover if is_valid_cover_url(self.cover) else self.id
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "owner": self.owner or "TX",
            "public": True,
            "songCount": self.song_count if songs is None else len(songs),
            "duration": sum(s.duration for s in (songs or [])),
            "created": self.created or "1970-01-01T00:00:00Z",
            "coverArt": cover,
            "comment": self.comment or "",
        }
        if songs is not None:
            data["entry"] = [s.to_child() for s in songs]
        return data


class MusicBackend:

    def __init__(
        self,
        session: ClientSession,
        search_source: str = "tx",
        music_source_js_url: str = "",
        preferred_quality: str = "flac",
    ) -> None:
        self._session = session
        self.search_source = (search_source or "tx").lower()
        self.music_source_js_url = (music_source_js_url or "").strip()
        self.preferred_quality = preferred_quality or "flac"
        self.song_cache: dict[str, Song] = {}
        self.cover_cache: dict[str, str] = {}
        self.playlist_cache: dict[str, Playlist] = {}
        self.playlist_songs_cache: dict[str, list[Song]] = {}
        self._timeout = ClientTimeout(total=20)
        self._source_cache: dict[str, Any] = {"url": None, "api_url": "", "api_key": "", "ts": 0}

    def cache_song(self, song: Song) -> None:
        self.song_cache[song.id] = song
        if is_valid_cover_url(song.cover):
            self.cover_cache[song.id] = song.cover
            if song.album_id:
                self.cover_cache[song.album_id] = song.cover

    async def _json_post(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        h = {
            "User-Agent": "QQMusic 14090508(android 12)",
            "Content-Type": "application/json",
            "Referer": "https://y.qq.com/",
        }
        if headers:
            h.update(headers)
        async with self._session.post(url, json=payload, headers=h, timeout=self._timeout) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def _json_get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
        h = {"User-Agent": UA, "Referer": "https://y.qq.com/"}
        if headers:
            h.update(headers)
        async with self._session.get(url, params=params, headers=h, timeout=self._timeout) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def search(self, query: str, limit: int = 20) -> list[Song]:
        source = self.search_source
        if source == "tx":
            return await self.search_tx(query, limit=limit)
        if source == "kg":
            return await self.search_kg(query, limit=limit)
        if source == "kw":
            return await self.search_kw(query, limit=limit)
        if source == "mg":
            return await self.search_mg(query, limit=limit)
        if source == "wy":
            return await self.search_wy(query, limit=limit)
        _LOGGER.warning("unknown search_source=%s, fallback tx", source)
        return await self.search_tx(query, limit=limit)

    async def search_tx(self, query: str, limit: int = 20) -> list[Song]:
        if not query:
            return []
        payloads = [
            {
                "comm": {"ct": 19, "cv": 1859, "uin": "0"},
                "req": {
                    "method": "DoSearchForQQMusicDesktop",
                    "module": "music.search.SearchCgiService",
                    "param": {
                        "query": query,
                        "page_num": 1,
                        "num_per_page": max(1, min(limit, 50)),
                        "search_type": 0,
                    },
                },
            },
            {
                "comm": {
                    "ct": "11",
                    "cv": "14090508",
                    "v": "14090508",
                    "tmeAppID": "qqmusic",
                    "uin": "0",
                },
                "req": {
                    "module": "music.search.SearchCgiService",
                    "method": "DoSearchForQQMusicMobile",
                    "param": {
                        "search_type": 0,
                        "query": query,
                        "page_num": 1,
                        "num_per_page": max(1, min(limit, 50)),
                        "highlight": 0,
                        "nqc_flag": 0,
                        "multi_zhida": 0,
                        "cat": 2,
                        "grp": 1,
                    },
                },
            },
        ]
        items: list[dict[str, Any]] = []
        last_err: Exception | None = None
        for payload in payloads:
            try:
                cand = await self._json_post("https://u.y.qq.com/cgi-bin/musicu.fcg", payload)
                if (cand or {}).get("code") != 0 or (cand.get("req") or {}).get("code") != 0:
                    last_err = RuntimeError(
                        f"tx search code={cand.get('code')} req={(cand.get('req') or {}).get('code')}"
                    )
                    continue
                body = (((cand.get("req") or {}).get("data") or {}).get("body")) or {}
                cand_items = body.get("song", {}).get("list") or body.get("item_song") or []
                if cand_items:
                    items = cand_items
                    break
                last_err = RuntimeError("tx search returned empty song list")
            except Exception as err:
                last_err = err
        if not items:
            _LOGGER.warning("TX search failed: %s", last_err)
            return []

        songs: list[Song] = []
        for item in items:
            mid = item.get("mid") or item.get("songmid")
            if not mid:
                continue
            album = item.get("album") or {}
            album_mid = album.get("mid") or ""
            album_name = album.get("name") or "Unknown Album"
            singers = item.get("singer") or []
            artist = "、".join([s.get("name", "") for s in singers if s.get("name")]) or "Unknown"
            cover = ""
            if album_mid and album_mid != "空":
                cover = f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{album_mid}.jpg"
            elif singers and singers[0].get("mid"):
                cover = f"https://y.gtimg.cn/music/photo_new/T001R500x500M000{singers[0]['mid']}.jpg"
            song = Song(
                id=f"tx_{mid}",
                title=(item.get("name") or item.get("title") or "Unknown") + (item.get("title_extra") or ""),
                artist=artist,
                album=album_name,
                album_id=f"alb_tx_{album_mid}" if album_mid else f"tx_{mid}",
                artist_id=f"artist_{artist.split('、')[0]}",
                cover=cover if is_valid_cover_url(cover) else "",
                duration=int(item.get("interval") or 0),
                source="tx",
                songmid=mid,
                parent=f"alb_tx_{album_mid}" if album_mid else f"tx_{mid}",
                bitrate=999 if (item.get("file") or {}).get("size_flac") else 320,
                suffix="flac" if (item.get("file") or {}).get("size_flac") else "mp3",
                content_type="audio/flac" if (item.get("file") or {}).get("size_flac") else "audio/mpeg",
                extra={"album_mid": album_mid, "media_mid": (item.get("file") or {}).get("media_mid")},
            )
            self.cache_song(song)
            songs.append(song)
        return songs

    async def search_tx_playlists(self, query: str, limit: int = 20) -> list[Playlist]:
        """Search QQ Music playlists (歌单)."""
        if not query:
            return []
        payload = {
            "comm": {"ct": 19, "cv": 1859, "uin": "0"},
            "req": {
                "method": "DoSearchForQQMusicDesktop",
                "module": "music.search.SearchCgiService",
                "param": {
                    "query": query,
                    "page_num": 1,
                    "num_per_page": max(1, min(limit, 30)),
                    "search_type": 3,
                },
            },
        }
        try:
            data = await self._json_post("https://u.y.qq.com/cgi-bin/musicu.fcg", payload)
            body = (((data.get("req") or {}).get("data") or {}).get("body")) or {}
            items = ((body.get("songlist") or {}).get("list")) or []
        except Exception as err:
            _LOGGER.warning("TX playlist search failed: %s", err)
            return []

        playlists: list[Playlist] = []
        for item in items:
            dissid = str(item.get("dissid") or item.get("id") or "")
            if not dissid:
                continue
            creator = item.get("creator") or {}
            owner = creator.get("name") or "TX"
            cover = item.get("imgurl") or item.get("logo") or ""
            created = item.get("createtime") or item.get("createTime") or "1970-01-01"
            if created and "T" not in str(created):
                created = f"{created}T00:00:00Z"
            pl = Playlist(
                id=f"pl_tx_{dissid}",
                name=item.get("dissname") or item.get("name") or f"歌单{dissid}",
                owner=owner,
                cover=cover if is_valid_cover_url(cover) else "",
                song_count=int(item.get("song_count") or item.get("songnum") or 0),
                created=str(created),
                comment=str(item.get("introduction") or item.get("desc") or "")[:200],
                source="tx",
                dissid=dissid,
            )
            self.playlist_cache[pl.id] = pl
            if is_valid_cover_url(pl.cover):
                self.cover_cache[pl.id] = pl.cover
            playlists.append(pl)
        return playlists

    async def get_playlist(self, playlist_id: str) -> tuple[Playlist | None, list[Song]]:
        """Get playlist metadata + songs. Currently TX only (pl_tx_*)."""
        if playlist_id in self.playlist_songs_cache and playlist_id in self.playlist_cache:
            return self.playlist_cache[playlist_id], self.playlist_songs_cache[playlist_id]

        dissid = ""
        if playlist_id.startswith("pl_tx_"):
            dissid = playlist_id[len("pl_tx_") :]
        elif playlist_id.isdigit():
            dissid = playlist_id
            playlist_id = f"pl_tx_{dissid}"
        else:
            return self.playlist_cache.get(playlist_id), self.playlist_songs_cache.get(playlist_id, [])

        url = (
            "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"
            f"?type=1&json=1&utf8=1&onlysong=0&new_format=1&disstid={dissid}"
            "&loginUin=0&hostUin=0&format=json&inCharset=utf8&outCharset=utf-8"
            "&notice=0&platform=yqq.json&needNewCode=0"
        )
        try:
            async with self._session.get(
                url,
                headers={
                    "User-Agent": UA,
                    "Referer": f"https://y.qq.com/n/ryqq/playlist/{dissid}",
                },
                timeout=self._timeout,
            ) as resp:
                data = await resp.json(content_type=None)
        except Exception as err:
            _LOGGER.warning("TX playlist detail failed %s: %s", playlist_id, err)
            return self.playlist_cache.get(playlist_id), []

        cdlist = data.get("cdlist") or []
        if not cdlist:
            return self.playlist_cache.get(playlist_id), []
        cd = cdlist[0]
        cover = cd.get("logo") or cd.get("imgurl") or ""
        owner = cd.get("nickname") or (cd.get("creator") or {}).get("name") or "TX"
        pl = Playlist(
            id=playlist_id,
            name=cd.get("dissname") or cd.get("diss_name") or f"歌单{dissid}",
            owner=owner,
            cover=cover if is_valid_cover_url(cover) else "",
            song_count=int(cd.get("songnum") or len(cd.get("songlist") or []) or 0),
            created=str(cd.get("ctime") or cd.get("createtime") or "1970-01-01T00:00:00Z"),
            comment=str(cd.get("desc") or "")[:200],
            source="tx",
            dissid=dissid,
        )
        songs: list[Song] = []
        for item in cd.get("songlist") or []:
            mid = item.get("mid") or item.get("songmid")
            if not mid:
                continue
            album = item.get("album") or {}
            album_mid = album.get("mid") or ""
            album_name = album.get("name") or "Unknown Album"
            singers = item.get("singer") or []
            artist = "、".join([s.get("name", "") for s in singers if s.get("name")]) or "Unknown"
            # Prefer album cover only. Never reuse playlist cover for every track.
            sc = ""
            album_pmid = album.get("pmid") or ""
            if album_mid and album_mid != "空":
                sc = f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{album_mid}.jpg"
            elif album_pmid:
                # some payloads only provide pmid
                mid2 = str(album_pmid).split("_")[0]
                if mid2 and mid2 != "空":
                    sc = f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{mid2}.jpg"
            if not is_valid_cover_url(sc) and singers and singers[0].get("mid"):
                sc = f"https://y.gtimg.cn/music/photo_new/T001R500x500M000{singers[0]['mid']}.jpg"
            file_info = item.get("file") or {}
            is_flac = bool(file_info.get("size_flac"))
            song = Song(
                id=f"tx_{mid}",
                title=item.get("title") or item.get("name") or "Unknown",
                artist=artist,
                album=album_name,
                # Keep album_id as real album, but never playlist id.
                album_id=f"alb_tx_{album_mid}" if album_mid else f"tx_{mid}",
                artist_id=f"artist_{artist.split('、')[0]}",
                # Song-own cover URL used by getCoverArt(tx_mid). Never playlist cover.
                cover=sc if is_valid_cover_url(sc) else "",
                duration=int(item.get("interval") or 0),
                source="tx",
                songmid=mid,
                parent=f"alb_tx_{album_mid}" if album_mid else f"tx_{mid}",
                bitrate=999 if is_flac else 320,
                suffix="flac" if is_flac else "mp3",
                content_type="audio/flac" if is_flac else "audio/mpeg",
                extra={"album_mid": album_mid, "media_mid": file_info.get("media_mid"), "playlist_id": playlist_id},
            )
            self.cache_song(song)
            songs.append(song)
        pl.song_count = len(songs) or pl.song_count
        self.playlist_cache[playlist_id] = pl
        self.playlist_songs_cache[playlist_id] = songs
        if is_valid_cover_url(pl.cover):
            self.cover_cache[playlist_id] = pl.cover
        return pl, songs

    async def list_playlists(self) -> list[Playlist]:
        return list(self.playlist_cache.values())

    async def search_kg(self, query: str, limit: int = 20) -> list[Song]:

        if not query:
            return []
        url = (
            "https://songsearch.kugou.com/song_search_v2"
            f"?keyword={quote(query)}&page=1&pagesize={max(1, min(limit, 50))}"
            "&userid=0&clientver=&platform=WebFilter&filter=2&iscorrection=1&privilege_filter=0&area_code=1"
        )
        try:
            data = await self._json_get(url, headers={"Referer": "https://www.kugou.com/", "User-Agent": UA})
            items = ((data.get("data") or {}).get("lists")) or []
        except Exception as err:
            _LOGGER.warning("KG search failed: %s", err)
            return []
        songs: list[Song] = []
        for item in items:
            audio_id = item.get("Audioid") or item.get("audio_id") or ""
            file_hash = item.get("FileHash") or item.get("fileHash") or ""
            if not audio_id and not file_hash:
                continue
            songmid = str(audio_id or file_hash)
            album_id = str(item.get("AlbumID") or item.get("album_id") or "")
            title = item.get("SongName") or item.get("songname") or "Unknown"
            artist = item.get("SingerName") or ""
            if not artist and item.get("Singers"):
                artist = "、".join([s.get("name", "") for s in item.get("Singers") or [] if s.get("name")])
            cover = ""
            if item.get("Image"):
                cover = str(item["Image"]).replace("{size}", "240")
            elif (item.get("trans_param") or {}).get("union_cover"):
                cover = str(item["trans_param"]["union_cover"]).replace("{size}", "240")
            duration = int(item.get("Duration") or item.get("duration") or 0)
            is_flac = bool(item.get("SQFileSize"))
            song = Song(
                id=f"kg_{songmid}",
                title=title,
                artist=artist or "Unknown",
                album=item.get("AlbumName") or "Unknown Album",
                album_id=f"alb_kg_{album_id}" if album_id else f"kg_{songmid}",
                artist_id=f"artist_{ (artist or 'Unknown').split('、')[0] }",
                cover=cover if is_valid_cover_url(cover) else "",
                duration=duration,
                source="kg",
                songmid=songmid,
                parent=f"alb_kg_{album_id}" if album_id else f"kg_{songmid}",
                bitrate=999 if is_flac else 320,
                suffix="flac" if is_flac else "mp3",
                content_type="audio/flac" if is_flac else "audio/mpeg",
                extra={"hash": file_hash, "album_id": album_id},
            )
            self.cache_song(song)
            songs.append(song)
        return songs

    async def search_kw(self, query: str, limit: int = 20) -> list[Song]:
        if not query:
            return []
        url = (
            "http://search.kuwo.cn/r.s?client=kt"
            f"&all={quote(query)}&pn=0&rn={max(1, min(limit, 50))}"
            "&uid=794762570&ver=kwplayer_ar_9.2.2.1&vipver=1&show_copyright_off=1&newver=1"
            "&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vermerge=1&mobi=1&issubtitle=1"
        )
        try:
            data = await self._json_get(url, headers={"Referer": "https://www.kuwo.cn/", "User-Agent": UA})
            items = data.get("abslist") or []
        except Exception as err:
            _LOGGER.warning("KW search failed: %s", err)
            return []
        songs: list[Song] = []
        for item in items:
            rid = str(item.get("MUSICRID") or item.get("DC_TARGETID") or "")
            rid = rid.replace("MUSIC_", "")
            if not rid:
                continue
            title = item.get("SONGNAME") or item.get("NAME") or "Unknown"
            artist = item.get("ARTIST") or "Unknown"
            album = item.get("ALBUM") or "Unknown Album"
            album_id = str(item.get("ALBUMID") or "")
            duration = parse_duration(item.get("DURATION") or item.get("duration") or 0)
            cover = ""
            if item.get("web_albumpic_short"):
                cover = f"https://img4.kuwo.cn/star/albumcover/500{item['web_albumpic_short']}"
            elif item.get("web_artistpic_short"):
                cover = f"https://img4.kuwo.cn/star/starheads/500{item['web_artistpic_short']}"
            song = Song(
                id=f"kw_{rid}",
                title=title,
                artist=artist,
                album=album,
                album_id=f"alb_kw_{album_id}" if album_id else f"kw_{rid}",
                artist_id=f"artist_{artist.split('&')[0].split('、')[0]}",
                cover=cover if is_valid_cover_url(cover) else "",
                duration=duration,
                source="kw",
                songmid=rid,
                parent=f"alb_kw_{album_id}" if album_id else f"kw_{rid}",
                bitrate=320,
                suffix="mp3",
                content_type="audio/mpeg",
            )
            self.cache_song(song)
            songs.append(song)
        return songs

    async def search_mg(self, query: str, limit: int = 20) -> list[Song]:
        if not query:
            return []
        # Public migu search (simple)
        url = (
            "https://app.c.nf.migu.cn/MIGUM2.0/v1.0/content/search_all.do"
            f"?text={quote(query)}&pageNo=1&pageSize={max(1, min(limit, 50))}"
            "&searchSwitch=%7B%22song%22%3A1%2C%22album%22%3A0%2C%22singer%22%3A0%2C%22tagSong%22%3A0%2C%22mvSong%22%3A0%2C%22songlist%22%3A0%2C%22bestShow%22%3A0%7D"
        )
        try:
            data = await self._json_get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://m.music.migu.cn/",
                    "channel": "0146951",
                },
            )
            items = (((data.get("songResultData") or {}).get("result")) or data.get("songs") or [])
            if not items and isinstance((data.get("songResultData") or {}).get("resultList"), list):
                # nested list form
                nested = data["songResultData"]["resultList"]
                items = [x for group in nested for x in (group or [])]
        except Exception as err:
            _LOGGER.warning("MG search failed: %s", err)
            return []

        songs: list[Song] = []
        for item in items:
            sid = str(item.get("id") or item.get("songId") or item.get("contentId") or "")
            copyright_id = str(item.get("copyrightId") or "")
            if not sid and not copyright_id:
                continue
            songmid = sid or copyright_id
            title = item.get("name") or item.get("songName") or "Unknown"
            singers = item.get("singers") or item.get("singerList") or []
            if isinstance(singers, list):
                artist = "、".join([s.get("name", "") for s in singers if isinstance(s, dict) and s.get("name")]) or "Unknown"
            else:
                artist = str(item.get("singer") or "Unknown")
            album = (item.get("albums") or [{}])
            album_name = "Unknown Album"
            album_id = ""
            if isinstance(album, list) and album:
                album_name = album[0].get("name") or album_name
                album_id = str(album[0].get("id") or "")
            elif item.get("album"):
                album_name = item.get("album") or album_name
                album_id = str(item.get("albumId") or "")
            cover = ""
            imgs = item.get("imgItems") or []
            if imgs and isinstance(imgs, list):
                cover = imgs[0].get("img") or ""
            cover = cover or item.get("img3") or item.get("img2") or item.get("img1") or item.get("cover") or ""
            if cover and cover.startswith("/"):
                cover = "http://d.musicapp.migu.cn" + cover
            duration = parse_duration(item.get("duration") or item.get("length") or 0)
            song = Song(
                id=f"mg_{songmid}",
                title=title,
                artist=artist,
                album=album_name,
                album_id=f"alb_mg_{album_id}" if album_id else f"mg_{songmid}",
                artist_id=f"artist_{artist.split('、')[0]}",
                cover=cover if is_valid_cover_url(cover) else "",
                duration=duration,
                source="mg",
                songmid=songmid,
                parent=f"alb_mg_{album_id}" if album_id else f"mg_{songmid}",
                bitrate=320,
                suffix="mp3",
                content_type="audio/mpeg",
                extra={"copyrightId": copyright_id},
            )
            self.cache_song(song)
            songs.append(song)
        return songs

    async def search_wy(self, query: str, limit: int = 20) -> list[Song]:
        """Netease cloud search via public cloudsearch endpoint (best-effort)."""
        if not query:
            return []
        url = "https://music.163.com/api/cloudsearch/pc"
        params = {
            "s": query,
            "type": 1,
            "limit": max(1, min(limit, 50)),
            "offset": 0,
            "total": "true",
        }
        try:
            data = await self._json_get(
                url,
                params=params,
                headers={
                    "User-Agent": UA,
                    "Referer": "https://music.163.com/",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            items = ((data.get("result") or {}).get("songs")) or []
        except Exception as err:
            _LOGGER.warning("WY search failed: %s", err)
            return []
        songs: list[Song] = []
        for item in items:
            sid = str(item.get("id") or "")
            if not sid:
                continue
            artists = item.get("ar") or item.get("artists") or []
            artist = "、".join([a.get("name", "") for a in artists if a.get("name")]) or "Unknown"
            al = item.get("al") or item.get("album") or {}
            album_name = al.get("name") or "Unknown Album"
            album_id = str(al.get("id") or "")
            cover = al.get("picUrl") or ""
            duration = int((item.get("dt") or item.get("duration") or 0) / 1000)
            song = Song(
                id=f"wy_{sid}",
                title=item.get("name") or "Unknown",
                artist=artist,
                album=album_name,
                album_id=f"alb_wy_{album_id}" if album_id else f"wy_{sid}",
                artist_id=f"artist_{artist.split('、')[0]}",
                cover=cover if is_valid_cover_url(cover) else "",
                duration=duration,
                source="wy",
                songmid=sid,
                parent=f"alb_wy_{album_id}" if album_id else f"wy_{sid}",
                bitrate=320,
                suffix="mp3",
                content_type="audio/mpeg",
            )
            self.cache_song(song)
            songs.append(song)
        return songs

    async def get_song(self, song_id: str) -> Song | None:
        if song_id in self.song_cache:
            return self.song_cache[song_id]
        if song_id.startswith("tx_"):
            mid = song_id[3:]
            payload = {
                "comm": {"ct": "19", "cv": "1859", "uin": "0"},
                "req": {
                    "module": "music.pf_song_detail_svr",
                    "method": "get_song_detail_yqq",
                    "param": {"song_type": 0, "song_mid": mid},
                },
            }
            try:
                data = await self._json_post("https://u.y.qq.com/cgi-bin/musicu.fcg", payload)
                item = data["req"]["data"]["track_info"]
            except Exception as err:
                _LOGGER.warning("TX get_song failed %s: %s", song_id, err)
                hits = await self.search_tx(mid, limit=10)
                for h in hits:
                    if h.songmid == mid or h.id == song_id:
                        return h
                return None
            album = item.get("album") or {}
            album_mid = album.get("mid") or ""
            album_name = album.get("name") or "Unknown Album"
            singers = item.get("singer") or []
            artist = "、".join([s.get("name", "") for s in singers if s.get("name")]) or "Unknown"
            cover = ""
            if album_mid and album_mid != "空":
                cover = f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{album_mid}.jpg"
            file_info = item.get("file") or {}
            is_flac = bool(file_info.get("size_flac"))
            song = Song(
                id=f"tx_{item.get('mid') or mid}",
                title=item.get("title") or item.get("name") or "Unknown",
                artist=artist,
                album=album_name,
                album_id=f"alb_tx_{album_mid}" if album_mid else f"tx_{mid}",
                artist_id=f"artist_{artist.split('、')[0]}",
                cover=cover if is_valid_cover_url(cover) else "",
                duration=int(item.get("interval") or 0),
                source="tx",
                songmid=item.get("mid") or mid,
                parent=f"alb_tx_{album_mid}" if album_mid else f"tx_{mid}",
                bitrate=999 if is_flac else 320,
                suffix="flac" if is_flac else "mp3",
                content_type="audio/flac" if is_flac else "audio/mpeg",
                extra={"album_mid": album_mid, "media_mid": file_info.get("media_mid")},
            )
            self.cache_song(song)
            return song

        # non-tx: reconstruct from id prefix if possible via search is weak; return cache-only miss
        for prefix, src in (("kg_", "kg"), ("kw_", "kw"), ("mg_", "mg"), ("wy_", "wy")):
            if song_id.startswith(prefix):
                # create minimal shell so stream can still use songmid
                mid = song_id[len(prefix) :]
                song = Song(
                    id=song_id,
                    title=mid,
                    artist="Unknown",
                    source=src,
                    songmid=mid,
                    album_id=song_id,
                    parent=song_id,
                )
                self.cache_song(song)
                return song
        return None

    async def get_album_songs(self, album_id: str) -> tuple[str, list[Song]]:
        cached = [s for s in self.song_cache.values() if s.album_id == album_id]
        if cached:
            return cached[0].album, cached
        song = await self.get_song(album_id)
        if song:
            return song.album, [song]
        return "Album", []

    async def get_lyrics(self, song_id: str, *, fetch: bool = True) -> str:
        """Return lyrics. fetch=False makes an instant empty result (used for bulk album loads)."""
        if not fetch:
            return ""
        song = await self.get_song(song_id)
        if not song:
            return ""
        if song.source == "tx":
            try:
                url = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
                params = {
                    "songmid": song.songmid,
                    "pcachetime": str(int(time.time() * 1000)),
                    "g_tk": "5381",
                    "loginUin": "0",
                    "hostUin": "0",
                    "format": "json",
                    "inCharset": "utf8",
                    "outCharset": "utf-8",
                    "notice": "0",
                    "platform": "yqq",
                    "needNewCode": "0",
                }
                async with self._session.get(
                    url,
                    params=params,
                    headers={"User-Agent": UA, "Referer": "https://y.qq.com/"},
                    timeout=self._timeout,
                ) as resp:
                    data = await resp.json(content_type=None)
                lyric_b64 = data.get("lyric") or ""
                if not lyric_b64:
                    return ""
                return base64.b64decode(lyric_b64).decode("utf-8", errors="ignore")
            except Exception as err:
                _LOGGER.warning("lyric failed %s: %s", song_id, err)
                return ""
        # other sources: empty ok (MA tolerates empty lyrics)
        return ""

    async def _ensure_music_source_from_js(self) -> tuple[str, str]:
        """Return (api_url, api_key) parsed from music_source_js_url."""
        js_url = self.music_source_js_url
        if not js_url:
            return "", ""
        now = time.time()
        if self._source_cache.get("url") == js_url and now - float(self._source_cache.get("ts") or 0) < 3600:
            return str(self._source_cache.get("api_url") or ""), str(self._source_cache.get("api_key") or "")

        script = ""
        candidates = [js_url]
        if "raw.githubusercontent.com" in js_url:
            candidates.append("https://ghproxy.net/" + js_url)
        last_err: Exception | None = None
        for u in candidates:
            try:
                async with self._session.get(u, headers={"User-Agent": UA}, timeout=ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        last_err = RuntimeError(f"status {resp.status}")
                        continue
                    script = await resp.text()
                    if script:
                        break
            except Exception as err:
                last_err = err
        if not script:
            _LOGGER.warning("fetch music source js failed: %s", last_err)
            return "", ""

        parsed = parse_music_source_js(script)
        api_url = (parsed.get("api_url") or "").rstrip("/")
        api_key = parsed.get("api_key") or ""
        self._source_cache = {"url": js_url, "api_url": api_url, "api_key": api_key, "ts": now, "name": parsed.get("name")}
        if not api_url:
            _LOGGER.warning(
                "music source js has no extractable API_URL (maybe obfuscated). name=%s",
                parsed.get("name"),
            )
        else:
            _LOGGER.info("loaded music source from js: %s api=%s key=%s", parsed.get("name"), api_url, "set" if api_key else "empty")
        return api_url, api_key

    def _quality_candidates(self, song: Song | None = None) -> list[str]:
        preferred = (self.preferred_quality or "flac").lower()
        base = ["flac", "320k", "128k", "flac24bit", "hires"]
        return [preferred] + [q for q in base if q != preferred]

    async def resolve_music_url_api(self, song: Song) -> str | None:
        api_url, api_key = await self._ensure_music_source_from_js()
        if not api_url:
            return None
        song_id = song.songmid or song.id
        # kg sources usually need hash
        if song.source == "kg":
            song_id = (song.extra or {}).get("hash") or song.songmid or song_id
        if isinstance(song_id, str) and song_id.startswith(f"{song.source}_"):
            song_id = song_id[len(song.source) + 1 :]
        source = song.source or self.search_source or "tx"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "lx-music-request/2.0.0",
        }
        if api_key:
            headers["X-API-Key"] = api_key
        last_err: Exception | None = None
        for quality in self._quality_candidates(song):
            url = f"{api_url}/url"
            params = {"source": source, "songId": song_id, "quality": quality}
            try:
                async with self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self._timeout,
                    allow_redirects=True,
                ) as resp:
                    if resp.status in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("Location")
                        if loc:
                            return loc
                    data = await resp.json(content_type=None)
                code = data.get("code")
                if code in (200, "200") and data.get("url"):
                    return str(data["url"])
                last_err = RuntimeError(f"code={code} msg={data.get('message')}")
            except Exception as err:
                last_err = err
                continue
        _LOGGER.warning("music_url_api failed for %s: %s", song.id, last_err)
        return None

    async def resolve_stream_url(
        self,
        song_id: str,
        username: str | None = None,
        password: str | None = None,
    ) -> str | None:
        song = await self.get_song(song_id)
        if not song:
            return None
        return await self.resolve_music_url_api(song)

    async def fetch_cover_bytes(self, cover_id: str) -> tuple[bytes, str] | None:
        url = None
        if is_valid_cover_url(cover_id):
            url = cover_id
        elif cover_id in self.cover_cache:
            url = self.cover_cache[cover_id]
        elif cover_id.startswith("alb_tx_"):
            mid = cover_id.replace("alb_tx_", "", 1)
            url = f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{mid}.jpg"
        elif cover_id.startswith("tx_"):
            song = await self.get_song(cover_id)
            if song and is_valid_cover_url(song.cover):
                url = song.cover
            elif song and song.songmid:
                # last resort: QQ album-less song still may have mid-based album art unknown;
                # keep empty rather than playlist cover.
                url = None
        elif cover_id.startswith("pl_tx_"):
            pl, _ = await self.get_playlist(cover_id)
            if pl and is_valid_cover_url(pl.cover):
                url = pl.cover
        else:
            song = self.song_cache.get(cover_id)
            if song and is_valid_cover_url(song.cover):
                url = song.cover

        if not is_valid_cover_url(url):
            return None
        try:
            async with self._session.get(url, headers={"User-Agent": UA}, timeout=self._timeout) as resp:
                if resp.status != 200:
                    return None
                ctype = resp.headers.get("Content-Type", "image/jpeg")
                if not ctype.startswith("image/"):
                    return None
                data = await resp.read()
                if not data:
                    return None
                return data, ctype
        except Exception as err:
            _LOGGER.warning("cover fetch failed %s: %s", cover_id, err)
            return None
