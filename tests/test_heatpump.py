"""Tests for HeatPump MQTT message handling and availability."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.thermiq_mqtt.heatpump import HeatPump, AVAILABILITY_TIMEOUT


def _make_heatpump(now=1000.0):
    hass = MagicMock()
    hass.loop.time.return_value = now
    entry = MagicMock()
    entry.data = {"id_name": "vp1"}
    hp = HeatPump(hass, entry)
    # mqtt_counter is normally initialised in update_config()
    hp._hpstate["mqtt_counter"] = 0
    return hp, hass


def _message(payload: dict):
    msg = MagicMock()
    msg.payload = json.dumps(payload)
    return msg


async def test_message_populates_state_and_combines_decimals():
    hp, hass = _make_heatpump()
    await hp.message_received(
        _message(
            {
                "Client_Name": "ThermIQ_x",
                "r00": 21,
                "r01": 20,
                "r02": 5,
                "r03": 18,
                "r04": 3,
            }
        )
    )
    assert hp._hpstate["r00"] == 21
    assert hp._hpstate["r01"] == pytest.approx(20.5)  # 20 + 5/10
    assert hp._hpstate["r03"] == pytest.approx(18.3)  # 18 + 3/10
    assert hp._hpstate["mqtt_counter"] == 1
    hass.bus.fire.assert_called()


async def test_decimals_not_combined_when_absent():
    hp, _ = _make_heatpump()
    # A partial message without r01/r02 must not touch r01
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "r00": 7}))
    assert hp._hpstate["r01"] is None


async def test_foreign_payload_is_ignored():
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "Other", "r00": 1}))
    assert hp._hpstate["r00"] is None
    assert hp._hpstate["mqtt_counter"] == 0


async def test_invalid_json_does_not_raise():
    hp, _ = _make_heatpump()
    msg = MagicMock()
    msg.payload = "{not valid json"
    await hp.message_received(msg)  # must not raise
    assert hp._hpstate["mqtt_counter"] == 0


async def test_unknown_key_does_not_abort_processing():
    hp, _ = _make_heatpump()
    # 'dXX' makes int() fail; r00 must still be stored
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "dXX": 1, "r00": 9})
    )
    assert hp._hpstate["r00"] == 9


async def test_availability_reflects_last_message():
    hp, hass = _make_heatpump(now=1000.0)
    assert hp.available is False  # nothing received yet
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "r00": 1}))
    assert hp.available is True
    # advance the clock past the timeout -> unavailable
    hass.loop.time.return_value = 1000.0 + AVAILABILITY_TIMEOUT.total_seconds() + 1
    assert hp.available is False


def _make_writable_heatpump():
    """A heatpump with the topics send_mqtt_reg needs, and a mocked publish."""
    hp, hass = _make_heatpump()
    hp._cmd_topic = "ThermIQ/ThermIQ-mqtt/write"
    hp._set_topic = "ThermIQ/ThermIQ-mqtt/set"
    hp._hexFormat = False
    return hp, hass


async def test_send_mqtt_reg_publishes_value_in_range():
    hp, hass = _make_writable_heatpump()
    with patch(
        "custom_components.thermiq_mqtt.heatpump.mqtt.async_publish",
        new=AsyncMock(),
    ) as publish:
        # indoor_requested_t (r32) allows 0..50
        await hp.send_mqtt_reg("indoor_requested_t", 21, 0xFFFF)
        hass.async_create_task.assert_called_once()
        publish.assert_called_once()
        topic, payload = publish.call_args[0][1], publish.call_args[0][2]
        assert topic == hp._cmd_topic
        assert json.loads(payload) == {"d050": 21}


async def test_send_mqtt_reg_rejects_value_out_of_range():
    hp, hass = _make_writable_heatpump()
    with patch(
        "custom_components.thermiq_mqtt.heatpump.mqtt.async_publish",
        new=AsyncMock(),
    ) as publish:
        await hp.send_mqtt_reg("indoor_requested_t", 95, 0xFFFF)
        publish.assert_not_called()
        hass.async_create_task.assert_not_called()


async def test_send_mqtt_reg_rejects_non_boolean_for_switch_register():
    hp, hass = _make_writable_heatpump()
    with patch(
        "custom_components.thermiq_mqtt.heatpump.mqtt.async_publish",
        new=AsyncMock(),
    ) as publish:
        await hp.send_mqtt_reg("heatpump_evu_block", 5, 0xFFFF)
        publish.assert_not_called()


async def test_send_mqtt_reg_accepts_boolean_for_switch_register():
    hp, hass = _make_writable_heatpump()
    with patch(
        "custom_components.thermiq_mqtt.heatpump.mqtt.async_publish",
        new=AsyncMock(),
    ) as publish:
        await hp.send_mqtt_reg("heatpump_evu_block", 1, 0xFFFF)
        publish.assert_called_once()
        topic, payload = publish.call_args[0][1], publish.call_args[0][2]
        assert topic == hp._set_topic
        assert json.loads(payload) == {"EVU": 1}


async def test_send_mqtt_reg_accepts_negative_value_in_range():
    hp, hass = _make_writable_heatpump()
    with patch(
        "custom_components.thermiq_mqtt.heatpump.mqtt.async_publish",
        new=AsyncMock(),
    ) as publish:
        # integral1_curve_p5 (r37) allows -5..5; the wire format is 16-bit
        # two's complement, so -3 must be published as 65533
        await hp.send_mqtt_reg("integral1_curve_p5", -3, 0xFFFF)
        publish.assert_called_once()
        payload = json.loads(publish.call_args[0][2])
        assert payload == {"d055": 65533}


async def test_send_mqtt_reg_rejects_negative_value_below_min():
    hp, hass = _make_writable_heatpump()
    with patch(
        "custom_components.thermiq_mqtt.heatpump.mqtt.async_publish",
        new=AsyncMock(),
    ) as publish:
        await hp.send_mqtt_reg("integral1_curve_p5", -6, 0xFFFF)
        publish.assert_not_called()


async def test_send_mqtt_reg_rejects_non_numeric_value():
    hp, hass = _make_writable_heatpump()
    with patch(
        "custom_components.thermiq_mqtt.heatpump.mqtt.async_publish",
        new=AsyncMock(),
    ) as publish:
        await hp.send_mqtt_reg("indoor_requested_t", "high", 0xFFFF)
        publish.assert_not_called()


# --- Capability detection from what the pump actually sends -------------


async def test_plain_mqtt_payload_reports_no_evu_or_room_sensor():
    """A plain ThermIQ-MQTT /data payload mentions neither key."""
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message(
            {
                "Client_Name": "ThermIQ_x",
                "app_info": "ThermIQ-mqtt 2.22",
                "d0": 21,
                "d50": 15,
            }
        )
    )
    assert hp.supports("r00") is True
    assert hp.supports("evu") is False
    assert hp.supports("indr_t") is False


async def test_room2_payload_reports_evu_and_room_sensor():
    """A ThermIQ-Room2 echoes EVU and INDR_T back, so both are drivable."""
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message(
            {
                "Client_Name": "ThermIQ_x",
                "app_info": "ThermIQ-room2 2.68",
                "d0": 17,
                "EVU": 0,
                "INDR_T": 21.1,
            }
        )
    )
    assert hp.supports("evu") is True
    assert hp.supports("indr_t") is True


async def test_capability_survives_a_message_that_omits_it():
    """Sticky: MISMATCH-style intermittent keys must not remove a control."""
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "EVU": 1, "d0": 17})
    )
    assert hp.supports("evu") is True
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "d0": 18}))
    assert hp.supports("evu") is True


async def test_integration_generated_values_count_as_present():
    """mqtt_counter, time_str and communication_status are ours, not the pump's."""
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "d0": 21, "time": "2026-08-12 20:00:00"})
    )
    for key in ("mqtt_counter", "time_str", "communication_status"):
        assert hp.supports(key) is True, key


