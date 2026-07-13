"""Coordinator for LX OpenSubsonic health status."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .music_backend import MusicBackend

_LOGGER = logging.getLogger(__name__)


class LxOpenSubsonicCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, backend: MusicBackend) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="lx_opensubsonic",
            update_interval=timedelta(minutes=10),
        )
        self.entry = entry
        self.backend = backend

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.backend.health_check()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err
