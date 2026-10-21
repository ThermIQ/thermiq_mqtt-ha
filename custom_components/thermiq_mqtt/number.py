"""Number entities for ThermIQ writable registers.

Replaces the previous approach of injecting entities into Home Assistant's
built-in input_number platform via hass.data[CONF_ENTITY_PLATFORM] (an
unsupported internal API). These are standard NumberEntity instances in the
`number` domain and update from the shared heatpump state on the msg_rec_event.
"""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberDeviceClass, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .heatpump import HeatPump
from .heatpump.thermiq_regs import (
    FIELD_REGNUM,
    FIELD_REGTYPE,
    FIELD_UNIT,
    FIELD_MINVALUE,
    FIELD_MAXVALUE,
    id_names,
    reg_id,
)

_LOGGER = logging.getLogger(__name__)

# Register types that are exposed as writable numbers
NUMBER_TYPES = ["temperature_input", "time_input", "sensor_input", "generated_input"]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ThermIQ number entities for a config entry."""
    heatpump = hass.data[DOMAIN].heatpumps[config_entry.data["id_name"]]
    entities = [
        ThermIQNumber(heatpump, key)
        for key in reg_id
        if reg_id[key][FIELD_REGTYPE] in NUMBER_TYPES
    ]
    async_add_entities(entities)


class ThermIQNumber(NumberEntity):
    """A writable ThermIQ register exposed as a Number."""

    _attr_should_poll = False
    _attr_mode = NumberMode.BOX
    # Use the entity name as-is; never prefix it with the device name
    _attr_has_entity_name = False

    def __init__(self, heatpump: HeatPump, key: str) -> None:
        self._heatpump = heatpump
        self._hpstate = heatpump._hpstate
        self._key = key
        self._reg = reg_id[key][FIELD_REGNUM]

        self.entity_id = f"number.{heatpump._domain}_{heatpump._id}_{key}"
        self._attr_unique_id = "uid-" + self.entity_id
        self._attr_name = id_names[key][heatpump._langid] if key in id_names else key
        self._attr_native_min_value = reg_id[key][FIELD_MINVALUE]
        self._attr_native_max_value = reg_id[key][FIELD_MAXVALUE]
        self._attr_native_step = 0.1 if self._reg == "indr_t" else 1

        unit = reg_id[key][FIELD_UNIT]
        if reg_id[key][FIELD_REGTYPE] == "temperature_input" or unit in ("C", "°C"):
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
            self._attr_icon = "mdi:thermometer"
        else:
            self._attr_native_unit_of_measurement = unit or None
            self._attr_icon = "mdi:gauge"

    @property
    def available(self) -> bool:
        """Unavailable while silent, or if this pump never sends the register.

        See HeatPump.supports: a control the hardware cannot drive is worse
        than a missing one, because it looks like it works.
        """
        return self._heatpump.available and self._heatpump.supports(self._reg)

    @property
    def native_value(self) -> float | None:
        """Current register value, or None until the first MQTT message."""
        value = self._hpstate.get(self._reg)
        if isinstance(value, (int, float)):
            return value
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Write a new value to the heatpump."""
        # Only send once the heatpump has reported real data
        if self._heatpump._hpstate["mqtt_counter"] <= 0:
            _LOGGER.debug(
                "Ignoring set for %s: no data from heatpump yet", self.entity_id
            )
            return

        # Always publish, even when the cached value already matches: the
        # cache reflects the last message from the pump, not what the pump did
        # with the last write, so skipping here makes a lost write impossible
        # to retry.
        self._hpstate[self._reg] = value
        # Refresh all entities of this heatpump
        self._heatpump._hass.bus.fire(
            f"{self._heatpump._domain}_{self._heatpump._id}_msg_rec_event", {}
            )
        await self._heatpump.send_mqtt_reg(self._key, value, 0xFFFF)

    async def async_added_to_hass(self) -> None:
        """Refresh state on each heatpump message; auto-removed on unload."""
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
