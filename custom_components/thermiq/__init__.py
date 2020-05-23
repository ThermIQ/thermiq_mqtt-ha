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

# import homeassistant.loader as loader




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


# Register as sensors
reg_id = {
    #  reg_id          : ['reg#' ],
    "T_UTE": ["r00", "temperature"],
    "T_RUM_AR": ["r01", "temperature"],
    "T_RUM_AR_DEC": ["r02", "temperature"],
    "T_RUM_BOR": ["r03", "temperature"],
    "T_RUM_BOR_DEC": ["r04", "temperature"],
    "T_FRAM": ["r05", "temperature"],
    "T_RETUR": ["r06", "temperature"],
    "T_VATTEN": ["r07", "temperature"],
    "T_BRINE_UT": ["r08", "temperature"],
    "T_BRINE_IN": ["r09", "temperature"],
    "T_KYLNING": ["r0a", "temperature"],
    "T_FRAM_SHUNT": ["r0b", "temperature"],
    "STROMFORBR": ["r0c", "sensor"],
    "TS_1": ["r0d", "binary_sensor", 0x0001],
    "TS_2": ["r0d", "binary_sensor", 0x0002],
    "T_FRAM_BOR": ["r0e", "temperature"],
    "T_FRAM_SHUNT_BOR": ["r0f", "temperature"],
    "BRINE": ["r10", "binary_sensor", 0x0001],
    "KOMPR": ["r10", "binary_sensor", 0x0002],
    "CIRKP": ["r10", "binary_sensor", 0x0004],
    "VARMVATTEN": ["r10", "binary_sensor", 0x0008],
    "TS2": ["r10", "binary_sensor", 0x0010],
    "SHUNTN": ["r10", "binary_sensor", 0x0020],
    "SHUNTP": ["r10", "binary_sensor", 0x0040],
    "TS1": ["r10", "binary_sensor", 0x0080],
    "SHNTGRPN": ["r11", "binary_sensor", 0x0001],
    "SHNTGRPP": ["r11", "binary_sensor", 0x0002],
    "SHNT_KYLN": ["r11", "binary_sensor", 0x0004],
    "SHNT_KYLP": ["r11", "binary_sensor", 0x0008],
    "AKT_KYL": ["r11", "binary_sensor", 0x0010],
    "PASS_KYL": ["r11", "binary_sensor", 0x0020],
    "LARM": ["r11", "binary_sensor", 0x0040],
    "PWM_UT": ["r12", "sensor"],
    "ALM_HP": ["r13", "binary_sensor", 0x0001],
    "ALM_LP": ["r13", "binary_sensor", 0x0002],
    "ALM_MS": ["r13", "binary_sensor", 0x0004],
    "ALM_BLF": ["r13", "binary_sensor", 0x0008],
    "ALM_BLT": ["r13", "binary_sensor", 0x0010],
    "ALM_UTE": ["r14", "binary_sensor", 0x0001],
    "ALM_FRAM": ["r14", "binary_sensor", 0x0002],
    "ALM_RETUR": ["r14", "binary_sensor", 0x0004],
    "ALM_VV": ["r14", "binary_sensor", 0x0008],
    "ALM_RUM": ["r14", "binary_sensor", 0x0010],
    "ALM_FAS": ["r14", "binary_sensor", 0x0020],
    "ALM_OVRH": ["r14", "binary_sensor", 0x0040],
    "BEHOV1": ["r15", "sensor"],
    "BEHOV2": ["r16", "sensor"],
    "TRYCKR_T": ["r17", "temperature"],
    "HGW_VV": ["r18", "temperature"],
    "INTEGR": ["r19", "sensor"],
    "INTGR_STEG": ["r1a", "sensor"],
    "CLK_VV": ["r1b", "time"],
    "MIN_TIME_START": ["r1c", "time"],
    "SW_VER": ["r1d", "sensor"],
    "CIRK_SPEED": ["r1e", "sensor"],
    "BRINE_SPEED": ["r1f", "sensor"],
    "CLK_VV_STOP": ["r20", "sensor"],
    "RUM_BOR2": ["r32", "temperature_input", 0, 50],
    "DL": ["r33", "select_input", 0, 16],
    "KURVA": ["r34", "temperature_input", 0, 200],
    "KURVA_MIN": ["r35", "temperature_input", 0, 200],
    "KURVA_MAX": ["r36", "temperature_input", 0, 200],
    "KURVA_P5": ["r37", "temperature_input", 0, 200],
    "KURVA_0": ["r38", "temperature_input", 0, 200],
    "KURVA_N5": ["r39", "temperature_input", 0, 200],
    "VARME_STP": ["r3a", "temperature_input", 0, 200],
    "SANKN_T": ["r3b", "temperature_input", 0, 100],
    "RUMFAKT": ["r3c", "temperature_input", 0, 100],
    "KURVA2": ["r3d", "temperature_input", 0, 200],
    "KURVA2_MIN": ["r3e", "temperature_input", 0, 200],
    "KURVA2_MAX": ["r3f", "temperature_input", 0, 200],
    "KURVA2_BOR": ["r40", "temperature_input", 0, 200],
    "KURVA2_AR": ["r41", "temperature_input", 0, 200],
    "STATUS6": ["r42", "temperature_input", 0, 100],
    "TRYCKR_LIMIT": ["r43", "temperature_input", 0, 200],
    "VV_START": ["r44", "temperature_input", 0, 100],
    "VV_TID": ["r45", "time_input", 0, 32767],
    "VARME_TID": ["r46", "time_input", 0, 32767],
    "LEG_INTERV": ["r47", "time_input", 0, 32767],
    "LEG_STOP_T": ["r48", "temperature_input", 0, 100],
    "INTEGR_A1": ["r49", "sensor_input", -32768, 32767],
    "HYST_VP": ["r4a", "temperature_input", 0, 100],
    "MAX_RET": ["r4b", "temperature_input", 0, 100],
    "MIN_ST_INT": ["r4c", "time_input", 0, 32767],
    "MIN_BRINE_T": ["r4d", "temperature_input", -25, 100],
    "KYLA_BOR": ["r4e", "temperature_input", 0, 50],
    "INTEGR_A2": ["r4f", "sensor_input", 0, 200],
    "HYST_TS": ["r50", "temperature_input", 0, 100],
    "MAX_STEG_TS": ["r51", "sensor_input", -32768, 32767],
    "MAX_STROM": ["r52", "sensor_input", -32768, 32767],
    "SHUNTTID": ["r53", "time_input", 0, 32767],
    "VV_STOP": ["r54", "temperature_input", 0, 100],
    "TEST_MODE": ["r55", "sensor"],
    "STATUS7": ["r56", "sensor"],
    "LANG": ["r57", "sensor_language"],
    "STATUS8": ["r58", "sensor"],
    "FABRIKSINST": ["r59", "sensor"],
    "RESET_DR_TID": ["r5a", "sensor_boolean"],
    "CAL_UTE": ["r5b", "temperature"],
    "CAL_FRAM": ["r5c", "temperature"],
    "CAL_RET": ["r5d", "temperature"],
    "CAL_VV": ["r5e", "temperature"],
    "CAL_BRUT": ["r5f", "temperature"],
    "CAL_BRIN": ["r60", "temperature"],
    "SYS_TYP": ["r61", "sensor"],
    "TILL_FASM": ["r62", "binary_sensor", 0x0001],
    "TILL_2": ["r62", "binary_sensor", 0x0002],
    "TILL_HGW": ["r62", "binary_sensor", 0x0004],
    "TILL_4": ["r62", "binary_sensor", 0x0008],
    "TILL_5": ["r62", "binary_sensor", 0x0010],
    "TILL_6": ["r62", "binary_sensor", 0x0020],
    "TILL_OPT": ["r62", "binary_sensor", 0x0040],
    "TILL_FW": ["r62", "binary_sensor", 0x0080],
    "LOG_TIM": ["r63", "time"],
    "BRINE_TIM_ON": ["r64", "time"],
    "BRINE_TIM_OFF": ["r65", "time"],
    "LEG_TOP_ON": ["r66", "sensor_boolean"],
    "LEG_TOP_TIM": ["r67", "time"],
    "DR_TIM_VP": ["r68", "time"],
    "STATUS10": ["r69", "sensor"],
    "DR_TIM_TS1": ["r6a", "time"],
    "STATUS11": ["r6b", "sensor"],
    "DR_TIM_VV": ["r6c", "time"],
    "STATUS12": ["r6d", "sensor"],
    "DR_TIM_PAS_KYL": ["r6e", "time"],
    "STATUS13": ["r6f", "sensor"],
    "DR_TIM_AKT_KYL": ["r70", "time"],
    "STATUS14": ["r71", "sensor"],
    "DR_TIM_TS2": ["r72", "time"],
    "STATUS15": ["r73", "sensor"],
    "STATUS16": ["r74", "sensor"],
    "t_sensor_meassured": ["r00", "temperature", 0, 50],
    "t_sensor_target": ["r00", "temperature", 0, 50],
    "SENSOR_MEASSURED": ["rf0", "temperature", 0, 50],
    "SENSOR_TARGET": ["rf1", "temperature", 0, 50],
}

