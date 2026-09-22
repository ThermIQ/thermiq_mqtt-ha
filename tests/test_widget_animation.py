"""Tests for the widget's flow animations, which nothing else can check.

Every flow in the drawing is two elements that have to agree: a dashed path
whose ``stroke-dashoffset`` animates, and one or more chevron arrowheads driven
along the same path by ``offset-path``. Nothing in the markup relates them, so
they agree only because two numbers were written the same way twice.

They diverge silently. Both halves animate, so the drawing still moves and a
screenshot still looks right - the head simply travels at a different speed to
the dashes it sits in, which is only obvious once someone watches it for a few
seconds on a live install. That is how it was found (#82), and only at low pump
speed: the two expressions agree at --vpw:100 and diverge as the multiplier
falls, so the bug hides at exactly the speed a demo or a busy pump runs at.
"""

import re
from pathlib import Path

TEMPLATE = Path("custom_components/thermiq_mqtt/frontend/heatpump_widget.j2")

# <path d="..." ... animation:vpd<N> <duration> linear infinite ...>
DASH_PATH = re.compile(
    r'<path\s+d="([^"]+)"[^>]*?animation:(vpd[A-Za-z0-9]+) ([^;"]+?) linear infinite',
    re.S,
)
# <path ... offset-path:path('...');...animation:vpoffs <duration> linear infinite ...>
CHEVRON = re.compile(
    r"offset-path:path\('([^']+)'\)[^\"]*?animation:vpoffs ([^;\"]+?) linear infinite",
    re.S,
)


def _normalise(duration: str) -> str:
    """Collapse whitespace so `calc(2.4s * 100 / var(--vpw))` compares cleanly."""
    return " ".join(duration.split())


def _dash_durations() -> dict[str, str]:
    text = TEMPLATE.read_text(encoding="utf-8")
    return {d: _normalise(dur) for d, _name, dur in DASH_PATH.findall(text)}


def _chevron_durations() -> list[tuple[str, str]]:
    text = TEMPLATE.read_text(encoding="utf-8")
    return [(d, _normalise(dur)) for d, dur in CHEVRON.findall(text)]


def test_the_template_still_has_animated_flows():
    """A guard on the regexes: silence here would make every test below pass."""
    assert len(_dash_durations()) >= 10
    assert len(_chevron_durations()) >= 20


def test_every_arrowhead_follows_a_path_that_is_actually_drawn():
    """An offset-path with no dashed path behind it is an arrow in mid-air."""
    dashes = _dash_durations()
    for path, _duration in _chevron_durations():
        assert path in dashes, f"arrowhead follows an undrawn path: {path}"


def test_arrowheads_move_at_the_speed_of_the_dashes_they_sit_in():
    """The head and its line must carry the same duration expression.

    Not merely the same number: `2.4s` and `calc(2.4s * 100 / var(--vpw))` are
    equal only while the pump reports 100%, which is why the supply riser looked
    correct until someone watched it with the pump stopped.
    """
    dashes = _dash_durations()
    mismatched = []
    for path, duration in _chevron_durations():
        if dashes.get(path) != duration:
            mismatched.append(
                f"  {path}\n    line: {dashes[path]}\n    head: {duration}"
            )

    report = "arrowhead and dash speeds differ:\n" + "\n".join(mismatched)
    assert not mismatched, report


def test_water_flows_scale_with_their_pump_and_refrigerant_does_not():
    """Each circuit is paced by its own pump, and the compressor by nothing.

    `--vpw` is the supply pump, `--vpb` the brine pump. The refrigerant loop is
    deliberately fixed: the compressor is single-speed, so a rate there would be
    invented rather than measured. A flow that scales with the wrong pump, or a
    water flow that does not scale at all, is the bug this catches.
    """
    durations = _dash_durations()
    well_formed = re.compile(r"^(?:[\d.]+s|calc\([\d.]+s \* 100 / var\(--vp[wb]\)\))$")
    for path, duration in durations.items():
        assert well_formed.match(duration), f"{path}: malformed duration {duration}"

    values = list(durations.values())
    assert any("var(--vpw)" in d for d in values), "no flow paced by the supply pump"
    assert any("var(--vpb)" in d for d in values), "no flow paced by the brine pump"

    # The refrigerant loop is the only thing that may be unscaled, and it is
    # three paths inside the cabinet. If that count grows, a water flow has
    # most likely lost its pump rather than a new refrigerant path appearing.
    unscaled = [p for p, d in durations.items() if "var(" not in d]
    assert len(unscaled) == 3, f"expected 3 fixed-rate flows, found: {unscaled}"
