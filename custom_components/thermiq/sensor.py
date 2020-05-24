"""Support for ThermIQ sensors."""
import logging

from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.const import (DEVICE_CLASS_BATTERY,  # UNIT_PERCENTAGE
                                 DEVICE_CLASS_HUMIDITY,
                                 DEVICE_CLASS_TEMPERATURE, TEMP_CELSIUS)
from homeassistant.helpers.entity import Entity, async_generate_entity_id

from . import DOMAIN as THERMIQ_DOMAIN
from . import id_names as id_names
from . import reg_id as reg_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the available ThermIQ sensors etc."""
    if discovery_info is None:
        return
    data = hass.data[THERMIQ_DOMAIN]

    dev = []

    for key in reg_id:
        if reg_id[key][1] in ['temperature', 'temperature_input', 'time_input', 'sensor', 'sensor_input', 'time', 'select_input', 'sensor_language', 'sensor_boolean']:
            device_id = key
            if key in id_names:
                friendly_name = id_names[key]
            else:
                friendly_name = None
            vp_reg = reg_id[key][0]



            dev.append(
                ThermIQ_MQTT(
                    hass,
                    data,
                    device_id,
                    vp_reg,
                    friendly_name,
                )
            )
    async_add_entities(dev)




class ThermIQ_MQTT(Entity):
    """Representation of a Sensor."""
    def __init__(
        self,
        hass,
        data,
        device_id,
        vp_reg,
        friendly_name,
    ):
        """Initialize the Template switch."""
        self.hass = hass
        self._data = data
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, "thermiq_"+device_id, hass=hass
        )
        _LOGGER.debug("entity_id:"+self.entity_id)
        _LOGGER.debug("idx:"+device_id)
        self._name = friendly_name
        self._state = False
        self._icon = None
        self._icon = 'mdi:temperature'  
        # "mdi:thermometer" ,"mdi:oil-temperature", "mdi:gauge", "mdi:speedometer", "mdi:alert"
        self._entity_picture = None
        self._available = True

        self._idx = device_id
        self._vp_reg = vp_reg
        self._unit = 'C'
        # Listen for the ThermIQ rec event indicating new data
        hass.bus.async_listen("thermiq_mqtt_msg_rec_event", self._async_update_event)



    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False
        
    @property
    def vp_reg(self):
        """Return the device class of the sensor."""
        return self._vp_reg
        
    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit
        
  
    @property
    def icon(self):
      """ Return the icon of the sensor. """
      return self._icon
    
    async def async_update(self):
        """Update the new state of the sensor."""

        _LOGGER.debug("update: thermiq_"+self._idx)
        self._state = self._data.get_value(self._vp_reg)
        if self._state is None:
            _LOGGER.debug("Could not get data for %s", self._idx)

    async def _async_update_event(self, event):
        """Update the new state of the sensor."""

        _LOGGER.debug("event: thermiq_"+self._idx)
        state = self._data.get_value(self._vp_reg)
        if state is None:
            _LOGGER.debug("Could not get data for %s", self._idx)
        if ( self._state != state ):
        	self._state = state
        	self.async_schedule_update_ha_state()
        	_LOGGER.debug("async_update_ha: %s", str(state))
