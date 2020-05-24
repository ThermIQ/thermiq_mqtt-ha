import json
import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.components import mqtt
# import homeassistant.components.sensor as sensor
from homeassistant.components.input_select import (ATTR_OPTION, ATTR_OPTIONS,
                                                   DOMAIN, SERVICE_SELECT_NEXT,
                                                   SERVICE_SELECT_OPTION,
                                                   SERVICE_SELECT_PREVIOUS,
                                                   SERVICE_SET_OPTIONS)
from homeassistant.const import (ATTR_ENTITY_ID,  # UNIT_PERCENTAGE,
                                 ATTR_UNIT_OF_MEASUREMENT, CONF_HOST,
                                 DEVICE_CLASS_BATTERY, DEVICE_CLASS_HUMIDITY,
                                 DEVICE_CLASS_TEMPERATURE, POWER_WATT,
                                 SERVICE_TOGGLE, SERVICE_TURN_OFF,
                                 SERVICE_TURN_ON, STATE_ON, STATE_UNKNOWN,
                                 TEMP_CELSIUS)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.util import Throttle

# import ThermIQ register defines
from custom_components.thermiq.thermiq_regs import reg_id, id_names, id_units, FIELD_REGNUM, FIELD_REGTYPE, FIELD_UNIT, FIELD_MINVALUE, FIELD_MAXVALUE, FIELD_BITMASK 


THERMIQ_PLATFORMS = ["binary_sensor", "sensor"]
# "binary_sensor",]"input_number",
DOMAIN = "thermiq_mqtt"

# List of integration names (string) your integration depends upon.
DEPENDENCIES = ["mqtt"]


# Constants and Schema used to validate the configuration
CONF_MQTT_NODE = "mqtt_node"
CONF_MQTT_DBG = "mqtt_dbg"
DEFAULT_NODE = "ThermIQ/ThermIQ-mqtt"
CONF_DATA = "data_msg"
DEFAULT_DATA = "/data"
CONF_CMD = "cmd_msg"
DEFAULT_CMD = "/WRITE"
DEFAULT_DBG = False


CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MQTT_NODE, default=DEFAULT_NODE): cv.string,
        vol.Optional(CONF_MQTT_DBG, default=DEFAULT_DBG): cv.boolean,
        # vol.Optional(CONF_CMD,default=DEFAULT_CMD): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)


_LOGGER = logging.getLogger(__name__)




