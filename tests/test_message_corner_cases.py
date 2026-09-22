"""Corner cases on the /data payload, mocked message by message.

Requested by @ThermIQ (fork issue #28): a complete set of MQTT messages
covering the edges of `HeatPump.message_received`, so a change to the ingest
path fails a named test rather than a user's dashboard.

Every expectation here was read off the running code, not assumed. Where the
behaviour is merely *current* rather than obviously *right*, the test says so
in its docstring - those are the ones worth an opinion from someone who knows
what the hardware actually emits.

The companion catalogue, including the payloads that need answers before they
can become assertions, is in tests/CORNER_CASES.md.
"""

import json
from unittest.mock import MagicMock

import pytest

from custom_components.thermiq_mqtt.heatpump import HeatPump


def _make_heatpump(now=1000.0):
    hass = MagicMock()
    hass.loop.time.return_value = now
    entry = MagicMock()
    entry.data = {"id_name": "vp1"}
    hp = HeatPump(hass, entry)
    hp._hpstate["mqtt_counter"] = 0
    return hp, hass


def _raw(payload: str):
    """A message carrying an exact byte string, valid JSON or not."""
    msg = MagicMock()
    msg.payload = payload
    return msg


def _message(payload: dict):
    return _raw(json.dumps(payload))


# --- The envelope ------------------------------------------------------
#
# Everything is gated on Client_Name starting with "ThermIQ_". A broker
# carries other traffic, and a payload that is not ours must leave the state
# untouched rather than half-applied.


@pytest.mark.parametrize(
    ("label", "name"),
    [
        ("normal", "ThermIQ_x"),
        ("exactly the prefix", "ThermIQ_"),
        ("long suffix", "ThermIQ_kitchen_pump_2"),
    ],
)
async def test_accepted_client_names(label, name):
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": name, "r00": 7}))
    assert hp._hpstate["r00"] == 7, label
    assert hp._hpstate["mqtt_counter"] == 1


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("someone else's device", {"Client_Name": "Other", "r00": 7}),
        ("no Client_Name at all", {"r00": 7}),
        ("prefix one char short", {"Client_Name": "ThermIQ", "r00": 7}),
        ("wrong case", {"Client_Name": "thermiq_x", "r00": 7}),
        ("numeric Client_Name", {"Client_Name": 12345678, "r00": 7}),
    ],
)
async def test_rejected_envelopes_change_nothing(label, payload):
    """A rejected message must not count, and must not store a register."""
    hp, _ = _make_heatpump()
    await hp.message_received(_message(payload))
    assert hp._hpstate["r00"] is None, label
    assert hp._hpstate["mqtt_counter"] == 0, label


@pytest.mark.parametrize(
    ("label", "raw"),
    [
        ("truncated object", "{not json"),
        ("empty payload", ""),
        ("whitespace only", "   "),
        ("a JSON array", "[1, 2, 3]"),
        ("a bare JSON string", '"hello"'),
        ("a bare JSON null", "null"),
        ("a bare JSON number", "42"),
    ],
)
async def test_non_object_payloads_are_ignored_without_raising(label, raw):
    """None of these may raise: an exception here kills the MQTT callback."""
    hp, _ = _make_heatpump()
    await hp.message_received(_raw(raw))
    assert hp._hpstate["mqtt_counter"] == 0, label


# --- Register key formats ----------------------------------------------
#
# The same register can arrive three ways: hex (r0b), decimal (d011), or by
# name (EVU). Keys are lowercased, so case is not a distinguishing feature.


@pytest.mark.parametrize(
    ("label", "key", "stored_as"),
    [
        ("hex, numeric", "r00", "r00"),
        ("hex, with a letter", "r0b", "r0b"),
        ("hex, uppercase", "R00", "r00"),
        ("decimal, one digit", "d0", "r00"),
        ("decimal, two digits", "d50", "r32"),
        ("decimal, three digits", "d050", "r32"),
    ],
)
async def test_key_formats_land_on_the_same_register(label, key, stored_as):
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", key: 7}))
    assert hp._hpstate[stored_as] == 7, label


async def test_a_key_that_is_not_a_register_is_kept_verbatim():
    """`d300` looks like a decimal register but is not one.

    int("300") formats to hex "12c", so the candidate key "r12c" is four
    characters where a register key is three - the code then falls back to
    the key as sent. This is why d300 does not reach `evu`, and the reason
    is arithmetic rather than intent.
    """
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "d300": 1}))
    assert hp._hpstate["d300"] == 1
    assert hp._hpstate.get("evu") is None
    assert hp._hpstate.get("r12c") is None


