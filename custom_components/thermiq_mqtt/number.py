"""Number entities for ThermIQ heat pump settings."""
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
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

INPUT_REG_TYPES = [
    "temperature_input",
    "time_input",
    "sensor_input",
    "generated_input",
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ThermIQ number entities from a config entry."""
    worker = hass.data[DOMAIN]
    heatpump = worker.get_entry(config_entry)

    entities = []
    for key, reg_def in reg_id.items():
        if reg_def[FIELD_REGTYPE] in INPUT_REG_TYPES:
            entities.append(HeatPumpNumber(heatpump, key))

    async_add_entities(entities)


class HeatPumpNumber(NumberEntity):
    """A number entity for a ThermIQ heat pump register."""

    _attr_should_poll = False
    _attr_mode = NumberMode.BOX

    def __init__(self, heatpump, register_name: str) -> None:
        """Initialize the number entity."""
        self._heatpump = heatpump
        self._register_name = register_name
        self._reg_def = reg_id[register_name]
        self._reg = self._reg_def[FIELD_REGNUM]

        # Entity identification
        self._attr_unique_id = (
            f"{heatpump._domain}_{heatpump._id}_{register_name}"
        )
        self.entity_id = (
            f"number.{heatpump._domain}_{heatpump._id}_{register_name}"
        )

        # Friendly name from translations
        if register_name in id_names:
            self._attr_name = id_names[register_name][heatpump._langid]
        else:
            self._attr_name = register_name

        # Min/max/step
        self._attr_native_min_value = float(self._reg_def[FIELD_MINVALUE])
        self._attr_native_max_value = float(self._reg_def[FIELD_MAXVALUE])
        self._attr_native_step = (
            0.1 if self._reg == "indr_t" else 1.0
        )

        # Unit and icon
        if (
            self._reg_def[FIELD_REGTYPE] == "temperature_input"
            or self._reg_def[FIELD_UNIT] in ("C", "°C")
        ):
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_icon = "mdi:temperature-celsius"
        else:
            unit = self._reg_def[FIELD_UNIT]
            self._attr_native_unit_of_measurement = unit if unit else None
            self._attr_icon = "mdi:gauge"

        # Device info to group under the heat pump device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, heatpump._id)},
        }

    @property
    def native_value(self) -> float | None:
        """Return the current value from heat pump state."""
        val = self._heatpump._hpstate.get(self._reg)
        if val is None or val == -1:
            return None
        return float(val)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value, and send MQTT command to heat pump."""
        # Only send if we've received at least one MQTT message
        if self._heatpump._hpstate.get("mqtt_counter", -1) <= 0:
            return

        current = self._heatpump._hpstate.get(self._reg)
        if current != value:
            self._heatpump._hpstate[self._reg] = value
            self._heatpump._hass.bus.fire(
                f"{self._heatpump._domain}_{self._heatpump._id}_msg_rec_event",
                {},
            )
            await self._heatpump.send_mqtt_reg(
                self._register_name, value, 0xFFFF
            )
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register event listener when added to hass."""
        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{self._heatpump._domain}_{self._heatpump._id}_msg_rec_event",
                self._async_update_event,
            )
        )

    async def _async_update_event(self, event) -> None:
        """Handle heat pump state update event."""
        self.async_write_ha_state()
