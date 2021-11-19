import json
import logging
from datetime import timedelta

import voluptuous as vol

# import ThermIQ register defines
from custom_components.thermiq_mqtt.thermiq_regs import (
    FIELD_BITMASK,
    FIELD_MAXVALUE,
    FIELD_MINVALUE,
    FIELD_REGNUM,
    FIELD_REGTYPE,
    FIELD_UNIT,
    id_names,
    id_units,
    reg_id,
)

from homeassistant.components import mqtt

# import homeassistant.components.sensor as sensor
from homeassistant.components.input_select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    DOMAIN,
    SERVICE_SELECT_NEXT,
    SERVICE_SELECT_OPTION,
    SERVICE_SELECT_PREVIOUS,
    SERVICE_SET_OPTIONS,
)
from homeassistant.const import ATTR_ENTITY_ID  # UNIT_PERCENTAGE,
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_HOST,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_TEMPERATURE,
    POWER_WATT,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNKNOWN,
    TEMP_CELSIUS,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.util import Throttle

THERMIQ_PLATFORMS = ["binary_sensor", "sensor"]

DOMAIN = "thermiq_mqtt"

# List of integration names (string) your integration depends upon.
DEPENDENCIES = ["mqtt"]


# Constants and Schema used to validate the configuration
CONF_MQTT_NODE = "mqtt_node"
CONF_MQTT_DBG = "thermiq_dbg"
DEFAULT_NODE = "ThermIQ/ThermIQ-mqtt"
CONF_DATA = "data_msg"
DEFAULT_DATA = "/data"
CONF_CMD = "cmd_msg"
DEFAULT_CMD = "/WRITE"
DEFAULT_DBG = False
MSG_RECEIVED_STATE = 'thermiq_mqtt.last_msg_time'


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
    if conf[CONF_MQTT_DBG] == True:
        conf.cmd_topic = conf.get(CONF_MQTT_NODE) + "/mqtt_dbg"
        _LOGGER.debug("MQTT Debug write enabled");
    else:
        conf.cmd_topic = conf.get(CONF_MQTT_NODE) + "/write"
    _LOGGER.info("data:" + conf.data_topic)
    _LOGGER.info("cmd:" + conf.cmd_topic)

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN] = ThermIQ_MQTT(config[DOMAIN])

    for platform in THERMIQ_PLATFORMS:
        _LOGGER.debug("platform:" + platform)
        discovery.load_platform(hass, platform, DOMAIN, {}, config)
        
# Create reverse lookup dictionary (id_reg->reg_number
    id_reg= {}
    for k,v in reg_id.items():
       id_reg[v[0]]=k
       _LOGGER.debug("id_reg[%s => %s]",v[0],k)

    # ###
    @callback
    def message_received(message):
        """Handle new MQTT messages."""
        _LOGGER.debug("message.payload:[%s]", message.payload)
        try:
            json_dict = json.loads(message.payload)
            if json_dict["Client_Name"][:8] == "ThermIQ_":
                for k in json_dict.keys():
                    kstore=k.lower()
                    dstore=k
                    # Make internal register hex if incoming register is decimal format
                    if k[0]=='d':
                        reg=int(k[1:])
                        kstore="r"+format(reg,'02x')
                        dstore="d"+format(reg,'03d')
                        if len(kstore) != 3:
                            kstore=k                
                    if k[0]=='r' and len(k)==3:
                    	reg= int(k[1:],16)
                    	dstore="d"+format(reg,'03d')               
                    hass.data[DOMAIN]._data[kstore] = json_dict[k]
                    if kstore in id_reg:
                        if kstore!='r01' and kstore!='r03':
                        	hass.states.async_set("thermiq_mqtt."+id_reg[kstore],json_dict[k])
                    _LOGGER.debug("[%s] [%s] [%s]", kstore, json_dict[k],dstore)

