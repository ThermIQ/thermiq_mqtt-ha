# CLAUDE.md

Working notes for this repository. These are the conventions that are **not**
visible in the code — the code itself is heavily commented, and where it is,
trust it over this file.

This is a maintained fork of [ThermIQ/thermiq_mqtt-ha](https://github.com/ThermIQ/thermiq_mqtt-ha).
Fixes are developed here, released here, and offered upstream as separate PRs.

## Releases

**Cut every release as a pre-release first.** `manifest.json` carries the
matching `-beta.N`; hassfest accepts that version format.

```bash
gh release create v3.5.11-beta.1 -R larsablixth/thermiq_mqtt-ha \
  --target master --prerelease --title "..." --notes "..."
```

`--target` takes a **branch name**. A commit SHA is rejected with
`Release.target_commitish is invalid`.

HACS's `releases/latest` skips pre-releases, so a beta reaches only people who
enable *Show beta versions* — in practice, @mahagr — while everyone else stays
on the last stable. Promote only after he has confirmed it on live hardware:
manifest to the plain version, PR, merge, then tag again without `--prerelease`.

**Batch changes into one beta round.** Not a beta per merged PR. Eleven betas in
two days (3.5.11) was the same flood the pre-release channel exists to prevent,
just moved somewhere quieter. Agreed on #78.

**Delete superseded pre-releases and their tags.** GitHub sorts them as strings,
so `beta.10` and `beta.11` rank above `beta.2` and "newest" is not where anyone
looks. Keep one live beta at a time, and drop the last one once the stable
release is out.

## Whether a release needs a hard refresh depends on which file changed

Say which one it is **in every release note** — that is what tells a tester
whether a problem they still see is real or a stale cache.

| changed | hard refresh | `CARD_VERSION` |
|---|---|---|
| `frontend/heatpump_widget.j2` only | **no** | do **not** bump |
| `frontend/thermiq-widget-card.js` | **yes** | **must** bump |

The card fetches the template with `cache: "no-store"`, so a new drawing arrives
on the next page load. The card module itself is cached by the browser behind
`?v=<CARD_VERSION>` in `__init__.py`, so without a bump the change never arrives
at all.

## The widget

**Nothing is drawn that was not either measured or declared.** No inferred
temperatures, no assumed flow. If the pump cannot see it, it comes from an
opt-in helper entity the user defines (`binary_sensor.pool_heating_active` is
the pattern) or it is not drawn — a pipe with no sensor behind it is grey and
carries no number.

This is a rule with scar tissue behind it. Drawing a plausible picture of a
system somebody does not have is worse than drawing less: see #74, a buffer tank
designed, shipped and reverted in six hours because it put a real vessel in the
wrong place.

**One condition, one job.** Two bugs in 3.5.11 (#53, #63) were a single flag
meaning both "water is moving" and "the house is being heated". When a new state
appears, check whether an existing condition is quietly answering two questions.

**Every element is absolutely positioned**, so nothing reflows and two badges
can overlap silently. Arithmetic is the only thing keeping them apart; squinting
at screenshots does not find collisions, measuring does — render the template
with `tools/render_widget_html.py` and read `getBoundingClientRect()` in a
headless browser, per scenario.

**The drawing needs 357px of card inner width.** `_fit()` centres it but never
scales, taking an early `return` when there is no room — so on a 375pt iPhone
(327px) and a 393pt one (345px) it sits left-aligned with dead space. Cosmetic
today; anything that widens the drawing makes it structural.

## Two files have a downstream consumer

`heatpump_widget.j2` and `heatpump/thermiq_regs.py` are vendored by
[thermiq-bridge](https://github.com/larsablixth/thermiq-bridge), which compiles
the template to C and tests both renderers byte for byte. See CONTRIBUTING.md.

Practically: **the template must stay inside the Jinja subset that compiler
implements.** Clamp with the idiom already in the file —
`([lo, value, hi]|sort)[1]` — rather than reaching for `min`/`max`. A new
entity referenced from the template is fine; the add-on has no such entity and
falls back.

## Tests and CI

```bash
python3 -m pytest tests -v     # 134 tests
python3 -m mypy                # config in mypy.ini
black --check .
```

CI runs all three on pushes to `master`/`dev` **and on pull requests**. The PR
trigger was off until 2026-08-12, which is how a test suite sat green-looking
and unexecuted for months — do not remove it.

`requirements_test.txt` is the single source of truth for the `black` pin; the
workflow greps the version out of it rather than pinning separately.

`tests/CORNER_CASES.md` is the catalogue of what an incoming `/data` payload can
carry, backed by mocked messages. Every expectation there was read off the
running code, so it records *current* behaviour, not necessarily *correct*
behaviour — it ends with open questions only the hardware vendor can answer.

## The people

**@mahagr** is the only person testing on real hardware, and has no separate test
instance — a bad general release breaks his heating. His installation: radiators
plus floor heating, buffer tank, shunt group on Curve 2, HGW fitted, custom
entity prefix. He reports precisely and pushes back when the picture is wrong;
take the pushback literally, and read his description twice before drawing
anything from it.

**@ThermIQ** (Anders) maintains upstream. He merges by hand rather than through
the PR UI, so changes have arrived subtly altered — a `@property` lost, a file
saved with CR-only line endings. After an upstream merge, diff the result
against the branch rather than assuming it landed intact.

**Discuss before building anything large.** A feature request with a round of
comments costs one comment; #74 cost two releases and a revert. This was
@mahagr's ask on #78 and it was a fair one.

## Small facts that have caused wasted time

- `README.md` is **LF**. An older note in the issue tracker claiming CRLF is
  wrong; `.gitattributes` sets `* text=auto eol=lf`.
- There is no committed rendering of the widget to check work against, on
  purpose. `docs/heatpump_widget.png` is a real screenshot and will age; the
  static SVG that used to sit beside it drifted five releases before anyone
  noticed. To see what the template *currently* draws, render it:
  `python3 tools/render_widget_html.py -o /tmp/w.html`, with `--state` to pick
  the scenario.
- `entity_prefix` on the card works by string-replacing `thermiq_mqtt_vp1`
  throughout the template. Helper entities named without that prefix — such as
  `binary_sensor.pool_heating_active` — are therefore shared by every widget on
  the dashboard.
- Registers seed as `None`, not `-1`. Guards in `message_received` depend on
  that; `-1` used to light up every alarm bitmask at startup.
