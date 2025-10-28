import logging
from homeassistant.core import HomeAssistant, callback 


from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import (
    ATTR_IDENTIFIERS,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
)
from homeassistant.helpers.device_registry import DeviceEntryType
from datetime import datetime
from homeassistant.helpers.entity import Entity, async_generate_entity_id

from homeassistant.const import (
    UnitOfTemperature,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfTime
)

from homeassistant.components.sensor import SensorDeviceClass


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

_LOGGER = logging.getLogger(__name__)


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

    def __init__(
        self, hass, heatpump, device_id, vp_reg, friendly_name, vp_type, vp_unit
    ):
        self.hass = hass
        self._heatpump = heatpump
        self._hpstate = heatpump._hpstate
        # set HA instance attributes directly (mostly don't use property)
        # self._attr_unique_id
        self.entity_id = f"sensor.{heatpump._domain}_{heatpump._id}_{device_id}"
        self._attr_unique_id = "uid-" + self.entity_id

        _LOGGER.debug("entity_id:" + self.entity_id)
        _LOGGER.debug("idx:" + device_id)
        self._name = friendly_name
        self._state = None
        self._icon = None        
        self._attr_state_class = SensorStateClass.MEASUREMENT

        # Override for known types
        if (vp_type in ["temperature_input",]) or (
            vp_unit
            in [
                "C",
            ]
        ):
            self._icon = "mdi:temperature-celsius"
            self._unit =UnitOfTemperature.CELSIUS
            
        if (vp_type in ["temperature",] ):
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._icon = "mdi:temperature-celsius"
            self._unit =UnitOfTemperature.CELSIUS
            
        elif (vp_type in ["time",] ):
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_device_class = SensorDeviceClass.DURATION
            self._icon = "mdi:clock-star-four-points-outline"
            self._unit =UnitOfTime.HOURS
            
        elif (vp_type in ["sensor",]) and (
            vp_unit
            in [
                "A",
            ]
            ):
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._icon = "mdi:clock-star-four-points-outline"
            self._unit =UnitOfElectricCurrent.AMPERE
        




        elif (vp_type in [
            "sensor_boolean",
        ]):
            self._unit = ""
            self._icon = "mdi:alert"
        else:
            self._unit = vp_unit
            self._icon = "mdi:gauge"
        # "mdi:thermometer" ,"mdi:oil-temperature", "mdi:gauge", "mdi:speedometer", "mdi:alert"
        self._entity_picture = None
        self._available = True

        self._idx = device_id
        self._vp_reg = vp_reg
        
        # self.device_class [temperature, voltage,
        #self.state_class= measurement

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

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def vp_reg(self):
        """Return the device class of the sensor."""
        return self._vp_reg

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    async def async_update(self):
        """Update the value of the entity."""
        """Update the new state of the sensor."""

        _LOGGER.debug("update: " + self._idx)
        self._state = self._hpstate.get_value(self._vp_reg)
        if self._state is None:
            _LOGGER.warning("Could not get data for %s", self._idx)

    async def _async_update_event(self, event):
        """Update the new state of the sensor."""

        _LOGGER.debug("event: " + self._idx)
        state = self._hpstate[self._vp_reg]
        if state is None:
            _LOGGER.debug("Could not get data for %s", self._idx)
        if self._state != state:
            self._state = state
            self.async_schedule_update_ha_state()
            _LOGGER.debug("async_update_ha: %s", str(state))

    @property
    def device_class(self):
        """Return the class of this device."""
        return f"{DOMAIN}_HeatPumpSensor"
