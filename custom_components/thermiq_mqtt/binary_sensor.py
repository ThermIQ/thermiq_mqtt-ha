import logging
from numbers import Number
from typing import TYPE_CHECKING, Literal, final
from homeassistant.core import HomeAssistant, callback

from homeassistant.const import STATE_OFF, STATE_ON

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import (
    ATTR_IDENTIFIERS,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    STATE_OFF,
    STATE_ON,
    EntityCategory)

from homeassistant.helpers.device_registry import DeviceEntryType

from homeassistant.const import (
    PERCENTAGE
)
from .const import (
    DOMAIN,
    MANUFACTURER,
    DEVVERSION,
    CONF_ID,
)


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


from functools import cached_property


_LOGGER = logging.getLogger(__name__)

_DEVICE_CLASS_MAP = {
    # Pumps and compressor
    "compressor_on":          BinarySensorDeviceClass.RUNNING,
    "brine_pump_on":          BinarySensorDeviceClass.RUNNING,
    "supply_pump_on":         BinarySensorDeviceClass.RUNNING,
    "hotwaterproduction_on":  BinarySensorDeviceClass.RUNNING,
    "active_cooling_on":      BinarySensorDeviceClass.RUNNING,
    "passive_cooling_on":     BinarySensorDeviceClass.RUNNING,
    # Electric heating elements
    "boiler_3kw_on":          BinarySensorDeviceClass.HEAT,
    "boiler_6kw_on":          BinarySensorDeviceClass.HEAT,
    "aux1_heating_on":        BinarySensorDeviceClass.HEAT,
    "aux2_heating_on":        BinarySensorDeviceClass.HEAT,
    # Alarms
    "alarm_indication_on":    BinarySensorDeviceClass.PROBLEM,
    "highpressure_alm":       BinarySensorDeviceClass.PROBLEM,
    "lowpressure_alm":        BinarySensorDeviceClass.PROBLEM,
    "motorbreaker_alm":       BinarySensorDeviceClass.PROBLEM,
    "brine_flow_alm":         BinarySensorDeviceClass.PROBLEM,
    "brine_temperature_alm":  BinarySensorDeviceClass.PROBLEM,
    "outdoor_sensor_alm":     BinarySensorDeviceClass.PROBLEM,
    "supplyline_sensor_alm":  BinarySensorDeviceClass.PROBLEM,
    "returnline_sensor_alm":  BinarySensorDeviceClass.PROBLEM,
    "boiler_sensor_alm":      BinarySensorDeviceClass.PROBLEM,
    "indoor_sensor_alm":      BinarySensorDeviceClass.PROBLEM,
    "phase_order_alm":        BinarySensorDeviceClass.PROBLEM,
    "overheating_alm":        BinarySensorDeviceClass.PROBLEM,
    # Installed add-ons
    "opt_phasemeassure_installed": BinarySensorDeviceClass.CONNECTIVITY,
    "opt_2_installed":        BinarySensorDeviceClass.CONNECTIVITY,
    "opt_hgw_installed":      BinarySensorDeviceClass.CONNECTIVITY,
    "opt_4_installed":        BinarySensorDeviceClass.CONNECTIVITY,
    "opt_5_installed":        BinarySensorDeviceClass.CONNECTIVITY,
    "opt_6_installed":        BinarySensorDeviceClass.CONNECTIVITY,
    "opt_optimum_installed":  BinarySensorDeviceClass.CONNECTIVITY,
    "opt_flowguard_installed": BinarySensorDeviceClass.CONNECTIVITY,
    # shunt1_n/p, shunt2_n/p, shunt_cooling_n/p, heatpump_evu_block: no device class
}