# Translation dictionary
id_names = {
    "T_UTE": "Outdoor temp.",
    "T_RUM_AR": "Indoor temp.",
    "T_RUM_AR_DEC": "Indoor temp., decimal",
    "T_RUM_BOR": "Indoor target temp.",
    "T_RUM_BOR_DEC": "Indoor target temp., decimal",
    "T_FRAM": "Supplyline temp.",
    "T_RETUR": "Returnline temp.",
    "T_VATTEN": "Hotwater temp.",
    "T_BRINE_UT": "Brine out temp.",
    "T_BRINE_IN": "Brine in temp.",
    "T_KYLNING": "Cooling temp.",
    "T_FRAM_SHUNT": "Supplyline temp., shunt",
    "STROMFORBR": "Electrical Current",
    "TS_1": "Aux. heater 3 kW",
    "TS_2": "Aux. heater 6 kW",
    "T_FRAM_BOR": "Supplyline target temp.",
    "T_FRAM_SHUNT_BOR": "Supplyline target temp., shunt",
    "BRINE": "Brinepump",
    "KOMPR": "Compressor",
    "CIRKP": "Flowlinepump",
    "VARMVATTEN": "Hotwater production.",
    "TS2": "Auxilliary 2",
    "SHUNTN": "Shunt -",
    "SHUNTP": "Shunt +",
    "TS1": "Auxilliary 1",
    "SHNTGRPN": "Shuntgroup -",
    "SHNTGRPP": "Shuntgroup +",
    "SHNT_KYLN": "Shunt cooling -",
    "SHNT_KYLP": "Shunt cooling +",
    "AKT_KYL": "Active cooling",
    "PASS_KYL": "Passive cooling",
    "LARM": "Alarm",
    "PWM_UT": "PWM Out",
    "ALM_HP": "Alarm highpr.pressostate",
    "ALM_LP": "Alarm lowpr.pressostate",
    "ALM_MS": "Alarm motorcircuit breaker",
    "ALM_BLF": "Alarm low flow brine",
    "ALM_BLT": "Alarm low temp. brine",
    "ALM_UTE": "Alarm outdoor t-sensor",
    "ALM_FRAM": "Alarm supplyline t-sensor",
    "ALM_RETUR": "Alarm returnline t-sensor",
    "ALM_VV": "Alarm hotw. t-sensor",
    "ALM_RUM": "Alarm indoor t-sensor",
    "ALM_FAS": "Alarm incorrect 3-phase order",
    "ALM_OVRH": "Alarm overheating",
    "BEHOV1": "DEMAND1",
    "BEHOV2": "DEMAND2",
    "TRYCKR_T": "Pressurepipe temp.",
    "HGW_VV": "Hotw. supplyline temp.",
    "INTEGR": "Integral",
    "INTGR_STEG": "Integral, reached A-limit",
    "CLK_VV": "Defrost",
    "MIN_TIME_START": "Minimum time to start",
    "SW_VER": "Program version",
    "CIRK_SPEED": "Flowlinepump speed",
    "BRINE_SPEED": "Brinepump speed",
    "CLK_VV_STOP": "STATUS3",
    "RUM_BOR2": "Indoor target temp.",
    "DL": "Mode",
    "KURVA": "Curve",
    "KURVA_MIN": "Curve min",
    "KURVA_MAX": "Curve max",
    "KURVA_P5": "Curve +5",
    "KURVA_0": "Curve 0",
    "KURVA_N5": "Curve -5",
    "VARME_STP": "Heatstop",
    "SANKN_T": "Temp. reduction",
    "RUMFAKT": "Room factor",
    "KURVA2": "Curve 2",
    "KURVA2_MIN": "Curve 2 min",
    "KURVA2_MAX": "Curve 2 max",
    "KURVA2_BOR": "Curve 2, Target",
    "KURVA2_AR": "Curve 2, Actual",
    "STATUS6": "Outdoor stop temp. (20=-20C)",
    "TRYCKR_LIMIT": "Pressurepipe, temp. limit",
    "VV_START": "Hotwater starttemp.",
    "VV_TID": "Hotwater operating time",
    "VARME_TID": "Heatpump operating time",
    "LEG_INTERV": "Legionella interval",
    "LEG_STOP_T": "Legionella stop temp.",
    "INTEGR_A1": "Integral limit A1",
    "HYST_VP": "Hysteresis, heatpump",
    "MAX_RET": "Returnline temp., max limit",
    "MIN_ST_INT": "Minimum starting interval",
    "MIN_BRINE_T": "Brinetemp., min limit (-15=OFFV)",
    "KYLA_BOR": "Cooling, target",
    "INTEGR_A2": "Integral limit A2",
    "HYST_TS": "Hysteresis limit, aux",
    "MAX_STEG_TS": "Max step, aux",
    "MAX_STROM": "Electrical current, max limit",
    "SHUNTTID": "Shunt time",
    "VV_STOP": "Hotwater stop temp.",
    "TEST_MODE": "Manual test mode",
    "STATUS7": "DT_LARMOFF",
    "LANG": "Language",
    "STATUS8": "SERVFAS",
    "FABRIKSINST": "Factory settings",
    "RESET_DR_TID": "Reset runtime counters",
    "CAL_UTE": "Calibration outdoor sensor",
    "CAL_FRAM": "Calibration supplyline sensor",
    "CAL_RET": "Calibration returnline sensor",
    "CAL_VV": "Calibration hotwater sensor",
    "CAL_BRUT": "Calibration brine out sensor",
    "CAL_BRIN": "Calibration brine in sensor",
    "SYS_TYP": "Heating system type 0=VL 4=D",
    "TILL_FASM": "Add-on phase order measurement",
    "TILL_2": "TILL2",
    "TILL_HGW": "Add-on HGW",
    "TILL_4": "TILL4",
    "TILL_5": "TILL5",
    "TILL_6": "TILL6",
    "TILL_OPT": "Add-on Optimum",
    "TILL_FW": "Add-on flow guard",
    "LOG_TIM": "Logging time",
    "BRINE_TIM_ON": "Brine run-out duration",
    "BRINE_TIM_OFF": "Brine run-in duration",
    "LEG_TOP_ON": "Legionella peak heating enable",
    "LEG_TOP_TIM": "Legionella peak heating duration",
    "DR_TIM_VP": "Runtime compressor",
    "STATUS10": "DVP_MSD1",
    "DR_TIM_TS1": "Runtime 3 kW",
    "STATUS11": "DTS_MSD1",
    "DR_TIM_VV": "Runtime hotwater production",
    "STATUS12": "DVV_MSD1",
    "DR_TIM_PAS_KYL": "Runtime passive cooling",
    "STATUS13": "DPAS_MSD1",
    "DR_TIM_AKT_KYL": "Runtime active cooling",
    "STATUS14": "DACT_MSD1",
    "DR_TIM_TS2": "Runtime 6 kW",
    "STATUS15": "DTS2_MSD1",
    "STATUS16": "GrafCounterOffSet",
}
# Unit dictionary
id_units = {
    "T_UTE": "C",
    "T_RUM_AR": "C",
    "T_RUM_AR_DEC": "0.1C",
    "T_RUM_BOR": "C",
    "T_RUM_BOR_DEC": "0.1C",
    "T_FRAM": "C",
    "T_RETUR": "C",
    "T_VATTEN": "C",
    "T_BRINE_UT": "C",
    "T_BRINE_IN": "C",
    "T_KYLNING": "C",
    "T_FRAM_SHUNT": "C",
    "STROMFORBR": "A",
    "TS_1": "Boolean",
    "TS_2": "Boolean",
    "T_FRAM_BOR": "C",
    "T_FRAM_SHUNT_BOR": "C",
    "BRINE": "Boolean",
    "KOMPR": "Boolean",
    "CIRKP": "Boolean",
    "VARMVATTEN": "Boolean",
    "TS2": "Boolean",
    "SHUNTN": "Boolean",
    "SHUNTP": "Boolean",
    "TS1": "Boolean",
    "SHNTGRPN": "Boolean",
    "SHNTGRPP": "Boolean",
    "SHNT_KYLN": "Boolean",
    "SHNT_KYLP": "Boolean",
    "AKT_KYL": "Boolean",
    "PASS_KYL": "Boolean",
    "LARM": "Boolean",
    "PWM_UT": "Units",
    "ALM_HP": "Boolean",
    "ALM_LP": "Boolean",
    "ALM_MS": "Boolean",
    "ALM_BLF": "Boolean",
    "ALM_BLT": "Boolean",
    "ALM_UTE": "Boolean",
    "ALM_FRAM": "Boolean",
    "ALM_RETUR": "Boolean",
    "ALM_VV": "Boolean",
    "ALM_RUM": "Boolean",
    "ALM_FAS": "Boolean",
    "ALM_OVRH": "Boolean",
    "BEHOV1": "  ",
    "BEHOV2": "  ",
    "TRYCKR_T": "C",
    "HGW_VV": "C",
    "INTEGR": "C*min",
    "INTGR_STEG": "  ",
    "CLK_VV": "*10s",
    "MIN_TIME_START": "min",
    "SW_VER": "  ",
    "CIRK_SPEED": "%",
    "BRINE_SPEED": "%",
    "CLK_VV_STOP": "  ",
    "RUM_BOR2": "C",
    "DL": "lage #",
    "KURVA": "C",
    "KURVA_MIN": "C",
    "KURVA_MAX": "C",
    "KURVA_P5": "C",
    "KURVA_0": "C",
    "KURVA_N5": "C",
    "VARME_STP": "C",
    "SANKN_T": "C",
    "RUMFAKT": "C",
    "KURVA2": "C",
    "KURVA2_MIN": "C",
    "KURVA2_MAX": "C",
    "KURVA2_BOR": "C",
    "KURVA2_AR": "C",
    "STATUS6": "C",
    "TRYCKR_LIMIT": "C",
    "VV_START": "C",
    "VV_TID": "min",
    "VARME_TID": "min",
    "LEG_INTERV": "days",
    "LEG_STOP_T": "C",
    "INTEGR_A1": "C*min",
    "HYST_VP": "C",
    "MAX_RET": "C",
    "MIN_ST_INT": "min",
    "MIN_BRINE_T": "C",
    "KYLA_BOR": "C",
    "INTEGR_A2": "10C*min",
    "HYST_TS": "C",
    "MAX_STEG_TS": "# steps",
    "MAX_STROM": "A",
    "SHUNTTID": "s",
    "VV_STOP": "C",
    "TEST_MODE": "mode #",
    "STATUS7": "  ",
    "LANG": "language #",
    "STATUS8": "  ",
    "FABRIKSINST": "setting #",
    "RESET_DR_TID": "Boolean",
    "CAL_UTE": "C",
    "CAL_FRAM": "C",
    "CAL_RET": "C",
    "CAL_VV": "C",
    "CAL_BRUT": "C",
    "CAL_BRIN": "C",
    "SYS_TYP": "type #",
    "TILL_FASM": "Boolean",
    "TILL_2": "Boolean",
    "TILL_HGW": "Boolean",
    "TILL_4": "Boolean",
    "TILL_5": "Boolean",
    "TILL_6": "Boolean",
    "TILL_OPT": "Boolean",
    "TILL_FW": "Boolean",
    "LOG_TIM": "min",
    "BRINE_TIM_ON": "*10s",
    "BRINE_TIM_OFF": "*10s",
    "LEG_TOP_ON": "Boolean",
    "LEG_TOP_TIM": "h",
    "DR_TIM_VP": "h",
    "STATUS10": "  ",
    "DR_TIM_TS1": "h",
    "STATUS11": "  ",
    "DR_TIM_VV": "h",
    "STATUS12": "  ",
    "DR_TIM_PAS_KYL": "h",
    "STATUS13": "  ",
    "DR_TIM_AKT_KYL": "h",
    "STATUS14": "  ",
    "DR_TIM_TS2": "h",
    "STATUS15": "  ",
    "STATUS16": "  ",
}


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