async def test_an_unknown_register_is_stored_rather_than_dropped():
    """Current behaviour: r99 is not in the register table, and is kept.

    Nothing reads it, so it is inert. Worth knowing before anyone assumes
    the state dict only ever holds known registers.
    """
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "r99": 5}))
    assert hp._hpstate["r99"] == 5


async def test_one_unparseable_key_does_not_lose_the_others():
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "dXX": 1, "r00": 9, "r05": 3})
    )
    assert hp._hpstate["r00"] == 9
    assert hp._hpstate["r05"] == 3


# --- Value types -------------------------------------------------------
#
# JSON can carry more than integers, and the ingest path stores whatever
# arrives. These record what reaches the entities.


@pytest.mark.parametrize(
    ("label", "value", "expected"),
    [
        ("integer", 7, 7),
        ("negative integer", -8, -8),
        ("float", 7.5, 7.5),
        ("zero", 0, 0),
        ("null", None, None),
        ("boolean true", True, True),
        ("string digits", "7", "7"),
    ],
)
async def test_value_types_are_stored_as_sent(label, value, expected):
    """No coercion happens on the way in; consumers apply int()/float()."""
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "r00": value}))
    assert hp._hpstate["r00"] == expected, label


# --- The split decimals -------------------------------------------------
#
# r01/r02 and r03/r04 are whole degrees and tenths. Combining them twice
# would compound the fraction, so it happens only when the whole part
# arrived in the same message.


async def test_tenths_combine_when_both_arrive():
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "r01": 21, "r02": 4, "r03": 18, "r04": 7})
    )
    assert hp._hpstate["r01"] == pytest.approx(21.4)
    assert hp._hpstate["r03"] == pytest.approx(18.7)


async def test_tenths_alone_do_not_compound_onto_an_earlier_value():
    """The guard that matters: a second message carrying only the tenths."""
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "r01": 21, "r02": 4})
    )
    assert hp._hpstate["r01"] == pytest.approx(21.4)
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "r02": 9}))
    assert hp._hpstate["r01"] == pytest.approx(21.4)  # not 21.4 + 0.9


async def test_whole_degrees_alone_stay_whole():
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "r01": 21}))
    assert hp._hpstate["r01"] == 21


# --- The integration's own bookkeeping ---------------------------------


@pytest.mark.parametrize("key", ["time", "Time"])
async def test_either_spelling_of_time_populates_the_clock(key):
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", key: "2026-08-14 20:00:00"})
    )
    assert hp._hpstate["time_str"] == "2026-08-14 20:00:00"


async def test_lowercase_time_wins_when_both_are_present():
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "time": "lower", "Time": "upper"})
    )
    assert hp._hpstate["time_str"] == "lower"


async def test_vp_read_becomes_the_communication_status():
    """MISMATCH is the value worth caring about: the interface is talking to
    us but not getting clean answers from the pump."""
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "vp_read": "MISMATCH"})
    )
    assert hp._hpstate["communication_status"] == "MISMATCH"


async def test_absent_vp_read_reads_as_ok():
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "r00": 1}))
    assert hp._hpstate["communication_status"] == "Ok"


async def test_a_later_message_without_vp_read_clears_a_mismatch():
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "vp_read": "MISMATCH"})
    )
    await hp.message_received(_message({"Client_Name": "ThermIQ_x", "r00": 1}))
    assert hp._hpstate["communication_status"] == "Ok"


async def test_app_info_is_recorded():
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "app_info": "ThermIQ-room2 2.68"})
    )
    assert hp._hpstate["app_info"] == "ThermIQ-room2 2.68"


async def test_the_counter_advances_once_per_accepted_message():
    hp, _ = _make_heatpump()
    for expected in (1, 2, 3):
        await hp.message_received(_message({"Client_Name": "ThermIQ_x", "r00": 1}))
        assert hp._hpstate["mqtt_counter"] == expected
    await hp.message_received(_message({"Client_Name": "Other", "r00": 1}))
    assert hp._hpstate["mqtt_counter"] == 3


# --- Capability detection ----------------------------------------------


async def test_a_capability_survives_an_intermittent_absence():
    """A MISMATCH round can drop keys from one message. An entity must not
    disappear because of it."""
    hp, _ = _make_heatpump()
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "EVU": 1, "INDR_T": 21.1})
    )
    assert hp.supports("evu") is True
    assert hp.supports("indr_t") is True
    await hp.message_received(
        _message({"Client_Name": "ThermIQ_x", "vp_read": "MISMATCH"})
    )
    assert hp.supports("evu") is True
    assert hp.supports("indr_t") is True


async def test_a_rejected_message_grants_no_capability():
    hp, _ = _make_heatpump()
    await hp.message_received(_message({"Client_Name": "Other", "EVU": 1}))
    assert hp.supports("evu") is False