async def async_setup_entry(
    hass, config_entry, async_add_entities, discovery_info=None
):
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
            "binary_sensor",
            "generated_input_boolean"
        ]:
            device_id = key
            if key in id_names:
                friendly_name = id_names[key][heatpump._langid]
            else:
                friendly_name = key
            vp_reg = reg_id[key][FIELD_REGNUM]
            vp_type = reg_id[key][FIELD_REGTYPE]
            bitmask = reg_id[key][FIELD_BITMASK]

            entities.append(
                HeatPumpBinarySensor(
                    hass,
                    heatpump,
                    device_id,
                    vp_reg,
                    friendly_name,
                    bitmask,
                )
            )
    async_add_entities(entities)


class HeatPumpBinarySensor(BinarySensorEntity):
    """Common functionality for all entities."""

    def __init__(self, hass, heatpump, device_id, vp_reg, friendly_name, bitmask):
        self.hass = hass
        self._heatpump = heatpump
        self._hpstate = heatpump._hpstate

        # set HA instance attributes directly (mostly don't use property)
        # self._attr_unique_id
        self.entity_id = f"binary_sensor.{heatpump._domain}_{heatpump._id}_{device_id}"
        self._attr_unique_id = "uid-" + self.entity_id

        _LOGGER.debug("entity_id:" + self.entity_id)
        _LOGGER.debug("idx:" + device_id)
        self._name = friendly_name
        self._state = None
        self._attr_is_on=False
        self._icon = "mdi:flash-outline"

        self._entity_picture = None
        self._available = True

        self._idx = device_id
        self._vp_reg = vp_reg
        self._bitmask = bitmask
        # ???
        if isinstance(vp_reg,Number):
            self._sorter = int("0x" + vp_reg[1:], 0) * 65536 + int(bitmask)
        else:
            self._sorter = 256 * 65536 + int(bitmask)

        # Listen for the ThermIQ rec event indicating new data
        hass.bus.async_listen(
            heatpump._domain + "_" + heatpump._id + "_msg_rec_event",
            self._async_update_event,
        )

        # This is needed
        self._attr_device_info = {
            ATTR_IDENTIFIERS: {(DOMAIN,heatpump._id)},
            ATTR_NAME: "Heatpump status",
            ATTR_MANUFACTURER: MANUFACTURER,
            ATTR_MODEL: DEVVERSION,
            "entry_type": DeviceEntryType.SERVICE,
        }


    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @final
    @property
    def state(self) -> Literal["on", "off"]:
        """Return the state of the sensor."""
        return STATE_ON if (self._state) else STATE_OFF

    @property
    def vp_reg(self):
        """Return the device class of the sensor."""
        return self._vp_reg

    @cached_property
    def is_on(self) -> bool:
        return (self._state==True)

    @property
    def sorter(self):
        """Return the state of the sensor."""
        return self._sorter

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    async def async_update(self):
        """Update the value of the entity."""
        """Update the new state of the sensor."""

        _LOGGER.debug("update: " + self._idx)
        reg_state = self._hpstate[self._vp_reg]
        if self._state is None:
            _LOGGER.warning("Could not get data for %s", self._idx)
        else:
            self._state = (int(reg_state) & self._bitmask) > 0
            self._attr_is_on = self._state

    async def _async_update_event(self, event):
        """Update the new state of the sensor."""

        _LOGGER.debug("event: " + self._idx)
        if self._vp_reg=='evu':
            _LOGGER.debug("EVU reg state read special")
        reg_state = self._hpstate[self._vp_reg]
        if reg_state is None:
            _LOGGER.debug("Could not get data for %s", self._idx)
            self._state = None
            bool_state = None
            self._attr_is_on = False
        else:
            bool_state = (int(reg_state) & self._bitmask) > 0

        if self._state != bool_state:
            self._state = bool_state
            self._attr_is_on = self._state
            self.async_schedule_update_ha_state()
            _LOGGER.debug("async_update_ha: %s: [%s]",self._idx, str(bool_state))

    @property
    def device_class(self):
        """Return the class of this device."""
        return _DEVICE_CLASS_MAP.get(self._idx)
