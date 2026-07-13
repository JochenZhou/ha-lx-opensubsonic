"""Select entities for LX OpenSubsonic runtime settings."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_PREFERRED_QUALITY,
    CONF_SEARCH_SOURCE,
    DOMAIN,
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
        # map label -> value
        value = option
        for k, label in self._labels.items():
            if label == option:
                value = k
                break
        new_data = {**self._entry.data, self._key: value}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
        # apply runtime
        backend = self._data.get("backend")
        api = self._data.get("api")
        if self._key == CONF_SEARCH_SOURCE and backend is not None:
            backend.search_source = value
            self.hass.data[DOMAIN]["search_source"] = value
        if self._key == CONF_PREFERRED_QUALITY and backend is not None:
            backend.preferred_quality = value
            self.hass.data[DOMAIN]["preferred_quality"] = value
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
