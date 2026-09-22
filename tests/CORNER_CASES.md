# MQTT corner cases

A catalogue of `/data` payloads worth testing, written for @ThermIQ after
[issue #28](https://github.com/larsablixth/thermiq_mqtt-ha/issues/28).

Everything in the **Covered** sections is asserted by a test today; the
expectations were read off the running code, not assumed. The **Open
questions** at the end are payloads that cannot become assertions until
someone who knows the hardware says what the right answer is.

Tests live in `tests/test_message_corner_cases.py` (the ingest path) and
`tests/test_heatpump.py` (EVU and the write path). Run them with
`pytest tests/ -q`.

---

## 1. The envelope

Everything is gated on `Client_Name` starting with `ThermIQ_`. A broker
carries other traffic, so a payload that is not ours must leave the state
untouched rather than half-applied.

| payload | result |
|---|---|
| `{"Client_Name":"ThermIQ_x","r00":7}` | accepted |
| `{"Client_Name":"ThermIQ_"}` | accepted — the bare prefix passes |
| `{"Client_Name":"ThermIQ_kitchen_pump_2"}` | accepted — any suffix |
| `{"Client_Name":"ThermIQ"}` | rejected — one character short |
| `{"Client_Name":"thermiq_x"}` | rejected — the check is case-sensitive |
| `{"Client_Name":12345678}` | rejected — stringified, then fails the prefix |
| `{"r00":7}` | rejected — no `Client_Name` |

A rejected message must not increment `mqtt_counter` and must not store a
register. Both are asserted.

**Payloads that are not JSON objects** must be ignored without raising — an
exception here kills the MQTT callback for every later message:

`{not json` · `` (empty) · `   ` (whitespace) · `[1,2,3]` · `"hello"` ·
`null` · `42`

---

## 2. Register key formats

The same register can arrive three ways: hex, decimal, or by name. Keys are
lowercased on the way in, so case is not a distinguishing feature.

| key | stored as | note |
|---|---|---|
| `r00` | `r00` | hex, the canonical form |
| `r0b` | `r0b` | hex with a letter |
| `R00` | `r00` | uppercase works |
| `d0` | `r00` | decimal, one digit |
| `d50` | `r32` | decimal, two digits |
| `d050` | `r32` | decimal, three digits |
| `EVU` / `evu` | `evu` | by name |
| `d300` | **`d300`** | *not* EVU — see below |
| `r99` | `r99` | unknown register, stored but inert |
| `dXX` | *skipped* | logged, and the rest of the message still lands |

### Why `d300` is not EVU

`int("300")` formats to hex `12c`, so the candidate key is `r12c` — four
characters where a register key is three. The code then falls back to the key
as sent. So `d300` never reaches `evu`, and the reason is arithmetic rather
than intent. The ingest path does compute `d300` as EVU's decimal alias, but
only ever uses it in the debug log.

**This is question 4 below.**

---

## 3. Value types

JSON carries more than integers, and nothing is coerced on the way in —
consumers apply `int()` / `float()` themselves.

| value | stored | reaches the entity as |
|---|---|---|
| `7` | `7` | 7 |
| `-8` | `-8` | −8 |
| `7.5` | `7.5` | 7.5 |
| `0` | `0` | 0 — a value, not an absence |
| `null` | `None` | `unknown` |
| `true` | `True` | 1 via `int()` |
| `"7"` | `"7"` | 7 via `int()`, but the raw type is a string |

---

## 4. The split decimals

`r01`/`r02` and `r03`/`r04` are whole degrees and tenths. Combining twice
would compound the fraction, so it happens only when the whole part arrived in
the **same** message.

| sequence | result |
|---|---|
| `{"r01":21,"r02":4}` | `r01 = 21.4` |
| `{"r01":21}` | `r01 = 21` |
| `{"r01":21,"r02":4}` then `{"r02":9}` | `r01` stays `21.4`, **not** 22.3 |

---

## 5. The integration's own bookkeeping

| payload | effect |
|---|---|
| `{"time":"..."}` | sets `time_str` |
| `{"Time":"..."}` | also sets `time_str` |
| both present | lowercase `time` wins |
| `{"vp_read":"MISMATCH"}` | `communication_status = MISMATCH` |
| no `vp_read` | `communication_status = Ok` |
| MISMATCH, then a clean message | back to `Ok` |
| `{"app_info":"ThermIQ-room2 2.68"}` | recorded |

`mqtt_counter` advances once per **accepted** message and not at all for
rejected ones.

---

## 6. Capability detection

What the pump sends is what the pump can do — no model list, no lookup table.
The set of echoed keys only ever grows.

| case | expectation |
|---|---|
| plain ThermIQ-MQTT `/data` | `evu` and `indr_t` unsupported |
| Room2 echoing `EVU` and `INDR_T` | both supported |
| `EVU: 0` | supported — **0 is a value, not an absence** |
| a later message omitting `EVU` | still supported |
| a MISMATCH round dropping keys | still supported |
| a rejected (foreign) message carrying `EVU` | grants nothing |
| before the first message | nothing supported |

The `EVU: 0` case is the one that matters most: capability keys off whether
the pump ever *mentioned* EVU, so a falsy value must not read as "this pump
cannot do EVU" — that would hide the control exactly when the block is
released.

---

## 7. The write path

| register | value | published |
|---|---|---|
| `heatpump_evu_block` | `1` | `{"EVU": 1}` to the **set** topic |
| `heatpump_evu_block` | `0` | `{"EVU": 0}` to the **set** topic |
| `heatpump_evu_block` | `2`, `-1` | refused |
| `indoor_requested_t` | `21` | `{"d050": 21}` to the **write** topic |
| `indoor_requested_t` | `95` | refused — outside 0..50 |
| `indoor_requested_t` | `"high"` | refused — not numeric |
| `integral1_curve_p5` | `-3` | `{"d055": 65533}` — 16-bit two's complement |
| `integral1_curve_p5` | `-6` | refused — outside −5..5 |
| read-only register | anything | refused |
| any register, before the first message | refused — nothing known yet |

Range validation runs on the **raw** value, before the bitmask conversion.
Checking after masking would push every legitimate negative far outside its
register bounds.

---

## Open questions — these need an answer before they can be tests

**1. Does the interface ever emit a negative register as raw 16-bit?**
The write path sends −3 as `65533`. The read path does no such conversion, so
a payload of `{"r37": 65533}` would surface as 65533 rather than −3. Live data
suggests the interface already decodes signs on the way out (`outdoor_t` arrives
as `-3`, `msd1_dts` as `-3071`), which would make this a non-issue — but that
is an inference from one pump, not a specification. If any firmware or any
register emits the raw 16-bit form, the read path needs the mirror of the
write path's conversion.

**2. What is the full set of `vp_read` values?**
`MISMATCH` is the one seen. If there are others — timeouts, checksum errors,
partial reads — they are worth surfacing distinctly rather than collapsing
everything that is not absent into one string.

**3. Does any firmware send register values as JSON strings?**
`{"r00": "7"}` is stored verbatim as `"7"`. Consumers apply `int()`, so it
works, but the raw type reaching the state differs. If this never happens on
the wire the test is documenting an impossibility, which is fine; if it does
happen, coercing at ingest would be tidier than at every reader.

**4. Is `d300` meant to be EVU's decimal alias?**
It reads like one in the ingest path but is unreachable as described above. If
a device does publish `d300` expecting it to mean EVU, that is a live bug and
the fix is a special case beside the existing `EVU` one. If nothing publishes
it, the dead alias is worth deleting so it stops implying a mapping.

**5. Are there registers that arrive only intermittently?**
Capability detection is deliberately sticky to survive this, but a concrete
example would let the test name the real register rather than a hypothetical.

**6. Does a Room2 always echo `INDR_T`, or only with a room sensor paired?**
If unpaired units stay silent on it, then absence means "no sensor" rather
than "no capability", and the room-sensor number should perhaps be offered
anyway.

**7. Can a payload nest objects or arrays?**
Everything here assumes a flat map of scalars. A nested value would be stored
as a `dict` or `list` and reach `int()` at the entity, which would log and
show `unknown` — survivable, but untested because it is not known to occur.

**8. Are register writes applied per-packet, or should they be batched?**
Asked by @mahagr: if several `/write` packets arrive in a row, does the
interface apply all of them, or should the integration coalesce a set of
values into one request? Today every `number`/`switch` change publishes its
own message, so a user dragging three sliders sends three packets. If the
interface prefers one, the write path wants a small queue. Related: can `EVU`
and `INDR_T` be written freely and independently, as separate control wires?
