#!/usr/bin/env python3
"""Render the widget template to a standalone HTML page, outside Home Assistant.

The widget is a Jinja2 template that Home Assistant renders as HTML: an SVG
schematic plus absolutely positioned HTML badges, a compressor and two pumps,
with flow arrows placed by CSS ``offset-path``. This script stubs out the two
template globals Home Assistant provides - ``states()`` and ``is_state()`` -
so the same template can be rendered from a shell, and wraps the result in the
page scaffold the card builds at runtime.

What it is for: **measuring the drawing in a browser.** Every element in the
template is absolutely positioned, so nothing reflows and two badges can
overlap silently - no markup relates them and only arithmetic keeps them apart.
Point a headless browser at the output of this script and
``getBoundingClientRect()`` will tell you what actually happens, per scenario.
That is how the badge collision fixed in v3.5.11-beta.1 was found; squinting at
screenshots did not find it in the four releases before.

Usage:
    python3 tools/render_widget_html.py -o /tmp/widget.html
    python3 tools/render_widget_html.py -o /tmp/dhw.html \\
        --state binary_sensor.thermiq_mqtt_vp1_hotwaterproduction_on=on \\
        --state input_boolean.hpviz_demo=off

Requires Jinja2. Prints unstubbed entities to stderr, so a template that starts
reading a new entity says so rather than silently rendering it as "unknown".

There used to be a second mode here that composed a static SVG for the README.
It was removed once the README moved to a real screenshot (#56): composing an
SVG means re-implementing text metrics, and the two places it did that were
both wrong - it assumed the 16px inherited font the badges stopped using in
v3.5.6, and it ignored the clock badge's ``width:auto`` override, emitting 35px
where a browser measures 78.3. A browser already knows all of this, which is
the whole argument for rendering HTML and measuring it there instead.
"""

from __future__ import annotations

import argparse
import os
import sys

from jinja2 import Environment

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(
    REPO, "custom_components", "thermiq_mqtt", "frontend", "heatpump_widget.j2"
)

# The drawing needs 357px of card inner width; `_fit()` centres it but never
# scales, so a narrower card leaves it left-aligned rather than clipping it.
# 492px is the width measured on a live dashboard.
CARD_W = 492
CARD_H = 343

# mdi:home-roof, from Templarian/MaterialDesign (Apache-2.0), viewBox 0 0 24 24.
# <ha-icon> only exists inside Home Assistant; without a stand-in the roof does
# not draw and its fallback text shows instead, which reads as a broken render.
MDI_HOME_ROOF = "M19 16H22L12 7L2 16H5L12 9.69L19 16M7 8.81V7H4V11.5L7 8.81Z"

# Demo values: compressor and both pumps running, no hot-water production,
# Optimum fitted so the pump-speed badges are visible. Override per run with
# --state, which is how a scenario sweep varies one condition at a time.
STATES = {
    "input_boolean.hpviz_demo": "on",
    "binary_sensor.pool_heating_active": "off",
    "binary_sensor.thermiq_mqtt_vp1_alarm_indication_on": "off",
    "binary_sensor.thermiq_mqtt_vp1_boiler_3kw_on": "off",
    "binary_sensor.thermiq_mqtt_vp1_boiler_6kw_on": "off",
    "binary_sensor.thermiq_mqtt_vp1_brine_pump_on": "on",
    "binary_sensor.thermiq_mqtt_vp1_compressor_on": "on",
    "binary_sensor.thermiq_mqtt_vp1_hotwaterproduction_on": "off",
    "binary_sensor.thermiq_mqtt_vp1_opt_hgw_installed": "on",
    "binary_sensor.thermiq_mqtt_vp1_opt_optimum_installed": "on",
    "binary_sensor.thermiq_mqtt_vp1_supply_pump_on": "on",
    "number.thermiq_mqtt_vp1_integral2_curve_target": "28",
    "sensor.thermiq_mqtt_vp1_boiler_t": "52",
    "sensor.thermiq_mqtt_vp1_brine_in_t": "2",
    "sensor.thermiq_mqtt_vp1_brine_out_t": "-1",
    "sensor.thermiq_mqtt_vp1_brine_pump_speed": "65",
    "sensor.thermiq_mqtt_vp1_communication_status": "Ok",
    "sensor.thermiq_mqtt_vp1_heating_stop_t": "17",
    "sensor.thermiq_mqtt_vp1_hgw_water_t": "45",
    "sensor.thermiq_mqtt_vp1_indoor_t": "21",
    "sensor.thermiq_mqtt_vp1_outdoor_t": "-3",
    "sensor.thermiq_mqtt_vp1_pressurepipe_t": "78",
    "sensor.thermiq_mqtt_vp1_returnline_t": "32",
    "sensor.thermiq_mqtt_vp1_supply_pump_speed": "70",
    "sensor.thermiq_mqtt_vp1_supply_shunt_t": "38",
    "sensor.thermiq_mqtt_vp1_supplyline_t": "38",
    "sensor.thermiq_mqtt_vp1_time_str": "demo data",
    "switch.thermiq_mqtt_vp1_heatpump_evu_block": "off",
}

