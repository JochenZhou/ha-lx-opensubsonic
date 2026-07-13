"""Sensor entities for LX OpenSubsonic."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, QUALITY_LABELS, SEARCH_SOURCE_LABELS
from .coordinator import LxOpenSubsonicCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: LxOpenSubsonicCoordinator = data["coordinator"]
    async_add_entities(
        [
            LxHealthSensor(coordinator, entry),
            LxStatusSensor(coordinator, entry, "search_ok", "搜索状态"),
            LxStatusSensor(coordinator, entry, "cover_ok", "封面状态"),
            LxStatusSensor(coordinator, entry, "stream_ok", "播放取链状态"),
            LxStatusSensor(coordinator, entry, "js_ok", "音源JS状态"),
        ]
    )


class _Base(CoordinatorEntity[LxOpenSubsonicCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LxOpenSubsonicCoordinator, entry: ConfigEntry, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "LX OpenSubsonic",
            "manufacturer": "JochenZhou",
            "model": "OpenSubsonic Bridge",
        }


class LxHealthSensor(_Base):
    def __init__(self, coordinator: LxOpenSubsonicCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "health", "健康状态")

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        return "正常" if data.get("ok") else "异常"

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        cfg = {**self._entry.data, **(self._entry.options or {})}
        sample = data.get("sample_song") or {}
        return {
            "search_ok": data.get("search_ok"),
            "cover_ok": data.get("cover_ok"),
            "stream_ok": data.get("stream_ok"),
            "js_ok": data.get("js_ok"),
            "search_source": cfg.get("search_source"),
            "search_source_label": SEARCH_SOURCE_LABELS.get(cfg.get("search_source", ""), cfg.get("search_source")),
            "preferred_quality": cfg.get("preferred_quality"),
            "preferred_quality_label": QUALITY_LABELS.get(cfg.get("preferred_quality", ""), cfg.get("preferred_quality")),
            "sample_song": f"{sample.get('artist', '')} - {sample.get('title', '')}".strip(" -"),
            "errors": data.get("errors") or [],
            "elapsed_ms": data.get("elapsed_ms") or {},
        }


class LxStatusSensor(_Base):
    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        return "正常" if data.get(self._key) else "异常"
