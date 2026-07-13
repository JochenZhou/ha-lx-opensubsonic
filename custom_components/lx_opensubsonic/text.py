"""Text entities for playlist import input."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PLAYLIST_INPUT, DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PlaylistInputText(hass, entry, data)])


class PlaylistInputText(TextEntity):
    _attr_has_entity_name = True
    _attr_name = "歌单链接或ID"
    _attr_native_min = 0
    _attr_native_max = 500
    _attr_mode = TextMode.TEXT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        self.hass = hass
        self._entry = entry
        self._data = data
        self._attr_unique_id = f"{entry.entry_id}_playlist_input"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "LX OpenSubsonic",
            "manufacturer": "JochenZhou",
            "model": "OpenSubsonic Bridge",
        }

    @property
    def native_value(self) -> str | None:
        store = self._data.get("playlist_store")
        if store and store.last_input:
            return store.last_input
        return (self._entry.data or {}).get(CONF_PLAYLIST_INPUT, "")

    async def async_set_value(self, value: str) -> None:
        value = (value or "").strip()
        store = self._data.get("playlist_store")
        if store is not None:
            store.last_input = value
            store.save()
        new_data = {**self._entry.data, CONF_PLAYLIST_INPUT: value}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
        self.async_write_ha_state()
