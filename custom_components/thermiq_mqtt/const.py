"""Constants for the component."""

# Component domain, used to store component data in hass data.
DOMAIN = "thermiq_mqtt"

# Database version, used to migrate old versions of data in the recorded history.
DATABASE_VERSION = 1.6
CONF_DB_VERSION = "database_version"
CONF_MIGRATE_DATA = "migrate_data"

# == ThermIQ Const
CONF_ID = "id_name"
CONF_MQTT_NODE = "mqtt_node"
CONF_MQTT_DBG = "thermiq_dbg"
CONF_MQTT_HEX = "hexformat"
CONF_LANGUAGE = "language"

AVAILABLE_LANGUAGES = ["en", "se", "fi", "no", "de"]