async def async_setup(hass, config):
    """Set up the ThermIQ_ MQTT component."""
    conf = config[DOMAIN]
    conf.entity_id = "thermiq_mqtt.timestamp"
    conf.data_topic = conf[CONF_MQTT_NODE] + "/data"
    if (CONF_MQTT_DBG):
        conf.cmd_topic = conf.get(CONF_MQTT_NODE) + "/mqtt_dbg"
    else:
      conf.cmd_topic = conf.get(CONF_MQTT_NODE) + "/write"
    _LOGGER.warning("data:" + conf.data_topic)
    _LOGGER.warning("cmd:" + conf.cmd_topic)

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN] = ThermIQ_MQTT(config[DOMAIN])

    for platform in THERMIQ_PLATFORMS:
        _LOGGER.debug("platform:" + platform)
        discovery.load_platform(hass, platform, DOMAIN, {}, config)

    # ###
    @callback
    def message_received(message):
        """Handle new MQTT messages."""
        _LOGGER.warning("message.payload:[%s]", message.payload)
        try:
            json_dict = json.loads(message.payload)
            if json_dict["app_info"][:13] == "ThermIQ-room ":
                for k in json_dict.keys():
                    hass.data[DOMAIN]._data[k] = json_dict[k]
                    _LOGGER.warning("[%s] [%s]", k, json_dict[k])
                hass.data[DOMAIN]._data["rf0"] = (
                    hass.data[DOMAIN]._data["r01"] + hass.data[DOMAIN]._data["r02"] / 10
                )
                hass.data[DOMAIN]._data["rf1"] = (
                    hass.data[DOMAIN]._data["r03"] + hass.data[DOMAIN]._data["r04"] / 10
                )
                hass.bus.fire("thermiq_mqtt_msg_rec_event", {})
            else:
                _LOGGER.warning("JSON result was not from ThermIQ-mqtt")
        except ValueError:
            _LOGGER.warning("MQTT payload could not be parsed as JSON")
            _LOGGER.debug("Erroneous JSON: %s", payload)

    # Service to publish a message on MQTT.
    @callback
    def write_msg_service(call):
        """Service to send a message."""
        _LOGGER.warning("message.entity_id:[%s]", call.data.get("entity_id"))
        hass.components.mqtt.async_publish(conf.cmd_topic, call.data.get("msg"))

    # Service to write specific value_id with data, value_id will be translated to register number.
    @callback
    def write_reg_service(call):
        reg = call.data.get("reg")
        value = call.data.get("value")
        bitmask = call.data.get("bitmask")
        if bitmask is None:
            bitmask = 0xFFFF
        val = value | bitmask
        msg = f'{{"r{reg:x}": {value} }}'

        _LOGGER.warning("message.reg:[%s]", call.data.get("reg"))
        _LOGGER.warning("message.value:[%s]", call.data.get("value"))
        _LOGGER.warning("message.bitmask:[%s]", call.data.get("bitmask"))
        _LOGGER.warning("msg:[%s]", msg)
        hass.components.mqtt.async_publish(conf.cmd_topic, msg)

    # Service to write specific value_id with data, value_id will be translated to register number.
    @callback
    def write_id_service(call):
        """Service to send a message."""
        _LOGGER.warning("message.value_id:[%s]", call.data.get("value_id"))
        _LOGGER.warning("message.payload:[%s]", call.data.get("value"))

        value_id = call.data.get("value_id").upper()
        idx = len(value_id) - (value_id.find(".THERMIQ") + 9)
        if idx > 0:
            value_id = value_id[-idx:]
        _LOGGER.warning("message.value_id:[%s]", value_id)
        if value_id in reg_id:
            reg = reg_id[value_id][0]
            value = call.data.get("value")
            if value is None:
                return
            bitmask = call.data.get("bitmask")
            if bitmask is None:
                bitmask = 0xFFFF
            value = int(value) & int(bitmask)
            msg = f'{{"{reg}": {value} }}'
            _LOGGER.warning("message.value:[%s]", call.data.get("value"))
            _LOGGER.warning("message.bitmask:[%s]", call.data.get("bitmask"))
            _LOGGER.warning("msg:[%s]", msg)

            if value != hass.data[DOMAIN]._data[reg]:
                hass.components.mqtt.async_publish(conf.cmd_topic, msg)
            else:
                _LOGGER.warning(
                    "No need to write"
                )  # Service to write specific value_id with data, value_id will be translated to register number.

    @callback
    def write_mode_service(call):
        """Service to send a message."""

        _LOGGER.warning("message.payload:[%s]", call.data.get("value"))
        reg = "r51"
        value = int(call.data.get("value"))
        if value is None:
            return
        bits = 2 ** value
        bitmask = 0x01F

        if bits is None:
            return
        value = int(bits) & int(bitmask)
        msg = f'{{"t{reg}": {value} }}'
        _LOGGER.warning("message.value:[%s]", call.data.get("value"))
        _LOGGER.warning("message.value:[%s]", value)
        _LOGGER.warning("msg:[%s]", msg)
        if value != hass.data[DOMAIN]._data[reg]:
            hass.components.mqtt.async_publish(conf.cmd_topic, msg)
        else:
            _LOGGER.warning("No need to write")

    # ###
    # Register our service with Home Assistant.
    hass.services.async_register(DOMAIN, "write_msg", write_msg_service)
    hass.services.async_register(DOMAIN, "write_id", write_id_service)
    hass.services.async_register(DOMAIN, "write_reg", write_reg_service)
    hass.services.async_register(DOMAIN, "write_mode", write_mode_service)
    _LOGGER.warning("Subscribe:" + conf.data_topic)
    await hass.components.mqtt.async_subscribe(conf.data_topic, message_received)
    # Return boolean to indicate that initialization was successfully.
    return True


class ThermIQ_MQTT:
    # Listener to be called when we receive a message.
    # The msg parameter is a Message object with the following members:
    # - topic, payload, qos, retain
    # Listen to a message on MQTT.
    """Handle all communication with ThermIQ."""

    def __init__(self, host):
        """Initialize the MQTT Record."""
        self._data = {}

    def get_value(self, item):
        """Get value for sensor."""
        _LOGGER.debug("get_value(" + item + ")")
        return self._data.get(item)

    def update_state(self, command, state_command):
        """Send update command to ThermIQ."""
        _LOGGER.error("update_state:" + command + " " + state_command)
        self._data[state_command] = self._client.command(command)
        hass.components.mqtt.async_publish(conf.cmd_topic, self._data[state_command])

    async def async_update(self):
        _LOGGER.debug("Fetching data from ThermIQ-MQTT")
        _LOGGER.debug("Done fetching data from ThermIQ-MQTT")
