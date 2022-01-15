"""Support for ThermIQ binary sensors."""
import logging

from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.const import STATE_OFF, STATE_ON

from . import DOMAIN as THERMIQ_DOMAIN
from . import (
    FIELD_BITMASK,
    FIELD_MAXVALUE,
    FIELD_MINVALUE,
    FIELD_REGNUM,
    FIELD_REGTYPE,
    FIELD_UNIT,
    id_names,
    reg_id,
)

try:
    from homeassistant.components.binary_sensor import BinarySensorEntity
except ImportError:
    from homeassistant.components.binary_sensor import (
        BinarySensorDevice as BinarySensorEntity,
    )


_LOGGER = logging.getLogger(__name__)
# From where should this be imported?
ENTITY_ID_FORMAT = "binary_sensor" + "."+THERMIQ_DOMAIN+"_{}"


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the available ThermIQ sensors etc."""
    if discovery_info is None:
        return
    data = hass.data[THERMIQ_DOMAIN]

    dev = []

    for key in reg_id:
        if reg_id[key][1] in ["binary_sensor"]:
            device_id = key
            if key in id_names:
                friendly_name = id_names[key][ hass.data[THERMIQ_DOMAIN]._data['language'] ]
            else:
                friendly_name = None
            vp_reg = reg_id[key][0]
            ANDbits = reg_id[key][3]

            dev.append(
                ThermIQ_MQTT_BinarySensor(
                    hass, data, device_id, vp_reg, friendly_name, ANDbits,
                )
            )
    async_add_entities(dev)


class ThermIQ_MQTT_BinarySensor(BinarySensorEntity):
    """Representation of a Binary Sensor."""

    def __init__(
        self, hass, data, device_id, vp_reg, friendly_name, ANDbits,
    ):
        """Initialize the Template switch."""
        self.hass = hass
        self._data = data
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, device_id, hass=hass
        )
        _LOGGER.debug("entity_id:" + self.entity_id)
        _LOGGER.debug("idx:" + device_id)
        self._name = friendly_name
        self._state = False
        self._icon = None
        self._icon = "mdi:flash-outline"
        self._entity_picture = None
        self._available = True

        self._idx = device_id
        self._vp_reg = vp_reg
        self._sorter = int("0x" + vp_reg[1:], 0) * 65536 + int(ANDbits)
        self._ANDbits = ANDbits

        # Listen for the ThermIQ rec event indicating new data
        hass.bus.async_listen(THERMIQ_DOMAIN+"_msg_rec_event", self._async_update_event)

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
    def is_on(self):
        return self._state

    @property
    def state(self):
        """Return the state of the sensor."""
        return STATE_ON if self.is_on else STATE_OFF

    @property
    def sorter(self):
        """Return the state of the sensor."""
        return self._sorter

    @property
    def icon(self):
        """ Return the icon of the sensor. """
        return self._icon

    async def async_update(self):
        """Update the new state of the sensor."""

        _LOGGER.debug("update: "+THERMIQ_DOMAIN +"_" + self._idx)
        state = self._data.get_value(self._vp_reg)
        # self._data.async_update()
        if (state) is None:
            self._state = None
            _LOGGER.error("Could not get data for %s", self._idx)
        else:
            self._state = (int(state) & self._ANDbits) > 0

    async def _async_update_event(self, event):
        """Update the new state of the sensor."""

        _LOGGER.debug("event: "+ THERMIQ_DOMAIN +"_" + self._idx)
        state = self._data.get_value(self._vp_reg)
        # self._data.async_update()
        if (state) is None:
            self._state = None
            bool_state = None
            _LOGGER.error("Could not get data for %s", self._idx)
        else:
            bool_state = (int(state) & self._ANDbits) > 0
        if True:  # bool_state != self._state ):
            self._state = bool_state
            self.async_schedule_update_ha_state()
            _LOGGER.debug("async_update_ha: %s", str(bool_state))
