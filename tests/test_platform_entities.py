"""Unit tests for the number/select/switch entities.

The entities read the shared heatpump state and write via send_mqtt_reg,
so a HeatPump with a mocked hass and a mocked send_mqtt_reg is enough -
no full Home Assistant instance is needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.thermiq_mqtt.heatpump import HeatPump
from custom_components.thermiq_mqtt.heatpump.thermiq_regs import FIELD_REGNUM, reg_id
from custom_components.thermiq_mqtt.number import ThermIQNumber
from custom_components.thermiq_mqtt.select import ThermIQSelect
from custom_components.thermiq_mqtt.switch import ThermIQSwitch


def _make_heatpump(has_data=True, echoed=None):
    hass = MagicMock()
    hass.loop.time.return_value = 1000.0
    entry = MagicMock()
    entry.data = {"id_name": "vp1"}
    hp = HeatPump(hass, entry)
    hp._hpstate["mqtt_counter"] = 1 if has_data else 0
    if has_data:
        hp._last_message_time = 1000.0
        # A pump that has sent data has sent registers; entities are only
        # available for registers this pump actually reports. Default to the
        # generous case so each test states its own capability question.
        hp._echoed = set(reg_id[k][FIELD_REGNUM] for k in reg_id)
    if echoed is not None:
        hp._echoed = set(echoed)
    hp.send_mqtt_reg = AsyncMock()  # type: ignore[method-assign]
    return hp


# --- Number -----------------------------------------------------------


def test_number_reads_register_and_bounds():
    hp = _make_heatpump()
    entity = ThermIQNumber(hp, "indoor_requested_t")  # r32, 0..50
    assert entity.native_value is None
    hp._hpstate["r32"] = 20
    assert entity.native_value == 20
    assert entity.native_min_value == 0
    assert entity.native_max_value == 50
    assert entity.available is True


async def test_number_write_sends_mqtt():
    hp = _make_heatpump()
    entity = ThermIQNumber(hp, "indoor_requested_t")
    hp._hpstate["r32"] = 20
    await entity.async_set_native_value(21)
    hp.send_mqtt_reg.assert_awaited_once_with("indoor_requested_t", 21, 0xFFFF)
    assert hp._hpstate["r32"] == 21


async def test_number_write_ignored_without_data():
    hp = _make_heatpump(has_data=False)
    entity = ThermIQNumber(hp, "indoor_requested_t")
    await entity.async_set_native_value(21)
    hp.send_mqtt_reg.assert_not_awaited()


async def test_number_write_resends_an_unchanged_value():
    """A repeat write must reach the pump.

    This used to be skipped when the cached value already matched. But the
    cache holds the last value the *pump reported*, not the result of the last
    write - so if a write was lost, sending the same value again did nothing
    at all, and there was no way to retry from the UI.
    """
    hp = _make_heatpump()
    entity = ThermIQNumber(hp, "indoor_requested_t")
    hp._hpstate["r32"] = 21
    await entity.async_set_native_value(21)
    hp.send_mqtt_reg.assert_awaited_once_with("indoor_requested_t", 21, 0xFFFF)


async def test_switch_write_resends_an_unchanged_value():
    hp = _make_heatpump()
    entity = ThermIQSwitch(hp, "heatpump_evu_block")
    hp._hpstate["evu"] = 1
    await entity.async_turn_on()
    hp.send_mqtt_reg.assert_awaited_once_with("heatpump_evu_block", 1, 0xFFFF)


async def test_select_write_resends_an_unchanged_value():
    hp = _make_heatpump()
    entity = ThermIQSelect(hp, "main_mode")
    hp._hpstate["r33"] = 2
    await entity.async_select_option(entity.options[2])
    hp.send_mqtt_reg.assert_awaited_once_with("main_mode", 2, 0xFFFF)


async def test_writes_survive_a_config_reload():
    """Saving options must not re-arm the "no data yet" guard.

    update_config runs on every options save and every entry reload, and it
    used to reset mqtt_counter to 0. The entities refuse to write while that
    is 0, so for the ~30 s until the pump's next message every setpoint change
    was silently dropped - nothing published, nothing logged above DEBUG, and
    the control springing back in the UI.
    """
    hp = _make_heatpump()
    entity = ThermIQNumber(hp, "indoor_requested_t")

    entry = MagicMock()
    entry.data = {
        "id_name": "vp1",
        "mqtt_node": "ThermIQ/ThermIQ-mqtt",
        "language": "en",
        "hexformat": False,
        "thermiq_dbg": False,
    }
    await hp.update_config(entry)

    assert hp._hpstate["mqtt_counter"] == 1, "the message count must survive a reload"
    await entity.async_set_native_value(21)
    hp.send_mqtt_reg.assert_awaited_once_with("indoor_requested_t", 21, 0xFFFF)


async def test_first_setup_still_refuses_to_write():
    """The guard itself must still work: no write before the pump has spoken."""
    hp = _make_heatpump(has_data=False)
    del hp._hpstate["mqtt_counter"]  # as it is before any update_config

    entry = MagicMock()
    entry.data = {
        "id_name": "vp1",
        "mqtt_node": "ThermIQ/ThermIQ-mqtt",
        "language": "en",
        "hexformat": False,
        "thermiq_dbg": False,
    }
    await hp.update_config(entry)

    assert hp._hpstate["mqtt_counter"] == 0
    entity = ThermIQNumber(hp, "indoor_requested_t")
    await entity.async_set_native_value(21)
    hp.send_mqtt_reg.assert_not_awaited()


def test_number_unavailable_before_first_message():
    hp = _make_heatpump(has_data=False)
    entity = ThermIQNumber(hp, "indoor_requested_t")
    assert entity.available is False


# --- Select -----------------------------------------------------------


def test_select_maps_register_to_option():
    hp = _make_heatpump()
    entity = ThermIQSelect(hp, "main_mode")  # r33
    assert entity.current_option is None
    hp._hpstate["r33"] = 2
    assert entity.current_option is not None
    assert entity.current_option.startswith("2 - ")
    assert len(entity.options) == 5


async def test_select_write_sends_mqtt():
    hp = _make_heatpump()
    entity = ThermIQSelect(hp, "main_mode")
    hp._hpstate["r33"] = 0
    option = entity.options[2]
    await entity.async_select_option(option)
    hp.send_mqtt_reg.assert_awaited_once_with("main_mode", 2, 0xFFFF)
    assert hp._hpstate["r33"] == 2


async def test_select_rejects_unknown_option():
    hp = _make_heatpump()
    entity = ThermIQSelect(hp, "main_mode")
    await entity.async_select_option("not a mode")
    hp.send_mqtt_reg.assert_not_awaited()


# --- Switch -----------------------------------------------------------


def test_switch_reads_register():
    hp = _make_heatpump()
    entity = ThermIQSwitch(hp, "heatpump_evu_block")  # reg 'evu'
    assert entity.is_on is None
    hp._hpstate["evu"] = 1
    assert entity.is_on is True
    hp._hpstate["evu"] = 0
    assert entity.is_on is False


async def test_switch_turn_on_off_sends_mqtt():
    hp = _make_heatpump()
    entity = ThermIQSwitch(hp, "heatpump_evu_block")
    hp._hpstate["evu"] = 0
    await entity.async_turn_on()
    hp.send_mqtt_reg.assert_awaited_once_with("heatpump_evu_block", 1, 0xFFFF)
    hp.send_mqtt_reg.reset_mock()
    await entity.async_turn_off()
    hp.send_mqtt_reg.assert_awaited_once_with("heatpump_evu_block", 0, 0xFFFF)


async def test_switch_write_ignored_without_data():
    hp = _make_heatpump(has_data=False)
    entity = ThermIQSwitch(hp, "heatpump_evu_block")
    await entity.async_turn_on()
    hp.send_mqtt_reg.assert_not_awaited()


# --- Binary sensor -----------------------------------------------------


def _make_binary(hp, key="compressor_on"):
    from custom_components.thermiq_mqtt.binary_sensor import HeatPumpBinarySensor
    from custom_components.thermiq_mqtt.heatpump.thermiq_regs import (
        FIELD_BITMASK,
        FIELD_REGNUM,
        reg_id,
    )

    return HeatPumpBinarySensor(
        hp._hass, hp, key, reg_id[key][FIELD_REGNUM], key, reg_id[key][FIELD_BITMASK]
    )


async def test_binary_sensor_unknown_until_data_then_bitmask():
    hp = _make_heatpump()
    ent = _make_binary(hp)  # compressor_on = r10 bit 0x0002
    ent.hass = hp._hass
    ent.async_write_ha_state = MagicMock()
    assert ent._attr_is_on is None  # unknown, not off
    hp._hpstate["r10"] = 0x0002
    await ent._async_update_event(None)
    assert ent._attr_is_on is True
    hp._hpstate["r10"] = 0x0000
    await ent._async_update_event(None)
    assert ent._attr_is_on is False


async def test_binary_sensor_none_register_reports_unknown():
    hp = _make_heatpump()
    ent = _make_binary(hp)
    ent.hass = hp._hass
    ent.async_write_ha_state = MagicMock()
    hp._hpstate["r10"] = 1  # known ...
    await ent._async_update_event(None)
    hp._hpstate["r10"] = None  # ... then register disappears
    await ent._async_update_event(None)
    assert ent._attr_is_on is None


async def test_binary_sensor_writes_on_availability_transition_only():
    hp = _make_heatpump()
    ent = _make_binary(hp)
    ent.hass = hp._hass
    ent.async_write_ha_state = MagicMock()
    hp._hpstate["r10"] = 0x0002
    await ent._async_update_event(None)
    assert ent.async_write_ha_state.call_count == 1
    # unchanged value + unchanged availability -> no write
    await ent._async_update_event(None)
    assert ent.async_write_ha_state.call_count == 1
    # availability flips (pump goes silent) -> write even though value unchanged
    hp._last_message_time = None
    await ent._async_update_event(None)
    assert ent.async_write_ha_state.call_count == 2


# --- Capability detection from the echoed payload ----------------------
#
# EVU is ThermIQ-Room2 only and the room-sensor setpoint needs a Room or a
# Room2. Rather than keep a table of models - which the user can defeat by
# renaming the MQTT node, and which goes stale when a new interface ships -
# the pump is taken at its word: what it sends is what it can drive.


def test_control_is_unavailable_when_the_pump_never_sends_the_register():
    """Plain ThermIQ-MQTT: no EVU in /data, so no EVU switch to press."""
    hp = _make_heatpump(echoed={"r32", "mqtt_counter"})
    hp._last_message_time = 1000.0
    evu = ThermIQSwitch(hp, "heatpump_evu_block")
    room = ThermIQNumber(hp, "room_sensor_set_t")
    assert evu.available is False
    assert room.available is False
    # ...while a register it does send stays available
    assert ThermIQNumber(hp, "indoor_requested_t").available is True


def test_control_is_available_when_the_pump_echoes_the_register():
    """ThermIQ-Room2: EVU and INDR_T come back in /data, so both work."""
    hp = _make_heatpump(echoed={"evu", "indr_t", "r32"})
    hp._last_message_time = 1000.0
    assert ThermIQSwitch(hp, "heatpump_evu_block").available is True
    assert ThermIQNumber(hp, "room_sensor_set_t").available is True


def test_capability_is_sticky_once_seen():
    """A key present in one message and absent from the next must not flap."""
    hp = _make_heatpump(echoed=set())
    hp._last_message_time = 1000.0
    evu = ThermIQSwitch(hp, "heatpump_evu_block")
    assert evu.available is False
    hp._echoed |= {"evu"}  # one message carried it
    assert evu.available is True
    hp._echoed |= {"r32"}  # a later message did not
    assert evu.available is True


def test_silence_still_wins_over_capability():
    """Supporting a register does not make a silent pump available."""
    hp = _make_heatpump(has_data=False, echoed={"evu"})
    assert ThermIQSwitch(hp, "heatpump_evu_block").available is False
