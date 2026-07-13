"""Button entities for LX OpenSubsonic."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PLAYLIST_INPUT, CONF_PLAYLIST_SOURCE, DOMAIN
from .playlist_store import import_playlist, refresh_playlist

# Shown after successful import/refresh so users know how MA actually picks it up.
_MA_PLAYLIST_HINT = (
    "Music Assistant 提示：自带播放列表是本地缓存。"
    "导入后请到「浏览 → OpenSubsonic Media Server Library → 播放列表」点开一次，"
    "或重启 Music Assistant；仅点重载/同步往往不会立刻出现。"
    "搜索页不支持找导入歌单。"
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LxTestConnectionButton(hass, entry, data),
            LxImportPlaylistButton(hass, entry, data),
            LxRefreshPlaylistButton(hass, entry, data),
            LxDeletePlaylistButton(hass, entry, data),
        ]
    )


class _BaseBtn(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict, key: str, name: str) -> None:
        self.hass = hass
        self._entry = entry
        self._data = data
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "LX OpenSubsonic",
            "manufacturer": "JochenZhou",
            "model": "OpenSubsonic Bridge",
        }

    async def _notify(self, title: str, message: str) -> None:
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {"title": title, "message": message, "notification_id": "lx_opensubsonic_playlist"},
            blocking=False,
        )

    async def _refresh_ui(self) -> None:
        coordinator = self._data.get("coordinator")
        if coordinator is not None:
            await coordinator.async_request_refresh()
        # Force HA to re-evaluate related entities (select options/sensor attrs).
        entity_ids: list[str] = []
        for state in self.hass.states.async_all(("sensor", "select", "text")):
            eid = state.entity_id
            if "lx_opensubsonic" not in eid:
                continue
            if any(
                key in eid
                for key in (
                    "yi_dao_ru_ge_dan",
                    "ge_dan_lian_jie",
                    "ge_dan_ping_tai",
                    "playlist",
                    "jian_kang",
                )
            ):
                entity_ids.append(eid)
        if entity_ids:
            await self.hass.services.async_call(
                "homeassistant",
                "update_entity",
                {"entity_id": entity_ids},
                blocking=True,
            )
        self.async_write_ha_state()


class LxTestConnectionButton(_BaseBtn):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        super().__init__(hass, entry, data, "test_connection", "测试连接")

    async def async_press(self) -> None:
        await self.hass.services.async_call(DOMAIN, "test_connection", {}, blocking=True)


class LxImportPlaylistButton(_BaseBtn):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        super().__init__(hass, entry, data, "import_playlist", "导入歌单")

    async def async_press(self) -> None:
        store = self._data.get("playlist_store")
        backend = self._data.get("backend")
        if not store or not backend:
            await self._notify("导入失败", "集成未就绪")
            return
        # Prefer live text entity state, then store/entry fallback.
        text = ""
        for st in self.hass.states.async_all("text"):
            if st.entity_id.endswith("_ge_dan_lian_jie_huo_id") or st.entity_id.endswith("_playlist_input") or "ge_dan_lian_jie" in st.entity_id:
                text = (st.state or "").strip()
                if text and text.lower() not in {"unknown", "unavailable"}:
                    break
        if not text:
            text = (store.last_input or (self._entry.data or {}).get(CONF_PLAYLIST_INPUT, "")).strip()
        source = store.last_source or (self._entry.data or {}).get(CONF_PLAYLIST_SOURCE, "auto")
        # also read playlist source select label/value if present
        for st in self.hass.states.async_all("select"):
            if "ge_dan_ping_tai" in st.entity_id or st.entity_id.endswith("_playlist_source"):
                label = (st.state or "").strip()
                low = label.lower()
                if label in {"自动识别", "auto"} or low == "auto":
                    source = "auto"
                elif "QQ" in label or low == "tx" or "(tx)" in low:
                    source = "tx"
                elif "网易" in label or low == "wy" or "(wy)" in low:
                    source = "wy"
                elif "酷狗" in label or low == "kg" or "(kg)" in low:
                    source = "kg"
                elif "酷我" in label or low == "kw" or "(kw)" in low:
                    source = "kw"
                elif "咪咕" in label or low == "mg" or "(mg)" in low:
                    source = "mg"
                break
        try:
            pl = await import_playlist(backend._session, store, text, source)
            # warm song cache
            for tr in pl.tracks:
                backend.cache_song(tr.to_song())
            msg = f"{store.last_message}\n\n{_MA_PLAYLIST_HINT}"
            store.last_message = msg
            store.save()
            await self._notify("导入成功", msg)
        except Exception as err:  # noqa: BLE001
            store.last_message = f"导入失败: {err}"
            store.save()
            await self._notify("导入失败", str(err))
        await self._refresh_ui()


class LxRefreshPlaylistButton(_BaseBtn):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        super().__init__(hass, entry, data, "refresh_playlist", "刷新歌单")

    async def async_press(self) -> None:
        store = self._data.get("playlist_store")
        backend = self._data.get("backend")
        if not store or not backend:
            await self._notify("刷新失败", "集成未就绪")
            return
        try:
            pl = await refresh_playlist(backend._session, store)
            for tr in pl.tracks:
                backend.cache_song(tr.to_song())
            msg = f"{store.last_message}\n\n{_MA_PLAYLIST_HINT}"
            store.last_message = msg
            store.save()
            await self._notify("刷新成功", msg)
        except Exception as err:  # noqa: BLE001
            store.last_message = f"刷新失败: {err}"
            store.save()
            await self._notify("刷新失败", str(err))
        await self._refresh_ui()


class LxDeletePlaylistButton(_BaseBtn):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        super().__init__(hass, entry, data, "delete_playlist", "删除歌单")

    async def async_press(self) -> None:
        store = self._data.get("playlist_store")
        if not store:
            await self._notify("删除失败", "集成未就绪")
            return
        msg = store.delete_selected()
        msg = f"{msg}\n\n如需从 Music Assistant 自带播放列表移除，请在 MA 中同步/重启后刷新库。"
        store.last_message = msg
        store.save()
        await self._notify("删除歌单", msg)
        await self._refresh_ui()
