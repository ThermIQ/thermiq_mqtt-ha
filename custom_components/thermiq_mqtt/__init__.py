"""Component for ThermIQ-MQTT support."""
import logging
from builtins import property
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, Event

from .const import (
    DOMAIN,
    CONF_ID,
)

# from .automation import setup_automations
from .input_number import setup_input_numbers
from .input_select import setup_input_select

# from .heatpump.sensor import HeatPumpSensor

from .heatpump import (
    HeatPump,
)

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [
    "sensor",
    "binary_sensor",
]


@asyncio.coroutine
async def async_setup(hass, config):
    """Set up HASL integration"""
    _LOGGER.error("Set up ThermIQ-MQTT integration")

    if DOMAIN not in hass.data:
        worker = hass.data.setdefault(DOMAIN, ThermIQWorker(hass))
    return True


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate configuration entry if needed"""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up component from a config entry, config_entry contains data from config entry database."""
    _LOGGER.error("Set up ThermIQ-MQTT integration entry " + entry.data[CONF_ID])

    # One common ThermIQWorker serves all HeatPump objects
    if DOMAIN in hass.data:
        worker = hass.data[DOMAIN]
    else:
        worker = hass.data.setdefault(DOMAIN, ThermIQWorker(hass))

    # add new heatpump to worker
    heatpump = worker.add_entry(entry)
    # Make config reload
    rld = entry.add_update_listener(reload_entry)
    entry.async_on_unload(rld)

    async def handle_hass_started(_event: Event) -> None:
        """Event handler for when HA has started."""
        await hass.async_create_task(setup_input_numbers(heatpump))
        await hass.async_create_task(setup_input_select(heatpump))
        await hass.async_create_task(heatpump.setup_mqtt())

    # Load the platforms for heatpump
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    )

    # Wait for hass to start and then add the input_* entities
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, handle_hass_started)
    # Make config reload

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        worker = hass.data[DOMAIN]
        worker.remove_entry(entry)
        if worker.is_idle():
            # also remove worker if not used by any entry any more
            del hass.data[DOMAIN]

    return unload_ok


async def reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if DOMAIN in hass.data:
        worker = hass.data[DOMAIN]
        await worker.update_heatpump_entry(entry)


class ThermIQWorker:
    """worker object. Stored in hass.data."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the instance."""
        self._hass = hass
        self._heatpumps = {}
        self._fetch_callback_listener = None
        self._worker = True

    @property
    def worker(self):
        return self._worker

    @property
    def heatpumps(self):
        return self._heatpumps

    def add_entry(self, config_entry: ConfigEntry):
        """Add entry."""
        heatpump = HeatPump(self._hass, config_entry)
        await heatpump.update_config(config_entry)
        self._heatpumps[config_entry.data[CONF_ID]] = heatpump
        self._hass.bus.fire(
            f"{DOMAIN}_changed",
            {"action": "add", "heatpump": config_entry.data[CONF_ID]},
        )
        return heatpump

    def remove_entry(self, config_entry: ConfigEntry):
        """Remove entry."""
        self._hass.bus.fire(
            f"{DOMAIN}_changed",
            {"action": "remove", "heatpump": config_entry.data[CONF_ID]},
        )
        self._heatpumps.pop(config_entry.data[CONF_ID])

    async def update_heatpump_entry(self, config_entry: ConfigEntry):
        heatpump = self._heatpumps[config_entry.data[CONF_ID]]
        await heatpump.update_config(config_entry)
        await self._hass.async_create_task(heatpump.setup_mqtt())

    def is_idle(self) -> bool:
        return not bool(self._heatpumps)
