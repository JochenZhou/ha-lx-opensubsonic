"""Button entities for LX OpenSubsonic."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LxTestConnectionButton(hass, entry, data)])


class LxTestConnectionButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "测试连接"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        self.hass = hass
        self._entry = entry
        self._data = data
        self._attr_unique_id = f"{entry.entry_id}_test_connection"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "LX OpenSubsonic",
            "manufacturer": "JochenZhou",
            "model": "OpenSubsonic Bridge",
        }

    async def async_press(self) -> None:
        await self.hass.services.async_call(DOMAIN, "test_connection", {}, blocking=True)