async def test_nothing_is_supported_before_the_first_message():
    hp, _ = _make_heatpump()
    assert hp.supports("r00") is False
    assert hp.supports("evu") is False


# --- EVU corner cases, from mocked payloads -----------------------------
#
# EVU is the one control that does not travel as a numbered register: the
# pump echoes it under its own name, and the integration keys it as "evu".
# That makes it the register most likely to break in a way the numbered
# ones cannot, so the cases below pin both directions of the wire.
# Requested by @ThermIQ (fork issue #28).


@pytest.mark.parametrize("value", [0, 1])
async def test_evu_round_trips_through_a_payload(value):
    """Both states arrive, and both are readable as themselves."""
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message(
            {"Client_Name": "ThermIQ_x", "app_info": "ThermIQ-room2 2.68", "EVU": value}
        )
    )
    assert hp._hpstate["evu"] == value


async def test_evu_zero_is_a_value_not_an_absence():
    """The corner case worth having: 0 is a state, not a missing register.

    Capability detection keys off whether the pump ever mentioned EVU. A
    falsy value must not read as "this pump cannot do EVU" - that would
    make the control vanish exactly when the block is released.
    """
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "EVU": 0}))
    assert hp._hpstate["evu"] == 0
    assert hp.supports("evu") is True


async def test_evu_tracks_a_change_across_messages():
    hp, _ = _make_heatpump()
    for value in (1, 0, 1):
        await hp.message_received(_message({"Client_Name": "ThermIQ_x", "EVU": value}))
        assert hp._hpstate["evu"] == value
        assert hp.supports("evu") is True


async def test_evu_key_is_case_insensitive():
    """Keys are lowercased on the way in, so 'evu' and 'EVU' are one register."""
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "evu": 1}))
    assert hp._hpstate["evu"] == 1
    assert hp.supports("evu") is True


async def test_evu_arriving_as_a_string_is_stored_verbatim():
    """A quoted value is not coerced. The switch reads it through int(), so
    it still resolves; this records that the raw type reaches the state."""
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "EVU": "1"}))
    assert hp._hpstate["evu"] == "1"
    assert int(hp._hpstate["evu"]) == 1


async def test_d300_is_not_the_evu_capability():
    """d300 appears in the debug log as EVU's decimal alias, but it is only
    a log label: a payload carrying d300 does not make EVU drivable."""
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "d300": 1}))
    assert hp._hpstate.get("evu") is None
    assert hp.supports("evu") is False


@pytest.mark.parametrize("value", [0, 1])
async def test_evu_write_publishes_both_states_to_the_set_topic(value):
    """Releasing the block has to reach the pump as surely as setting it."""
    hp, _ = _make_writable_heatpump()
    with patch(
        "custom_components.thermiq_mqtt.heatpump.mqtt.async_publish",
        new=AsyncMock(),
    ) as publish:
        await hp.send_mqtt_reg("heatpump_evu_block", value, 0xFFFF)
        publish.assert_called_once()
        topic, payload = publish.call_args[0][1], publish.call_args[0][2]
        assert topic == hp._set_topic
        assert json.loads(payload) == {"EVU": value}


@pytest.mark.parametrize("value", [2, -1])
async def test_evu_write_refuses_anything_that_is_not_a_boolean(value):
    hp, _ = _make_writable_heatpump()
    with patch(
        "custom_components.thermiq_mqtt.heatpump.mqtt.async_publish",
        new=AsyncMock(),
    ) as publish:
        await hp.send_mqtt_reg("heatpump_evu_block", value, 0xFFFF)
        publish.assert_not_called()