# Mirrors what thermiq-widget-card.js builds around the template: an ha-card
# with 16px padding, and the drawing in a position:relative containing block.
# Padding has to be on the card, not on that block - an absolutely positioned
# child's containing block is its parent's padding *box*, so padding there
# would not inset the drawing at all.
PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>ThermIQ widget</title><style>
html,body{{margin:0;padding:24px;background:#f2f4f7;
  font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
#hacard{{box-sizing:border-box;width:{card_w}px;padding:16px;background:#fff;
  border-radius:12px;box-shadow:0 2px 2px rgba(0,0,0,.14)}}
#root{{position:relative;height:{card_h}px}}
</style><script>
/* Stand-in for Home Assistant's <ha-icon>: enough of it to draw. */
customElements.define("ha-icon", class extends HTMLElement {{
  connectedCallback() {{
    const icons = {{"mdi:home-roof": "{roof}"}};
    const d = icons[this.getAttribute("icon")];
    if (!d) return;
    this.style.display = "inline-block";
    this.innerHTML =
      '<svg viewBox="0 0 24 24" style="width:100%;height:100%">' +
      '<path fill="currentColor" d="' + d + '"/></svg>';
  }}
}});
</script></head>
<body><div id="hacard"><div id="root">{body}</div></div></body></html>
"""


def render_html(states: dict[str, str] | None = None) -> str:
    """Render the widget template with the given entity states."""
    table = STATES if states is None else states
    missing: set[str] = set()

    def states_fn(entity_id):
        if entity_id not in table:
            missing.add(entity_id)
            return "unknown"
        return table[entity_id]

    def is_state(entity_id, value):
        return states_fn(entity_id) == value

    env = Environment()
    env.globals.update(states=states_fn, is_state=is_state)
    out = env.from_string(open(TEMPLATE).read()).render()
    if missing:
        print("WARNING: unstubbed entities: %s" % sorted(missing), file=sys.stderr)
    return out


def render_page(states: dict[str, str] | None = None, card_w: int = CARD_W) -> str:
    """Render the template inside the page scaffold the card builds."""
    return PAGE.format(
        card_w=card_w,
        card_h=CARD_H,
        roof=MDI_HOME_ROOF,
        body=render_html(states),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", required=True, help="HTML file to write")
    ap.add_argument(
        "--state",
        action="append",
        default=[],
        metavar="ENTITY=VALUE",
        help="override one entity state; repeatable",
    )
    ap.add_argument(
        "--card-width",
        type=int,
        default=CARD_W,
        help="card width in px (default %d, as measured live)" % CARD_W,
    )
    args = ap.parse_args()

    states = dict(STATES)
    for item in args.state:
        entity, sep, value = item.partition("=")
        if not sep:
            raise SystemExit("--state wants ENTITY=VALUE, got %r" % item)
        if entity not in states:
            # Not fatal: a new template may legitimately read a new entity.
            print("note: %s is not in the demo table" % entity, file=sys.stderr)
        states[entity] = value

    page = render_page(states, args.card_width)
    with open(args.out, "w") as fh:
        fh.write(page)
    print("wrote %s (%d bytes)" % (args.out, len(page)))


if __name__ == "__main__":
    main()
