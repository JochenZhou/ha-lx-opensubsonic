"""Select entities for LX OpenSubsonic runtime settings and playlists."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_PLAYLIST_SOURCE,
    CONF_PREFERRED_QUALITY,
    CONF_SEARCH_SOURCE,
    DEFAULT_PLAYLIST_SOURCE,
    DOMAIN,
    PLAYLIST_SOURCE_LABELS,
    PLAYLIST_SOURCE_OPTIONS,
    QUALITY_LABELS,
    QUALITY_OPTIONS,
    SEARCH_SOURCE_LABELS,
    SEARCH_SOURCES,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LxSearchSourceSelect(hass, entry, data),
            LxQualitySelect(hass, entry, data),
            LxPlaylistSourceSelect(hass, entry, data),
            LxImportedPlaylistSelect(hass, entry, data),
        ]
    )


class _BaseSelect(SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict, key: str, name: str, options: list[str], labels: dict[str, str]) -> None:
        self.hass = hass
        self._entry = entry
        self._data = data
        self._key = key
        self._labels = labels
        self._values = options
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_options = [labels.get(v, v) for v in options]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "LX OpenSubsonic",
            "manufacturer": "JochenZhou",
            "model": "OpenSubsonic Bridge",
        }

    def _current_value(self) -> str:
        cfg = {**self._entry.data, **(self._entry.options or {})}
        return str(cfg.get(self._key) or self._values[0])

    @property
    def current_option(self) -> str | None:
        return self._labels.get(self._current_value(), self._current_value())

    async def async_select_option(self, option: str) -> None:
        value = option
        for k, label in self._labels.items():
            if label == option:
                value = k
                break
        new_data = {**self._entry.data, self._key: value}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
        backend = self._data.get("backend")
        if self._key == CONF_SEARCH_SOURCE and backend is not None:
            backend.search_source = value
            self.hass.data[DOMAIN]["search_source"] = value
        if self._key == CONF_PREFERRED_QUALITY and backend is not None:
            backend.preferred_quality = value
            self.hass.data[DOMAIN]["preferred_quality"] = value
        if self._key == CONF_PLAYLIST_SOURCE:
            store = self._data.get("playlist_store")
            if store is not None:
                store.last_source = value
                await store.async_save(self.hass)
        self.async_write_ha_state()
        coordinator = self._data.get("coordinator")
        if coordinator is not None:
            await coordinator.async_request_refresh()


class LxSearchSourceSelect(_BaseSelect):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        super().__init__(hass, entry, data, CONF_SEARCH_SOURCE, "默认搜索源", SEARCH_SOURCES, SEARCH_SOURCE_LABELS)


class LxQualitySelect(_BaseSelect):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        super().__init__(hass, entry, data, CONF_PREFERRED_QUALITY, "优先音质", QUALITY_OPTIONS, QUALITY_LABELS)


class LxPlaylistSourceSelect(_BaseSelect):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        labels = PLAYLIST_SOURCE_LABELS
        values = [o["value"] for o in PLAYLIST_SOURCE_OPTIONS]
        super().__init__(hass, entry, data, CONF_PLAYLIST_SOURCE, "歌单平台", values, labels)

    def _current_value(self) -> str:
        store = self._data.get("playlist_store")
        if store and store.last_source:
            return store.last_source
        cfg = {**self._entry.data, **(self._entry.options or {})}
        return str(cfg.get(CONF_PLAYLIST_SOURCE) or DEFAULT_PLAYLIST_SOURCE)


class LxImportedPlaylistSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "已导入歌单"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        self.hass = hass
        self._entry = entry
        self._data = data
        self._attr_unique_id = f"{entry.entry_id}_imported_playlist"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "LX OpenSubsonic",
            "manufacturer": "JochenZhou",
            "model": "OpenSubsonic Bridge",
        }

    @property
    def options(self) -> list[str]:
        store = self._data.get("playlist_store")
        names = store.names() if store else []
        return names or ["无歌单"]

    @property
    def current_option(self) -> str | None:
        store = self._data.get("playlist_store")
        if not store:
            return "无歌单"
        pl = store.selected()
        return pl.name if pl else "无歌单"

    async def async_select_option(self, option: str) -> None:
        store = self._data.get("playlist_store")
        if not store or option == "无歌单":
            return
        store.set_selected_by_name(option)
        await store.async_save(self.hass)
        self.async_write_ha_state()
        # refresh related sensors
        coordinator = self._data.get("coordinator")
        if coordinator is not None:
            await coordinator.async_request_refresh()
