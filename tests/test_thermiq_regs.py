"""Integrity tests for the ThermIQ register table.

These are pure-data checks and do not need a running Home Assistant.
"""

from custom_components.thermiq_mqtt.heatpump.thermiq_regs import (
    reg_id,
    id_names,
    FIELD_REGTYPE,
    FIELD_MINVALUE,
    FIELD_MAXVALUE,
)

VALID_TYPES = {
    "temperature",
    "temperature_input",
    "sensor",
    "sensor_input",
    "sensor_boolean",
    "sensor_language",
    "time",
    "time_input",
    "binary_sensor",
    "select_input",
    "generated_input",
    "generated_sensor",
    "generated_input_boolean",
}

NUMBER_TYPES = {"temperature_input", "time_input", "sensor_input", "generated_input"}


def test_every_register_has_seven_fields():
    for key, value in reg_id.items():
        assert len(value) == 7, f"{key} has {len(value)} fields, expected 7"


def test_register_types_are_known():
    for key, value in reg_id.items():
        assert (
            value[FIELD_REGTYPE] in VALID_TYPES
        ), f"{key}: unknown type {value[FIELD_REGTYPE]}"


def test_number_registers_have_ordered_numeric_bounds():
    for key, value in reg_id.items():
        if value[FIELD_REGTYPE] in NUMBER_TYPES:
            lo, hi = value[FIELD_MINVALUE], value[FIELD_MAXVALUE]
            assert isinstance(lo, (int, float)), f"{key} min not numeric: {lo!r}"
            assert isinstance(hi, (int, float)), f"{key} max not numeric: {hi!r}"
            assert lo <= hi, f"{key} min {lo} > max {hi}"


def test_translation_entries_have_five_languages():
    # AVAILABLE_LANGUAGES = en, se, fi, no, de
    for key, names in id_names.items():
        assert len(names) == 5, f"{key} has {len(names)} translations, expected 5"


def test_select_modes_are_translated():
    # The main_mode select exposes modes 0..4
    for i in range(5):
        assert f"mode{i}" in id_names, f"mode{i} missing from translations"
        assert all(n for n in id_names[f"mode{i}"]), f"mode{i} has empty translation"


def test_reverse_lookup_is_unambiguous_for_writable_registers():
    # Writable registers (number/select/switch) must not share a register
    # number, since the reverse lookup maps register -> single id_name.
    writable = NUMBER_TYPES | {"select_input", "generated_input_boolean"}
    seen: dict[str, str] = {}
    for key, value in reg_id.items():
        if value[FIELD_REGTYPE] in writable:
            reg = value[0]
            assert reg not in seen, f"register {reg} shared by {seen[reg]} and {key}"
            seen[reg] = key
