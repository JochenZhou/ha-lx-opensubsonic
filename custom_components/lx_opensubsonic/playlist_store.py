"""Imported playlist storage and multi-source playlist import helpers."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .music_backend import Song, UA, is_valid_cover_url, parse_duration

_LOGGER = logging.getLogger(__name__)


@dataclass
class ImportedTrack:
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
    extra: dict[str, Any] = field(default_factory=dict)

    def to_song(self) -> Song:
        return Song(
            id=self.id,
            title=self.title,
            artist=self.artist,
            album=self.album,
            album_id=self.album_id or self.id,
            artist_id=self.artist_id or f"artist_{self.artist.split('、')[0]}",
            cover=self.cover,
            duration=self.duration,
            source=self.source,
            songmid=self.songmid or self.id.split("_", 1)[-1],
            parent=self.album_id or self.id,
            extra=dict(self.extra or {}),
        )

    def to_child(self) -> dict[str, Any]:
        return self.to_song().to_child()


@dataclass
class ImportedPlaylist:
    id: str
    name: str
    source: str
    remote_id: str
    cover: str = ""
    owner: str = ""
    comment: str = ""
    song_count: int = 0
    created: str = ""
    updated_at: str = ""
    tracks: list[ImportedTrack] = field(default_factory=list)

    def to_subsonic(self, with_tracks: bool = False) -> dict[str, Any]:
        cover = self.cover if is_valid_cover_url(self.cover) else self.id
        # libopensonic Playlist requires created + changed as ISO-like strings.
        created = self._iso_ts(self.created)
        changed = self._iso_ts(self.updated_at) or created
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "owner": self.owner or self.source.upper(),
            "public": True,
            "songCount": self.song_count or len(self.tracks),
            "duration": sum(t.duration for t in self.tracks),
            "created": created,
            "changed": changed,
            "coverArt": cover,
            "comment": self.comment or "",
        }
        if with_tracks:
            data["entry"] = [t.to_child() for t in self.tracks]
        return data

    @staticmethod
    def _iso_ts(value: str | None) -> str:
        """Normalize playlist timestamps for libopensonic/MA."""
        raw = (value or "").strip()
        if not raw:
            return "1970-01-01T00:00:00Z"
        # QQ ctime is often unix seconds as digit string.
        if raw.isdigit():
            try:
                from datetime import datetime, timezone

                return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                return "1970-01-01T00:00:00Z"
        # already ISO-ish
        if "T" in raw:
            return raw if raw.endswith("Z") or "+" in raw[10:] else f"{raw}Z"
        return "1970-01-01T00:00:00Z"


class PlaylistStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.playlists: dict[str, ImportedPlaylist] = {}
        self.selected_id: str = ""
        self.last_input: str = ""
        self.last_source: str = "auto"
        self.last_message: str = ""

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as err:
            _LOGGER.warning("load playlist store failed: %s", err)
            return
        self.selected_id = raw.get("selected_id") or ""
        self.last_input = raw.get("last_input") or ""
        self.last_source = raw.get("last_source") or "auto"
        self.last_message = raw.get("last_message") or ""
        for item in raw.get("playlists") or []:
            tracks = [ImportedTrack(**t) for t in (item.get("tracks") or [])]
            pl = ImportedPlaylist(
                id=item["id"],
                name=item.get("name") or item["id"],
                source=item.get("source") or "tx",
                remote_id=item.get("remote_id") or "",
                cover=item.get("cover") or "",
                owner=item.get("owner") or "",
                comment=item.get("comment") or "",
                song_count=int(item.get("song_count") or len(tracks)),
                created=item.get("created") or "",
                updated_at=item.get("updated_at") or "",
                tracks=tracks,
            )
            self.playlists[pl.id] = pl
        if self.selected_id not in self.playlists:
            self.selected_id = next(iter(self.playlists), "")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "selected_id": self.selected_id,
            "last_input": self.last_input,
            "last_source": self.last_source,
            "last_message": self.last_message,
            "playlists": [
                {
                    **{k: v for k, v in asdict(pl).items() if k != "tracks"},
                    "tracks": [asdict(t) for t in pl.tracks],
                }
                for pl in self.playlists.values()
            ],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def async_save(self, hass) -> None:
        await hass.async_add_executor_job(self.save)

    async def async_load(self, hass) -> None:
        await hass.async_add_executor_job(self.load)

    def list_playlists(self) -> list[ImportedPlaylist]:
        # stable newest-updated first
        return sorted(self.playlists.values(), key=lambda p: p.updated_at or p.created or p.name, reverse=True)

    def get(self, playlist_id: str) -> ImportedPlaylist | None:
        return self.playlists.get(playlist_id)

    def names(self) -> list[str]:
        return [p.name for p in self.list_playlists()]

    def selected(self) -> ImportedPlaylist | None:
        if self.selected_id and self.selected_id in self.playlists:
            return self.playlists[self.selected_id]
        items = self.list_playlists()
        return items[0] if items else None

    def set_selected_by_name(self, name: str) -> None:
        for pl in self.playlists.values():
            if pl.name == name:
                self.selected_id = pl.id
                return

    def upsert(self, pl: ImportedPlaylist) -> None:
        self.playlists[pl.id] = pl
        self.selected_id = pl.id

    def delete_selected(self) -> str:
        pl = self.selected()
        if not pl:
            self.last_message = "没有可删除的歌单"
            return self.last_message
        self.playlists.pop(pl.id, None)
        items = self.list_playlists()
        self.selected_id = items[0].id if items else ""
        self.last_message = f"已删除《{pl.name}》"
        return self.last_message

    def clear_all(self) -> str:
        n = len(self.playlists)
        self.playlists.clear()
        self.selected_id = ""
        self.last_message = f"已清空全部歌单（{n}）"
        return self.last_message


_SUPPORTED_SOURCES = ("tx", "wy", "kg", "kw", "mg")
_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 10; HLK-AL00) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
_IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
)

_ID_PATTERNS = {
    "tx": [
        re.compile(r"playlist/(\d+)", re.I),
        re.compile(r"[?&]id=(\d+)"),
        re.compile(r"disstid=(\d+)", re.I),
        re.compile(r"^(\d{6,})$"),
    ],
    "wy": [
        re.compile(r"[?&#]id=(\d+)", re.I),
        re.compile(r"/playlist/(\d+)", re.I),
        re.compile(r"^(\d{6,})$"),
    ],
    "kg": [
        re.compile(r"special/single/(\d+)", re.I),
        re.compile(r"plist/list/(\d+)", re.I),
        re.compile(r"specialid[=_](\d+)", re.I),
        re.compile(r"/(\d+)\.html", re.I),
        re.compile(r"^(\d{4,})$"),
    ],
    "kw": [
        re.compile(r"playlist(?:_detail)?/(\d+)", re.I),
        re.compile(r"[?&]pid=(\d+)", re.I),
        re.compile(r"^(\d{6,})$"),
    ],
    "mg": [
        re.compile(r"playlistId=(\d+)", re.I),
        re.compile(r"[?&]id=(\d+)", re.I),
        re.compile(r"/playlist/(\d+)", re.I),
        re.compile(r"^(\d{6,})$"),
    ],
}


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _track(
    *,
    source: str,
    songmid: str,
    title: str,
    artist: str,
    album: str = "Unknown Album",
    album_id: str = "",
    cover: str = "",
    duration: int = 0,
    extra: dict[str, Any] | None = None,
) -> ImportedTrack:
    artist = artist or "Unknown"
    return ImportedTrack(
        id=f"{source}_{songmid}",
        title=title or "Unknown",
        artist=artist,
        album=album or "Unknown Album",
        album_id=album_id or f"alb_{source}_{songmid}",
        artist_id=f"artist_{artist.split('、')[0]}",
        cover=cover if is_valid_cover_url(cover) else "",
        duration=int(duration or 0),
        source=source,
        songmid=str(songmid),
        extra=dict(extra or {}),
    )


def detect_source_and_id(text: str, preferred: str = "auto") -> tuple[str, str]:
    s = (text or "").strip()
    if not s:
        raise ValueError("请输入歌单链接或ID")
    low = s.lower()
    if preferred and preferred != "auto":
        src = preferred
    elif "y.qq.com" in low or "qq.com" in low:
        src = "tx"
    elif "music.163.com" in low or "163.com" in low or "163cn.tv" in low:
        src = "wy"
    elif "kugou.com" in low:
        src = "kg"
    elif "kuwo.cn" in low:
        src = "kw"
    elif "migu.cn" in low or "nf.migu.cn" in low:
        src = "mg"
    else:
        src = "tx"  # bare numeric id defaults to QQ
    if src not in _SUPPORTED_SOURCES:
        raise ValueError(f"不支持的歌单平台: {src}")
    for pat in _ID_PATTERNS.get(src, []):
        m = pat.search(s)
        if m:
            return src, m.group(1)
    m = re.search(r"(\d{4,})", s)
    if m:
        return src, m.group(1)
    raise ValueError("无法解析歌单ID，请检查链接")


async def fetch_tx_playlist(session: ClientSession, remote_id: str) -> ImportedPlaylist:
    url = (
        "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"
        f"?type=1&json=1&utf8=1&onlysong=0&new_format=1&disstid={remote_id}"
        "&loginUin=0&hostUin=0&format=json&inCharset=utf8&outCharset=utf-8"
        "&notice=0&platform=yqq.json&needNewCode=0"
    )
    timeout = ClientTimeout(total=30)
    async with session.get(
        url,
        headers={"User-Agent": UA, "Referer": f"https://y.qq.com/n/ryqq/playlist/{remote_id}"},
        timeout=timeout,
    ) as resp:
        data = await resp.json(content_type=None)
    cdlist = data.get("cdlist") or []
    if not cdlist:
        raise ValueError("未获取到QQ歌单详情")
    cd = cdlist[0]
    cover = cd.get("logo") or cd.get("imgurl") or ""
    owner = cd.get("nickname") or (cd.get("creator") or {}).get("name") or "TX"
    tracks: list[ImportedTrack] = []
    for item in cd.get("songlist") or []:
        mid = item.get("mid") or item.get("songmid")
        if not mid:
            continue
        album = item.get("album") or {}
        album_mid = album.get("mid") or ""
        album_name = album.get("name") or "Unknown Album"
        singers = item.get("singer") or []
        artist = "、".join([s.get("name", "") for s in singers if s.get("name")]) or "Unknown"
        sc = ""
        if album_mid and album_mid != "空":
            sc = f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{album_mid}.jpg"
        tracks.append(
            _track(
                source="tx",
                songmid=mid,
                title=item.get("title") or item.get("name") or "Unknown",
                artist=artist,
                album=album_name,
                album_id=f"alb_tx_{album_mid}" if album_mid else f"tx_{mid}",
                cover=sc,
                duration=int(item.get("interval") or 0),
                extra={"album_mid": album_mid, "media_mid": (item.get("file") or {}).get("media_mid")},
            )
        )
    if not tracks:
        raise ValueError("歌单为空或解析失败")
    now = _now_iso()
    return ImportedPlaylist(
        id=f"pl_tx_{remote_id}",
        name=cd.get("dissname") or cd.get("diss_name") or f"QQ歌单{remote_id}",
        source="tx",
        remote_id=str(remote_id),
        cover=cover if is_valid_cover_url(cover) else "",
        owner=owner,
        comment=str(cd.get("desc") or "")[:200],
        song_count=len(tracks),
        created=str(cd.get("ctime") or cd.get("createtime") or now),
        updated_at=now,
        tracks=tracks,
    )


async def fetch_wy_playlist(session: ClientSession, remote_id: str) -> ImportedPlaylist:
    url = f"https://music.163.com/api/v6/playlist/detail?id={remote_id}&n=1000"
    timeout = ClientTimeout(total=30)
    async with session.get(
        url,
        headers={"User-Agent": UA, "Referer": "https://music.163.com/"},
        timeout=timeout,
    ) as resp:
        data = await resp.json(content_type=None)
    if int(data.get("code") or 0) != 200:
        raise ValueError(f"未获取到网易云歌单详情: {data.get('code')}")
    pl = data.get("playlist") or {}
    tracks: list[ImportedTrack] = []
    for item in pl.get("tracks") or []:
        sid = item.get("id")
        if not sid:
            continue
        artists = item.get("ar") or item.get("artists") or []
        artist = "、".join([a.get("name", "") for a in artists if a.get("name")]) or "Unknown"
        album = item.get("al") or item.get("album") or {}
        album_id = str(album.get("id") or "")
        cover = album.get("picUrl") or ""
        duration_ms = int(item.get("dt") or item.get("duration") or 0)
        tracks.append(
            _track(
                source="wy",
                songmid=str(sid),
                title=item.get("name") or "Unknown",
                artist=artist,
                album=album.get("name") or "Unknown Album",
                album_id=f"alb_wy_{album_id}" if album_id else f"wy_{sid}",
                cover=cover,
                duration=max(1, duration_ms // 1000) if duration_ms else 0,
            )
        )
    # fallback: only trackIds present
    if not tracks:
        for tid in pl.get("trackIds") or []:
            sid = tid.get("id") if isinstance(tid, dict) else tid
            if not sid:
                continue
            tracks.append(_track(source="wy", songmid=str(sid), title=str(sid), artist="Unknown"))
    if not tracks:
        raise ValueError("网易云歌单为空或解析失败")
    now = _now_iso()
    creator = (pl.get("creator") or {}).get("nickname") or "WY"
    created = pl.get("createTime")
    created_s = str(int(created) // 1000) if isinstance(created, (int, float)) else str(created or now)
    return ImportedPlaylist(
        id=f"pl_wy_{remote_id}",
        name=pl.get("name") or f"网易云歌单{remote_id}",
        source="wy",
        remote_id=str(remote_id),
        cover=pl.get("coverImgUrl") if is_valid_cover_url(pl.get("coverImgUrl") or "") else "",
        owner=creator,
        comment=str(pl.get("description") or "")[:200],
        song_count=len(tracks),
        created=created_s,
        updated_at=now,
        tracks=tracks,
    )


async def fetch_kg_playlist(session: ClientSession, remote_id: str) -> ImportedPlaylist:
    url = f"https://m.kugou.com/plist/list/{remote_id}/?json=true"
    timeout = ClientTimeout(total=30)
    async with session.get(url, headers={"User-Agent": _MOBILE_UA}, timeout=timeout) as resp:
        data = await resp.json(content_type=None)
    info = ((data.get("info") or {}).get("list") or {}) if isinstance(data.get("info"), dict) else {}
    songs = (((data.get("list") or {}).get("list") or {}).get("info") or []) if isinstance(data.get("list"), dict) else []
    tracks: list[ImportedTrack] = []
    for item in songs:
        h = item.get("hash") or item.get("320hash") or item.get("sqhash")
        if not h:
            continue
        filename = item.get("filename") or ""
        if " - " in filename:
            artist, title = filename.split(" - ", 1)
        else:
            artist, title = "Unknown", filename or "Unknown"
        album_id = str(item.get("album_id") or "")
        cover = ""
        tp = item.get("trans_param") or {}
        if tp.get("union_cover"):
            cover = str(tp["union_cover"]).replace("{size}", "400")
        tracks.append(
            _track(
                source="kg",
                songmid=str(h).lower(),
                title=title,
                artist=artist,
                album=item.get("remark") or item.get("album_name") or "Unknown Album",
                album_id=f"alb_kg_{album_id}" if album_id else f"kg_{h.lower()}",
                cover=cover,
                duration=int(item.get("duration") or 0),
                extra={"hash": str(h).lower(), "album_id": album_id},
            )
        )
    if not tracks:
        raise ValueError("酷狗歌单为空或解析失败")
    now = _now_iso()
    cover = str(info.get("imgurl") or "").replace("{size}", "400")
    return ImportedPlaylist(
        id=f"pl_kg_{remote_id}",
        name=info.get("specialname") or f"酷狗歌单{remote_id}",
        source="kg",
        remote_id=str(remote_id),
        cover=cover if is_valid_cover_url(cover) else "",
        owner=info.get("nickname") or "KG",
        comment=str(info.get("intro") or "")[:200],
        song_count=len(tracks),
        created=str(info.get("publishtime") or now),
        updated_at=now,
        tracks=tracks,
    )


async def fetch_kw_playlist(session: ClientSession, remote_id: str) -> ImportedPlaylist:
    url = (
        "http://nplserver.kuwo.cn/pl.svc?op=getlistinfo"
        f"&pid={remote_id}&pn=0&rn=1000&encode=utf8&keyset=pl2012"
        "&identity=kuwo&pcmp4=1&vipver=MUSIC_9.0.5.0_W1&newver=1"
    )
    timeout = ClientTimeout(total=30)
    async with session.get(url, headers={"User-Agent": UA}, timeout=timeout) as resp:
        data = await resp.json(content_type=None)
    musiclist = data.get("musiclist") or []
    tracks: list[ImportedTrack] = []
    for item in musiclist:
        rid = item.get("id") or item.get("rid") or item.get("MUSICRID")
        if isinstance(rid, str) and rid.upper().startswith("MUSIC_"):
            rid = rid.split("_", 1)[-1]
        if not rid:
            continue
        title = item.get("name") or item.get("SONGNAME") or item.get("FSONGNAME") or "Unknown"
        artist = item.get("artist") or item.get("ARTIST") or item.get("AARTIST") or "Unknown"
        album = item.get("album") or item.get("ALBUM") or "Unknown Album"
        album_id = str(item.get("albumid") or item.get("ALBUMID") or "")
        cover = item.get("pic") or item.get("img") or ""
        if cover and cover.startswith("/"):
            cover = f"https://img4.kuwo.cn/star/albumcover/500{cover}"
        duration = item.get("duration") or item.get("DURATION") or 0
        try:
            duration = int(float(duration))
        except Exception:
            duration = 0
        tracks.append(
            _track(
                source="kw",
                songmid=str(rid),
                title=title,
                artist=artist,
                album=album,
                album_id=f"alb_kw_{album_id}" if album_id else f"kw_{rid}",
                cover=cover,
                duration=duration,
            )
        )
    if not tracks:
        raise ValueError("酷我歌单为空或解析失败")
    now = _now_iso()
    cover = data.get("pic") or data.get("img700") or data.get("img300") or ""
    return ImportedPlaylist(
        id=f"pl_kw_{remote_id}",
        name=data.get("title") or data.get("name") or f"酷我歌单{remote_id}",
        source="kw",
        remote_id=str(remote_id),
        cover=cover if is_valid_cover_url(cover) else "",
        owner=data.get("uname") or data.get("username") or "KW",
        comment=str(data.get("info") or data.get("desc") or "")[:200],
        song_count=len(tracks),
        created=str(data.get("ctime") or data.get("abstime") or now),
        updated_at=now,
        tracks=tracks,
    )


async def fetch_mg_playlist(session: ClientSession, remote_id: str) -> ImportedPlaylist:
    headers = {"User-Agent": _IPHONE_UA, "Referer": "https://m.music.migu.cn/"}
    timeout = ClientTimeout(total=30)
    info: dict[str, Any] = {}
    async with session.get(
        f"https://c.musicapp.migu.cn/MIGUM3.0/resource/playlist/v2.0?playlistId={remote_id}",
        headers=headers,
        timeout=timeout,
    ) as resp:
        meta = await resp.json(content_type=None)
    if str(meta.get("code") or "") in {"000000", "0", "200"}:
        info = meta.get("data") or {}
    tracks: list[ImportedTrack] = []
    page = 1
    while page <= 20:
        async with session.get(
            "https://app.c.nf.migu.cn/MIGUM3.0/resource/playlist/song/v2.0"
            f"?pageNo={page}&pageSize=50&playlistId={remote_id}",
            headers=headers,
            timeout=timeout,
        ) as resp:
            body = await resp.json(content_type=None)
        if str(body.get("code") or "") not in {"000000", "0", "200"}:
            if page == 1:
                raise ValueError(f"未获取到咪咕歌单详情: {body.get('code')}")
            break
        song_list = (body.get("data") or {}).get("songList") or []
        if not song_list:
            break
        for item in song_list:
            song_id = item.get("songId") or item.get("contentId") or item.get("copyrightId")
            if not song_id:
                continue
            singers = item.get("singerList") or item.get("singers") or []
            if isinstance(singers, list):
                artist = "、".join(
                    [(s.get("name") if isinstance(s, dict) else str(s)) for s in singers if s]
                ) or "Unknown"
            else:
                artist = str(singers or "Unknown")
            cover = (
                item.get("img1")
                or item.get("img2")
                or item.get("img3")
                or item.get("albumImg")
                or ""
            )
            imgs = item.get("imgItems") or []
            if not cover and imgs and isinstance(imgs, list):
                cover = (imgs[0] or {}).get("img") or ""
            album = item.get("album") or item.get("albumName") or "Unknown Album"
            if isinstance(album, dict):
                album_name = album.get("name") or "Unknown Album"
                album_id = str(album.get("id") or "")
            else:
                album_name = str(album)
                album_id = str(item.get("albumId") or "")
            duration = item.get("duration") or item.get("length") or 0
            try:
                duration = int(float(duration))
            except Exception:
                duration = 0
            tracks.append(
                _track(
                    source="mg",
                    songmid=str(song_id),
                    title=item.get("songName") or item.get("name") or "Unknown",
                    artist=artist,
                    album=album_name,
                    album_id=f"alb_mg_{album_id}" if album_id else f"mg_{song_id}",
                    cover=cover,
                    duration=duration,
                    extra={"contentId": item.get("contentId") or ""},
                )
            )
        total = int((body.get("data") or {}).get("totalCount") or 0)
        if total and len(tracks) >= total:
            break
        if len(song_list) < 50:
            break
        page += 1
    if not tracks:
        raise ValueError("咪咕歌单为空或解析失败")
    now = _now_iso()
    cover = ((info.get("imgItem") or {}).get("img") if isinstance(info.get("imgItem"), dict) else "") or info.get("img") or ""
    return ImportedPlaylist(
        id=f"pl_mg_{remote_id}",
        name=info.get("title") or info.get("name") or f"咪咕歌单{remote_id}",
        source="mg",
        remote_id=str(remote_id),
        cover=cover if is_valid_cover_url(cover) else "",
        owner=info.get("ownerName") or info.get("creator") or "MG",
        comment=str(info.get("summary") or info.get("desc") or "")[:200],
        song_count=len(tracks),
        created=str(info.get("publishTime") or now),
        updated_at=now,
        tracks=tracks,
    )


_FETCHERS = {
    "tx": fetch_tx_playlist,
    "wy": fetch_wy_playlist,
    "kg": fetch_kg_playlist,
    "kw": fetch_kw_playlist,
    "mg": fetch_mg_playlist,
}


async def fetch_playlist_by_source(session: ClientSession, source: str, remote_id: str) -> ImportedPlaylist:
    fetcher = _FETCHERS.get(source)
    if not fetcher:
        raise ValueError(f"不支持的歌单平台: {source}")
    return await fetcher(session, remote_id)


async def import_playlist(
    session: ClientSession,
    store: PlaylistStore,
    text: str,
    preferred_source: str = "auto",
) -> ImportedPlaylist:
    source, remote_id = detect_source_and_id(text, preferred_source)
    pl = await fetch_playlist_by_source(session, source, remote_id)
    store.last_input = text
    store.last_source = preferred_source or "auto"
    store.upsert(pl)
    store.last_message = f"已导入《{pl.name}》共 {pl.song_count} 首（{source}）"
    return pl


async def refresh_playlist(session: ClientSession, store: PlaylistStore) -> ImportedPlaylist:
    pl = store.selected()
    if not pl:
        raise ValueError("没有选中的歌单")
    if pl.source not in _FETCHERS:
        raise ValueError(f"不支持刷新该平台歌单: {pl.source}")
    new_pl = await fetch_playlist_by_source(session, pl.source, pl.remote_id)
    store.upsert(new_pl)
    store.last_message = f"已刷新《{new_pl.name}》共 {new_pl.song_count} 首（{new_pl.source}）"
    return new_pl