# Do some post processing of data eceived
                hass.data[DOMAIN]._data['r01'] = (
                    hass.data[DOMAIN]._data["r01"] + hass.data[DOMAIN]._data["r02"] / 10
                )
                hass.states.async_set("thermiq_mqtt.t_rum_ar",hass.data[DOMAIN]._data['r01'])
                
                hass.data[DOMAIN]._data["r03"] = (
                    hass.data[DOMAIN]._data["r03"] + hass.data[DOMAIN]._data["r04"] / 10
                )
                hass.states.async_set("thermiq_mqtt.t_rum_bor",hass.data[DOMAIN]._data["r03"])
                try:
                    hass.data[DOMAIN]._data['rf0']=hass.data[DOMAIN]._data['indr_t']
                except:
                    hass.data[DOMAIN]._data['rf0']=-1
                    hass.data[DOMAIN]._data['indr_t']=-1
                
                
                hass.states.async_set(MSG_RECEIVED_STATE,json_dict['timestamp'])
                
                hass.bus.fire("thermiq_mqtt_msg_rec_event", {})
                
            else:
                _LOGGER.error("JSON result was not from ThermIQ-mqtt")
        except ValueError:
            _LOGGER.error("MQTT payload could not be parsed as JSON")
            _LOGGER.debug("Erroneous JSON: %s", payload)

    # Service to publish a message on MQTT.
    @callback
    def write_msg_service(call):
        """Service to send a message."""
        _LOGGER.debug("message.entity_id:[%s]", call.data.get("entity_id"))
        hass.async_create_task(hass.components.mqtt.async_publish(conf.cmd_topic, call.data.get("msg")))

    # Service to write specific reg with data, value_id will be translated to register number.
    @callback
    def write_reg_service(call):
        reg = call.data.get("reg")
        value = call.data.get("value")
        bitmask = call.data.get("bitmask")
        if bitmask is None:
            bitmask = 0xFFFF
        val = value | bitmask
        msg = f'{{"r{reg:x}": {value} }}'

        _LOGGER.debug("message.reg:[%s]", call.data.get("reg"))
        _LOGGER.debug("message.value:[%s]", call.data.get("value"))
        _LOGGER.debug("message.bitmask:[%s]", call.data.get("bitmask"))
        _LOGGER.debug("msg:[%s]", msg)
        hass.async_create_task(hass.components.mqtt.async_publish(conf.cmd_topic, msg))

    # Service to write specific value_id with data, value_id will be translated to register number.
    @callback
    def write_id_service(call):
        """Service to send a message."""
        _LOGGER.debug("message.value_id:[%s]", call.data.get("value_id"))
        _LOGGER.debug("message.payload:[%s]", call.data.get("value"))

        value_id = call.data.get("value_id").lower()
        idx = len(value_id) - (value_id.find(".thermiq") + 9)
        if idx > 0:
            value_id = value_id[-idx:]
        _LOGGER.debug("message.value_id:[%s]", value_id)
        if value_id in reg_id:
            reg = reg_id[value_id][0]
            kstore="r"+format(int(reg[1:],16),'02x')
            dstore="d"+format(int(reg[1:],16),'03d')    
            value = call.data.get("value")
            if not(isinstance(value, int)) or value is None:
                return
            bitmask = call.data.get("bitmask")
            if bitmask is None:
                bitmask = 0xFFFF
            value = int(value) & int(bitmask)
            msg = f'{{"{reg}": {value} }}'
            _LOGGER.debug("message.value:[%s]", call.data.get("value"))
            _LOGGER.debug("message.bitmask:[%s]", call.data.get("bitmask"))
            _LOGGER.debug("msg:[%s]", msg)

            if value != hass.data[DOMAIN]._data[reg]:
                hass.data[DOMAIN]._data[reg]=value
                hass.states.async_set("thermiq_mqtt."+id_reg[kstore],value)
                _LOGGER.debug("set reg[%s]=%d",reg,hass.data[DOMAIN]._data[reg])
                hass.async_create_task(hass.components.mqtt.async_publish(conf.cmd_topic, msg,2,False))
            else:
                _LOGGER.debug(
                    "No need to write"
                )  # Service to write specific value_id with data, value_id will be translated to register number.

    @callback
    def write_mode_service(call):
        """Service to send a message."""

        _LOGGER.debug("message.payload:[%s]", call.data.get("value"))
        reg = "r33"
        value = int(call.data.get("value"))
        if value is None:
            return
        bits = 2 ** value
        bitmask = 0x01F

        if bits is None:
            return
        value = int(bits) & int(bitmask)
        msg = f'{{"t{reg}": {value} }}'
        _LOGGER.debug("message.value:[%s]", call.data.get("value"))
        _LOGGER.debug("message.value:[%s]", value)
        _LOGGER.debug("msg:[%s]", msg)
        if value != hass.data[DOMAIN]._data[reg]:
            hass.states.async_set("thermiq_mqtt.d51")
            hass.async_create_task(hass.components.mqtt.async_publish(conf.cmd_topic, msg))
        else:
            _LOGGER.debug("No need to write")

    # ###
    # Register our service with Home Assistant.
    hass.services.async_register(DOMAIN, "write_msg", write_msg_service)
    hass.services.async_register(DOMAIN, "write_id", write_id_service)
    hass.services.async_register(DOMAIN, "write_reg", write_reg_service)
    hass.services.async_register(DOMAIN, "write_mode", write_mode_service)
    _LOGGER.info("Subscribe:" + conf.data_topic)
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
        res=self._data.get(item)
        _LOGGER.debug("get_value(" + item + ")=%d",res)
        return res

    def update_state(self, command, state_command):
        """Send update command to ThermIQ."""
        _LOGGER.debug("update_state:" + command + " " + state_command)
        self._data[state_command] = self._client.command(command)
        hass.async_create_task(hass.components.mqtt.async_publish(conf.cmd_topic, self._data[state_command]))

    async def async_update(self):
        _LOGGER.debug("Fetching data from ThermIQ-MQTT")
        _LOGGER.debug("Done fetching data from ThermIQ-MQTT")
