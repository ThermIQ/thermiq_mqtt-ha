"""Constants for the component."""

# Component domain, used to store component data in hass data.
DOMAIN = "thermiq_mqtt"

# == ThermIQ Const
CONF_ID = "id_name"
CONF_MQTT_NODE = "mqtt_node"
CONF_MQTT_DBG = "thermiq_dbg"
CONF_MQTT_HEX = "hexformat"
CONF_LANGUAGE = "language"
DEFAULT_NODE = "ThermIQ/ThermIQ-mqtt"
CONF_DATA = "data_msg"
DEFAULT_DATA = "/data"
CONF_CMD = "cmd_msg"
DEFAULT_CMD = "/write"
DEFAULT_DBG = False
AVAILABLE_LANGUAGES = ["en", "se", "fi", "no", "de"]


PLATFORM_AUTOMATION = "automation"
PLATFORM_BINARY_SENSOR = "binary_sensor"
PLATFORM_GROUP = "group"
PLATFORM_INPUT_BOOLEAN = "input_boolean"
PLATFORM_INPUT_NUMBER = "input_number"
PLATFORM_INPUT_SELECT = "input_select"
PLATFORM_INPUT_TEXT = "input_text"
CONF_ENTITY_PLATFORM = "entity_platform"
