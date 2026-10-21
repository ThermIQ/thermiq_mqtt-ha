from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback


from homeassistant.components.sensor import SensorEntity, SensorStateClass
from datetime import datetime
from homeassistant.helpers.entity import Entity, async_generate_entity_id

from homeassistant.const import (
    UnitOfTemperature,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfTime,
)

from homeassistant.components.sensor import SensorDeviceClass


from .const import (
    DOMAIN,
    CONF_ID,
)

from .heatpump import HeatPump
from .heatpump.thermiq_regs import (
    FIELD_BITMASK,
    FIELD_MAXVALUE,
    FIELD_MINVALUE,
    FIELD_REGNUM,
    FIELD_REGTYPE,
    FIELD_UNIT,
    id_names,
    reg_id,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
) -> None:
    """Set up platform for a new integration.

    Called by the HA framework after async_setup_platforms has been called
    during initialization of a new integration.
    """

    @callback
    def async_add_sensor(sensor):
        """Add a ThermIQ sensor property"""
        async_add_entities([sensor], True)
        # _LOGGER.debug('Added new sensor %s / %s', sensor.entity_id, sensor.unique_id)

    worker = hass.data[DOMAIN].worker
    heatpump = hass.data[DOMAIN]._heatpumps[config_entry.data[CONF_ID]]
    entities = []

    for key in reg_id:
        if reg_id[key][1] in [
            "temperature",
            "temperature_input",
            "time_input",
            "sensor",
            "sensor_input",
            "generated_input",
            "time",
            "select_input",
            "sensor_language",
            "sensor_boolean",
            "generated_sensor",
        ]:
            device_id = key
            if key in id_names:
                friendly_name = id_names[key][heatpump._langid]
            else:
                friendly_name = key
            vp_reg = reg_id[key][0]
            vp_type = reg_id[key][1]
            vp_unit = reg_id[key][2]

            entities.append(
                HeatPumpSensor(
                    hass,
                    heatpump,
                    device_id,
                    vp_reg,
                    friendly_name,
                    vp_type,
                    vp_unit,
                )
            )
    async_add_entities(entities)


class HeatPumpSensor(SensorEntity):
    """Common functionality for all entities."""

    # Use the entity name as-is; never prefix it with the device name
    # (long names get truncated in the mobile app)
    _attr_has_entity_name = False

    def __init__(
        self,
        hass: HomeAssistant,
        heatpump: HeatPump,
        device_id: str,
        vp_reg: str,
        friendly_name: str,
        vp_type: str,
        vp_unit: str,
    ) -> None:
        self.hass = hass
        self._heatpump = heatpump
        self._hpstate = heatpump._hpstate
        # set HA instance attributes directly (mostly don't use property)
        # self._attr_unique_id
        self.entity_id = f"sensor.{heatpump._domain}_{heatpump._id}_{device_id}"
        self._attr_unique_id = "uid-" + self.entity_id

        _LOGGER.debug("entity_id: %s idx: %s", self.entity_id, device_id)
        self._name = friendly_name
        self._state = None
        self._last_available: bool | None = None
        self._icon = "mdi:gauge"
        # Default: no state class. Only numeric sensors get MEASUREMENT /
        # TOTAL_INCREASING - string sensors (time, communication_status,
        # app_info, sw_version, ...) must not, or the recorder rejects them.
        self._attr_state_class = None
        self._unit: str | None = vp_unit

        # Override for known types
        if (vp_type in ["temperature_input", "temperature"]) or (
            vp_unit
            in [
                "C",
                "°C",
            ]
        ):
            self._icon = "mdi:temperature-celsius"
            self._unit = UnitOfTemperature.CELSIUS
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_device_class = SensorDeviceClass.TEMPERATURE

        elif vp_type in ["time",] and (
            vp_unit
            in [
                "h",
            ]
        ):
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_device_class = SensorDeviceClass.DURATION
            self._icon = "mdi:clock-star-four-points-outline"
            self._unit = UnitOfTime.HOURS

        elif (vp_type in ["sensor",]) and (
            vp_unit
            in [
                "A",
            ]
        ):
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._icon = "mdi:flash"
            self._unit = UnitOfElectricCurrent.AMPERE

        elif vp_unit in [
            "dBm",
        ]:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._icon = "mdi:wifi"
            self._unit = "dBm"

        elif vp_unit == "%":
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._unit = PERCENTAGE

        elif vp_unit == "Cmin":
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif vp_type == "generated_sensor":
            # time / time_str / communication_status / app_info / mqtt_counter /
            # timestamp: informational text or a bare counter. No unit (the reg
            # table's 's' on 'time' is misleading - the value is a timestamp).
            self._unit = None
        elif vp_type in [
            "sensor_boolean",
        ]:
            self._unit = ""
            self._icon = "mdi:alert"
        # "mdi:thermometer" ,"mdi:oil-temperature", "mdi:gauge", "mdi:speedometer", "mdi:alert"

        self._idx = device_id
        self._vp_reg = vp_reg

    async def async_added_to_hass(self) -> None:

        """Register the update listener; removed automatically on unload."""
        self.async_on_remove(
            self.hass.bus.async_listen(
                self._heatpump._domain + "_" + self._heatpump._id + "_msg_rec_event",
                self._async_update_event,
            )
        )

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def should_poll(self) -> bool:
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def available(self) -> bool:
        """Unavailable while silent, or if this pump never sends the register.
        See HeatPump.supports. A sensor for a register the hardware does not
        report has nothing to show but `unknown`, forever.
        """
        return self._heatpump.available and self._heatpump.supports(self._vp_reg)

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self._state

    @property
    def vp_reg(self) -> str:
        """Return the register of the sensor."""
        return self._vp_reg

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement (None for text sensors).
        An empty string would make HA treat the sensor as numeric and the
        recorder would reject text values, so normalise "" to None.
        """
        return self._unit or None

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return self._icon

    async def async_update(self) -> None:
        """Update the value of the entity."""

        _LOGGER.debug("update: %s", self._idx)
        self._state = self._hpstate.get(self._vp_reg)
        self._last_available = self._heatpump.available
        if self._state is None:
            _LOGGER.debug("No data yet for %s", self._idx)

    async def _async_update_event(self, event: Event) -> None:
        """Update the new state of the sensor."""

        _LOGGER.debug("event: %s", self._idx)
        state = self._hpstate.get(self._vp_reg)
        if state is None:
            _LOGGER.debug("Could not get data for %s", self._idx)
        # Write on value change OR availability transition: an entity whose
        # register never updates must still reflect available/unavailable,
        # otherwise it stays stuck at 'unavailable' after boot
        available = self._heatpump.available
        if self._state != state or self._last_available != available:
            self._state = state
            self._last_available = available
            self.async_write_ha_state()
            _LOGGER.debug("async_update_ha: %s", str(state))
