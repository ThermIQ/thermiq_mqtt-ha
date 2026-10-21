"""Switch entities for ThermIQ boolean control registers.

Replaces injection into Home Assistant's built-in input_boolean platform.
Standard SwitchEntity instances in the `switch` domain (e.g. EVU block).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .heatpump import HeatPump
from .heatpump.thermiq_regs import (
    FIELD_REGNUM,
    FIELD_REGTYPE,
    FIELD_BITMASK,
    id_names,
    reg_id,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ThermIQ switch entities for a config entry."""
    heatpump = hass.data[DOMAIN].heatpumps[config_entry.data["id_name"]]
    entities = [
        ThermIQSwitch(heatpump, key)
        for key in reg_id
        if reg_id[key][FIELD_REGTYPE] == "generated_input_boolean"
    ]
    async_add_entities(entities)


class ThermIQSwitch(SwitchEntity):
    """A ThermIQ boolean control register exposed as a Switch."""

    _attr_should_poll = False
    _attr_icon = "mdi:transmission-tower"
    # Use the entity name as-is; never prefix it with the device name
    _attr_has_entity_name = False

    def __init__(self, heatpump: HeatPump, key: str) -> None:
        self._heatpump = heatpump
        self._hpstate = heatpump._hpstate
        self._key = key
        self._reg = reg_id[key][FIELD_REGNUM]
        self._bitmask = reg_id[key][FIELD_BITMASK]

        self.entity_id = f"switch.{heatpump._domain}_{heatpump._id}_{key}"
        self._attr_unique_id = "uid-" + self.entity_id
        self._attr_name = id_names[key][heatpump._langid] if key in id_names else key

    @property
    def available(self) -> bool:
        """Unavailable while silent, or if this pump never sends the register.

        See HeatPump.supports: a control the hardware cannot drive is worse
        than a missing one, because it looks like it works.
        """
        return self._heatpump.available and self._heatpump.supports(self._reg)

    @property
    def is_on(self) -> bool | None:
        """Return True/False, or None until the first MQTT message."""
        value = self._hpstate.get(self._reg)
        if value is None:
            return None
        try:
            return (int(value) & int(self._bitmask)) > 0
        except (TypeError, ValueError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_write(False)

    async def _async_write(self, turn_on: bool) -> None:
        if self._heatpump._hpstate["mqtt_counter"] <= 0:
            _LOGGER.debug("Ignoring switch for %s: no data yet", self.entity_id)
            return

        value = 1 if turn_on else 0
        # Always publish, even when the cached value already matches: the
        # cache reflects the last message from the pump, not what the pump
        # did with the last write, so skipping here makes a lost write
        # impossible to retry.
        self._hpstate[self._reg] = value
        self._heatpump._hass.bus.fire(
            f"{self._heatpump._domain}_{self._heatpump._id}_msg_rec_event", {}
            )
        await self._heatpump.send_mqtt_reg(self._key, value, 0xFFFF)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{self._heatpump._domain}_{self._heatpump._id}_msg_rec_event",
                self._async_update_event,
            )
        )

    async def _async_update_event(self, event: Event) -> None:
        # Write on value change OR availability transition only
        snapshot = (self._hpstate.get(self._reg), self._heatpump.available)
        if snapshot != getattr(self, "_last_snapshot", None):
            self._last_snapshot = snapshot
            self.async_write_ha_state()
