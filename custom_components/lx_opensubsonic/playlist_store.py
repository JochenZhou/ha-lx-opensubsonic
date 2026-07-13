"""Imported playlist storage and TX playlist import helpers."""

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
        self._load()

    def _load(self) -> None:
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
                self.save()
                return

    def upsert(self, pl: ImportedPlaylist) -> None:
        self.playlists[pl.id] = pl
        self.selected_id = pl.id
        self.save()

    def delete_selected(self) -> str:
        pl = self.selected()
        if not pl:
            self.last_message = "没有可删除的歌单"
            self.save()
            return self.last_message
        self.playlists.pop(pl.id, None)
        items = self.list_playlists()
        self.selected_id = items[0].id if items else ""
        self.last_message = f"已删除《{pl.name}》"
        self.save()
        return self.last_message

    def clear_all(self) -> str:
        n = len(self.playlists)
        self.playlists.clear()
        self.selected_id = ""
        self.last_message = f"已清空全部歌单（{n}）"
        self.save()
        return self.last_message


_ID_PATTERNS = {
    "tx": [
        re.compile(r"playlist/(\d+)", re.I),
        re.compile(r"[?&]id=(\d+)"),
        re.compile(r"disstid=(\d+)", re.I),
        re.compile(r"^(\d{6,})$"),
    ],
    "wy": [
        re.compile(r"playlist\?id=(\d+)", re.I),
        re.compile(r"/playlist/(\d+)", re.I),
        re.compile(r"^(\d{6,})$"),
    ],
}


def detect_source_and_id(text: str, preferred: str = "auto") -> tuple[str, str]:
    s = (text or "").strip()
    if not s:
        raise ValueError("请输入歌单链接或ID")
    low = s.lower()
    if preferred and preferred != "auto":
        src = preferred
    elif "y.qq.com" in low or "qq.com" in low:
        src = "tx"
    elif "music.163.com" in low or "163cn.tv" in low:
        src = "wy"
    else:
        src = "tx"  # default numeric id to QQ for MVP
    for pat in _ID_PATTERNS.get(src, []):
        m = pat.search(s)
        if m:
            return src, m.group(1)
    # bare digits
    m = re.search(r"(\d{6,})", s)
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
            ImportedTrack(
                id=f"tx_{mid}",
                title=item.get("title") or item.get("name") or "Unknown",
                artist=artist,
                album=album_name,
                album_id=f"alb_tx_{album_mid}" if album_mid else f"tx_{mid}",
                artist_id=f"artist_{artist.split('、')[0]}",
                cover=sc if is_valid_cover_url(sc) else "",
                duration=int(item.get("interval") or 0),
                source="tx",
                songmid=mid,
                extra={"album_mid": album_mid, "media_mid": (item.get("file") or {}).get("media_mid")},
            )
        )
    if not tracks:
        raise ValueError("歌单为空或解析失败")
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
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


async def import_playlist(
    session: ClientSession,
    store: PlaylistStore,
    text: str,
    preferred_source: str = "auto",
) -> ImportedPlaylist:
    source, remote_id = detect_source_and_id(text, preferred_source)
    if source != "tx":
        raise ValueError("当前版本仅支持导入 QQ 音乐歌单（tx）")
    pl = await fetch_tx_playlist(session, remote_id)
    store.last_input = text
    store.last_source = preferred_source or "auto"
    store.upsert(pl)
    store.last_message = f"已导入《{pl.name}》共 {pl.song_count} 首"
    store.save()
    return pl


async def refresh_playlist(session: ClientSession, store: PlaylistStore) -> ImportedPlaylist:
    pl = store.selected()
    if not pl:
        raise ValueError("没有选中的歌单")
    if pl.source != "tx":
        raise ValueError("当前版本仅支持刷新 QQ 音乐歌单")
    new_pl = await fetch_tx_playlist(session, pl.remote_id)
    store.upsert(new_pl)
    store.last_message = f"已刷新《{new_pl.name}》共 {new_pl.song_count} 首"
    store.save()
    return new_pl
