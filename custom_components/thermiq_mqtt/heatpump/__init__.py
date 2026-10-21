from __future__ import annotations

import json
import logging

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from ..const import (
    DOMAIN,
    CONF_ID,
    CONF_MQTT_NODE,
    CONF_MQTT_HEX,
    CONF_MQTT_DBG,
    CONF_LANGUAGE,
    AVAILABLE_LANGUAGES,
)

# import ThermIQ register defines
from .thermiq_regs import (
    FIELD_MAXVALUE,
    FIELD_MINVALUE,
    FIELD_REGTYPE,
    reg_id,
)

_LOGGER = logging.getLogger(__name__)

# The ThermIQ bridge publishes a data message roughly every 30 s. If nothing is
# received for this long the heatpump is considered unreachable and its entities
# report unavailable. The watchdog re-checks on this interval.
AVAILABILITY_TIMEOUT = timedelta(seconds=120)
AVAILABILITY_CHECK_INTERVAL = timedelta(seconds=30)

# Register types whose min/max fields are true numeric bounds. For
# generated_input_boolean the same table slot holds the bitmask, so it is
# validated separately (only 0/1 allowed).
BOUNDED_REGTYPES = {
    "temperature_input",
    "time_input",
    "sensor_input",
    "generated_input",
    "select_input",
}


