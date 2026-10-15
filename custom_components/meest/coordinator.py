"""Shared Meest polling and persistent token rotation."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MeestAuthError, MeestClient, MeestError, MeestRateLimitError, Tokens
from .const import (
    CONF_B2B,
    CONF_EXPIRES_AT,
    CONF_INTERVAL,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN,
    DEFAULT_INTERVAL,
    DOMAIN,
)
from .models import aggregate

_LOGGER = logging.getLogger(__name__)


class MeestCoordinator(DataUpdateCoordinator):
    """One complete parcel snapshot for both sensors."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
            always_update=False,
        )
        self.entry = entry
        self.business_option = entry.options.get(CONF_B2B, False)
        self.client = MeestClient(
            async_get_clientsession(hass),
            Tokens(
                entry.data[CONF_TOKEN],
                entry.data[CONF_REFRESH_TOKEN],
                entry.data.get(CONF_EXPIRES_AT),
            ),
            self._save_tokens,
        )

    async def _save_tokens(self, tokens: Tokens) -> None:
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={
                **self.entry.data,
                CONF_TOKEN: tokens.token,
                CONF_REFRESH_TOKEN: tokens.refresh_token,
                CONF_EXPIRES_AT: tokens.expires_at,
            },
        )

    async def _async_update_data(self) -> dict:
        try:
            async with asyncio.timeout(120):
                items = await self.client.parcels(self.entry.options.get(CONF_B2B, False))
            return aggregate(items)
        except MeestAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Meest authentication rejected; sign in again ({err})"
            ) from err
        except MeestRateLimitError as err:
            raise UpdateFailed("Meest rate limit", retry_after=err.retry_after) from err
        except (MeestError, ValueError) as err:
            raise UpdateFailed(str(err)) from err
        except TimeoutError as err:
            raise UpdateFailed("Meest snapshot timed out") from err