class HeatPump:

    _dbg: bool = True
    _mqtt_base: str = ""
    _hexFormat: bool = False
    _langid: int = 0
    _data_topic: str = ""
    _cmd_topic: str = ""
    _set_topic: str = ""
    # Monotonic timestamp of the last message; None until the first one
    _last_message_time: float | None = None

    unsubscribe_callback: Callable[[], None] | None

    # ###
    async def message_received(self, message: mqtt.ReceiveMessage) -> None:
        """Handle new MQTT messages."""
        _LOGGER.debug("%s: message.payload:[%s]", self._id, message.payload)
        try:
            json_dict = json.loads(message.payload)
        except ValueError:
            _LOGGER.error("MQTT payload could not be parsed as JSON")
            _LOGGER.debug("Erroneous JSON: %s", message.payload)
            return

        if (
            not isinstance(json_dict, dict)
            or str(json_dict.get("Client_Name", ""))[:8] != "ThermIQ_"
        ):
            _LOGGER.error("JSON result was not from ThermIQ-mqtt")
            return

        # Track which registers arrived in this message
        received = set()

        for k in json_dict.keys():
            # A malformed key must not abort processing of the remaining keys
            try:
                kstore = k.lower()
                dstore = k
                if kstore == "evu":
                    dstore = "d300"
                # # Create hex notation if incoming register is decimal format
                # Named registers must be longer than 4 characters to avoid confusion
                if k[0] == "d" and len(k) < 5:
                    reg = int(k[1:])
                    kstore = "r" + format(reg, "02x")
                    dstore = "d" + format(reg, "03d")
                    if len(kstore) != 3:
                        kstore = k
                # Create decimal notation if incoming register is hex format
                if k[0] == "r" and len(k) == 3:
                    reg = int(k[1:], 16)
                    dstore = "d" + format(reg, "03d")

                _LOGGER.debug(
                    "[%s] [%s] [%s] [%s]", self._id, kstore, json_dict[k], dstore
                )

                # Store the value under its canonical register key. The
                # number/select/switch/sensor/binary_sensor entities read from
                # this shared state when the msg_rec_event fires below, so the
                # incoming heatpump values always win over the UI.
                self._hpstate[kstore] = json_dict[k]
                received.add(kstore)
            except (ValueError, KeyError, IndexError, TypeError) as err:
                _LOGGER.warning(
                    "Could not process key [%s] in MQTT message: %s", k, err
                )

        # Do some post processing of data received
        # r01/r03 are combined with their decimal parts r02/r04, but only when
        # they arrived in this message - otherwise the decimal part would
        # compound onto an already combined value
        r01 = self._hpstate.get("r01")
        r02 = self._hpstate.get("r02")
        if (
            "r01" in received
            and isinstance(r01, (int, float))
            and isinstance(r02, (int, float))
        ):
            self._hpstate["r01"] = r01 + r02 / 10

        r03 = self._hpstate.get("r03")
        r04 = self._hpstate.get("r04")
        if (
            "r03" in received
            and isinstance(r03, (int, float))
            and isinstance(r04, (int, float))
        ):
            self._hpstate["r03"] = r03 + r04 / 10

        self._hpstate["mqtt_counter"] += 1

        if "time" in json_dict:
            self._hpstate["time_str"] = json_dict["time"]
        elif "Time" in json_dict:
            self._hpstate["time_str"] = json_dict["Time"]

        if "vp_read" in json_dict:
            self._hpstate["communication_status"] = json_dict["vp_read"]
        else:
            self._hpstate["communication_status"] = "Ok"

        # These three are this integration's own bookkeeping rather than
        # anything the pump sends, so they count as present the moment a
        # message is processed at all.
        received.update(("mqtt_counter", "time_str", "communication_status"))

        # What the pump actually sends is what it can actually do. EVU and the
        # room-sensor setpoint are the clear cases - a ThermIQ-Room2 echoes
        # them back in /data, a plain ThermIQ-MQTT never mentions them and
        # cannot act on them either - but the rule needs no list of models to
        # apply, and no lookup table to keep current when new interfaces ship.
        #
        # Only ever grows. A register that appears in one message and not the
        # next stays supported, so an intermittently reported capability
        # cannot make an entity flicker in and out of existence.
        self._echoed |= received

        if "app_info" in json_dict:
            self._hpstate["app_info"] = json_dict["app_info"]

        # Record receipt time for the availability watchdog
        self._last_message_time = self._hass.loop.time()
        self._was_available = True

        self._hass.bus.fire(self._domain + "_" + self._id + "_msg_rec_event", {})

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._hpstate: dict[str, Any] = {}
        # Register keys this pump has ever sent; see message_received.
        self._echoed: set[str] = set()
        self._domain = DOMAIN
        self._id: str = entry.data[CONF_ID]
        self._id_reg: dict[str, str] = {}
        self.unsubscribe_callback = None
        self._watchdog_unsub: Callable[[], None] | None = None
        self._last_message_time = None
        self._was_available = False

        # Create reverse lookup dictionary (id_reg->reg_number)
        # Registers start as None (unknown) until the first MQTT message;
        # -1 would make every bitmask test true and light up all alarms
        for k, v in reg_id.items():
            self._id_reg[v[0]] = k
            self._hpstate[v[0]] = None

    async def setup_mqtt(self) -> None:
        self.unsubscribe_callback = await mqtt.async_subscribe(
            self._hass,
            self._data_topic,
            self.message_received,
        )
        # Watchdog to flip entities to unavailable when messages stop arriving
        if self._watchdog_unsub is None:
            self._watchdog_unsub = async_track_time_interval(
                self._hass,
                self._availability_watchdog,
                AVAILABILITY_CHECK_INTERVAL,
            )

    @property
    def available(self) -> bool:
        """True while recent data has been received from the heatpump."""
        if self._last_message_time is None:
            return False
        return bool(
            (self._hass.loop.time() - self._last_message_time)
            < AVAILABILITY_TIMEOUT.total_seconds()
        )

    def supports(self, register: str) -> bool:
        """True if this pump has ever sent this register.

        The interfaces differ in what they can drive: EVU is ThermIQ-Room2
        only, and the room-sensor setpoint needs a Room or a Room2. Offering
        those controls on hardware that cannot act on them gives the user a
        switch that publishes, is ignored, and springs back - which reads as a
        broken integration rather than as unsupported hardware.

        Asking the data rather than the model avoids two traps. The MQTT node
        name is chosen by the user during setup, so it says nothing about the
        hardware behind it; and app_info is a name rather than a capability, so
        it needs a lookup table that goes stale the day a new interface ships.
        What arrives in /data is what the pump will actually act on.

        Before the first message this returns False for everything, which
        costs nothing: `available` is False then anyway.
        """
        return register in self._echoed

    async def _availability_watchdog(self, _now: datetime) -> None:
        """Notify entities when availability changes (e.g. comms lost)."""
        available = self.available
        if available != self._was_available:
            self._was_available = available
            self._hass.bus.fire(self._domain + "_" + self._id + "_msg_rec_event", {})

    async def update_config(self, entry: ConfigEntry) -> None:
        if self.unsubscribe_callback is not None:
            self.unsubscribe_callback()
        lang = entry.data[CONF_LANGUAGE]
        self._langid = AVAILABLE_LANGUAGES.index(lang)
        self._dbg = entry.data[CONF_MQTT_DBG]
        self._mqtt_base = entry.data[CONF_MQTT_NODE] + "/"
        self._hexFormat = entry.data[CONF_MQTT_HEX]
        self._data_topic = self._mqtt_base + "data"
        if self._dbg is True:
            # Debug mode diverts all writes to dbg_ topics so that a real
            # heatpump is never affected. The topics must be derived AFTER
            # applying the prefix, otherwise debug writes would still reach
            # the real heatpump
            self._cmd_topic = self._mqtt_base + "dbg_write"
            self._set_topic = self._mqtt_base + "dbg_set"
            _LOGGER.warning(
                "MQTT Debug write enabled, writes are diverted to [%s]",
                self._cmd_topic,
            )
        else:
            self._cmd_topic = self._mqtt_base + "write"
            self._set_topic = self._mqtt_base + "set"
        # Only seed the counter, never reset it. update_config runs on every
        # options save and every entry reload, and the entities refuse to
        # write while this is 0 - so resetting it here made every setpoint
        # change silently do nothing for the ~30 s until the next message,
        # with nothing above DEBUG to say why.
        if not isinstance(self._hpstate.get("mqtt_counter"), (int, float)):
            self._hpstate["mqtt_counter"] = 0

        # Provide some debug info
        _LOGGER.debug(
            f"INFO: {self._domain}_{self._id} mqtt_node: [{entry.data[CONF_MQTT_NODE]}]"
        )

        _LOGGER.debug("Language[%s]", self._langid)

        if self._hexFormat == True:
            _LOGGER.debug("INFO: Using HEX format")

    async def async_reset(self) -> bool:
        """Reset this heatpump: unsubscribe from MQTT.

        The number/select/switch/sensor/binary_sensor entities are removed by
        async_unload_platforms during config entry unload.
        """
        if self.unsubscribe_callback is not None:
            self.unsubscribe_callback()
            self.unsubscribe_callback = None
        if self._watchdog_unsub is not None:
            self._watchdog_unsub()
            self._watchdog_unsub = None
        return True

    @property
    def hpstate(self) -> dict[str, Any]:
        return self._hpstate

    def set_value(self, item: str, value: Any) -> None:
        """Set value for sensor."""
        _LOGGER.debug("set_value(" + item + ")=" + str(value))
        self._hpstate[item] = value

    def get_value(self, item: str) -> Any:
        """Get value for sensor."""
        res = self._hpstate.get(item)
        _LOGGER.debug("get_value(%s)=%s", item, res)
        return res

    def update_state(self, command: str, state_command: str) -> None:
        """Send MQTT message to ThermIQ."""
        _LOGGER.debug("update_state:" + command + " " + state_command)
        # self._data[state_command] = self._client.command(command)
        # hass.async_create_task(
        #     mqtt.async_publish(
        #         self._hass, conf.cmd_topic, self._data[state_command]
        #     )
        # )

    # ### ##################################################################
    # Write a specific value_id with data; value_id is translated to a register
    # number. Used by the number/select/switch entities to write to the pump.

    async def send_mqtt_reg(
        self, register_id: str, value: Any, bitmask: int | None
    ) -> None:
        """Service to send a message."""

        register = reg_id[register_id][0]
        _LOGGER.debug("register:[%s]", register)

        if isinstance(value, bool):
            # Templated service calls render true/false as Python bools
            value = int(value)
        if not isinstance(value, (int, float)):
            _LOGGER.error(
                "No MQTT message sent: value [%s] for register [%s] is not numeric",
                value,
                register_id,
            )
            return

        if bitmask is None:
            bitmask = 0xFFFF

        if not (register in self._id_reg):
            _LOGGER.error("No MQTT message sent due to unknown register:[%s]", register)
            return

        # Defense in depth: never publish a value the register table does not
        # allow, regardless of what the caller (UI, automation, service call)
        # asked for. The pump itself does not range-check writes.
        # Validation MUST run on the raw value BEFORE the bitmask conversion:
        # negative values (heating curve +-5, brine_min_t, sensor offsets) are
        # sent as 16-bit two's complement, which would land far outside the
        # register bounds if checked after masking.
        regtype = reg_id[register_id][FIELD_REGTYPE]
        if regtype == "generated_input_boolean":
            if value not in (0, 1):
                _LOGGER.error(
                    "No MQTT message sent: value [%s] for boolean register [%s] "
                    "must be 0 or 1",
                    value,
                    register_id,
                )
                return
        elif regtype in BOUNDED_REGTYPES:
            min_value = reg_id[register_id][FIELD_MINVALUE]
            max_value = reg_id[register_id][FIELD_MAXVALUE]
            if not (min_value <= value <= max_value):
                _LOGGER.error(
                    "No MQTT message sent: value [%s] for register [%s] is "
                    "outside the allowed range [%s..%s]",
                    value,
                    register_id,
                    min_value,
                    max_value,
                )
                return
        else:
            # Read-only or unknown register types are never writable; without
            # this branch they would bypass validation entirely
            _LOGGER.error(
                "No MQTT message sent: register [%s] (type %s) is not writable",
                register_id,
                regtype,
            )
            return

        ## check the bitmask
        # value = value | bitmask
        if register_id == "room_sensor_set_t":
            value = float(value)
        else:
            value = int(value) & int(bitmask)

        # Lets use the decimal register notation in the MQTT message towards ThermIQ-MQTT to improve human readability

        if register == "indr_t":
            topic = self._set_topic
            payload = json.dumps({"INDR_T": value})
        elif register == "evu":
            topic = self._set_topic
            payload = json.dumps({"EVU": value})
        elif self._hexFormat:
            # dreg = "d" + format(int(register[1:], 16), "03d")
            topic = self._cmd_topic
            payload = json.dumps({register: value})
        else:
            dreg = "d" + format(int(register[1:], 16), "03d")
            topic = self._cmd_topic
            payload = json.dumps({dreg: value})

        _LOGGER.debug("topic:[%s]", topic)
        _LOGGER.debug("payload:[%s]", payload)
        self._hass.async_create_task(
            mqtt.async_publish(self._hass, topic, payload, qos=2, retain=False)
        )
