# Install ThermIQ with an AI agent

You should not have to read an install guide to get a heat pump onto a dashboard.
Hand this file to an AI agent instead — it does the reading, you answer at most three
questions.

Works with any agent that can run shell commands and reach your Home Assistant:
Claude Code, Codex CLI, Gemini CLI, Copilot agent mode, or a chat assistant that can
call tools.

---

## The 30-second version

1. In Home Assistant: **your profile → Security → Long-lived access tokens → Create token**. Copy it.
2. In your terminal, put the token in the environment so it never has to be typed into a chat window:

   ```bash
   export HA_URL=http://homeassistant.local:8123
   export HA_TOKEN=paste_the_token_here
   ```

3. Start your agent in that same terminal and paste:

   > Install the ThermIQ MQTT Home Assistant integration for me.
   > Follow this runbook exactly: <https://raw.githubusercontent.com/larsablixth/thermiq_mqtt-ha/master/AI_INSTALL.md>
   > My Home Assistant URL and token are in the `HA_URL` and `HA_TOKEN` environment variables — use them, don't print them.

That is the whole thing. The agent will find your heat pump on MQTT by itself, install
the integration, restart Home Assistant, create the configuration entry, check that real
values are arriving, and offer to add the dashboard card.

Prefer to do it by hand? The manual steps are in the [README](README.md#steps-to-install-thermiq-ha-integration) and still work.

---

## What access the agent needs

| # | Access | Required? | What it is used for | How to grant it |
|---|--------|-----------|---------------------|-----------------|
| 1 | **Home Assistant long-lived access token**, from an **admin** account | Yes | Reading the HA version and loaded integrations, listening on MQTT to find your heat pump, creating the config entry, reading entity states, restarting HA | Profile → Security → Long-lived access tokens |
| 2 | **Network reach to Home Assistant** (`http(s)://host:8123`) | Yes | Everything above | Same LAN, VPN, or an externally reachable URL |
| 3 | **Outbound access to `github.com`** | Yes | Downloading the integration release | Normal internet access |
| 4 | **File access to the HA configuration directory** | Only for a fully hands-off install | Copying `custom_components/thermiq_mqtt/` into place and taking a database backup | Advanced SSH & Web Terminal add-on, Samba share, `docker exec` on the HA container, or the agent running on the HA host itself |
| 5 | **Shell on the machine the agent runs on** | Yes | `curl`, `tar`, and (optionally) `ssh` | It already has this if it can run commands |

**Without #4** the install still works: the agent does everything except the file copy, and
asks you to click one HACS button. That is the only manual action.

### What the agent does *not* need

- **Your MQTT broker username or password.** It listens through Home Assistant's own
  MQTT connection, which is already authenticated.
- **Your Home Assistant password**, or access to your ThermIQ / Thermia account.
- **Write access to the heat pump.** Everything in the runbook is read-only towards the
  pump. There is one optional write test at the very end, and it writes back the value
  the pump already reports, so nothing changes. It only runs if you say yes.
- **Access to any other machine on your network.**

### The token is a skeleton key — treat it like one

Home Assistant tokens cannot be scoped: token #1 can do anything your admin account can
do, including calling any service on any device. So:

- Create a **separate admin user** (Settings → People → Add person → Allow login, Advanced
  mode/admin) named e.g. `ai-installer`, generate the token from *that* account, and delete
  the user when the install is done. Deleting the user kills the token.
- Or, if you use your own account: revoke the token afterwards on the same profile page.
- Keep it in an environment variable, not in the chat and not in a file. If the agent
  writes it into a script, tell it to stop.
- The install touches your `custom_components` folder and your recorder database. **Take a
  Home Assistant backup first** — the runbook makes the agent do this, but it is your
  safety net, so check that it happened.

### What to allow in your AI tool

The agent needs permission to run `curl` (and `ssh`/`scp` or `docker` if your HA config
directory is on another machine), to read this file from the web, and to write files under
your Home Assistant configuration directory. Nothing else. If your tool asks per command,
approving `curl` calls to your own HA URL and `tar`/`cp` under the config directory is
enough.

---

## The contract

The runbook below binds the agent to these rules. Hold it to them.

**It will:**

- show you the plan and the values it detected before changing anything
- take a backup before touching the recorder database
- ask before restarting Home Assistant
- ask before writing to any dashboard
- tell you exactly what it changed and how to undo it

**It will never:**

- write registers to your heat pump without asking
- turn on the recorder-history migration on a fresh install (it rewrites history and
  cannot be undone)
- print, log, or save your token
- edit your automations, scripts, or existing dashboard cards
- pretend a step worked — every step is verified against Home Assistant, and it stops and
  reports rather than guessing

---
---

# Agent runbook

**Everything below this line is addressed to the AI agent.** Follow it in order. Do not
skip verification steps. If a step fails, stop and report — do not improvise around a
failure.

## 0. Ground rules

1. **Never echo the token.** Use `"$HA_TOKEN"` inside commands. Never `echo` it, never
   write it to a file, never include it in your summary.
2. **Verify, never assume.** Every state change is followed by a read that proves it
   happened. "The command returned 200" is not proof that the integration loaded.
3. **Ask before:** restarting Home Assistant, writing to a dashboard, enabling
   `migrate_data`, or publishing anything to the heat pump.
4. **One question at a time, in plain language.** The user chose this route to avoid
   reading documentation. Do not paste this runbook back at them.
5. **Stop conditions.** Stop and report if: Home Assistant is unreachable, the token is
   not admin, the MQTT integration is missing, no ThermIQ data is seen on MQTT, or the
   integration fails to load after a restart.

Set up a reusable shorthand at the start:

```bash
ha() { curl -sS -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" "$@"; }
```

## 1. Establish access

```bash
ha "$HA_URL/api/" ; echo
ha "$HA_URL/api/config" | python3 -m json.tool
```

`/api/` must return `{"message": "API running."}`. From `/api/config` record:

- `version` — Home Assistant version. This integration requires **2024.7.0 or newer**
  (see `hacs.json`).
- `config_dir` — the absolute path of the configuration directory *as Home Assistant sees
  it*. On a container install this is usually `/config`, which may be a different path on
  the host.
- `components` — the loaded integrations. You will check this list repeatedly.
- `state` — must be `RUNNING`.

Confirm the token is admin by hitting an admin-only endpoint:

```bash
ha "$HA_URL/api/config/config_entries/entry" | head -c 200; echo
```

A `401`/`403` means the token is not from an admin account — stop and ask for one.

**Decide your tier now** and tell the user which one you are in:

- **Tier 2 (hands-off)** — you can read and write files under `config_dir`, directly or
  over `ssh`/`docker exec`. Verify it for real: `ls "$CONFIG_DIR/configuration.yaml"`.
- **Tier 1 (one click)** — API access only. The user will click one HACS button.

## 2. Preflight

From the `components` list of `/api/config`:

| Check | Meaning | Action if missing |
|-------|---------|-------------------|
| `mqtt` in components | The MQTT integration is set up | **Stop.** The heat pump talks MQTT only. Point the user at README steps 1–5 (Mosquitto add-on + MQTT integration) and stop. |
| `hacs` in components | HACS is available | Not fatal. Determines the install path in step 5. |
| `thermiq_mqtt` in components | This integration is already installed | Switch to **Upgrading an existing install** below. |
| `recorder` in components | History is being recorded | Not fatal, but if present a backup matters more. |

Also list existing entries so you do not create a duplicate:

```bash
ha "$HA_URL/api/config/config_entries/entry?domain=thermiq_mqtt" | python3 -m json.tool
```

Tier 2 — also record, from the config directory:

- whether `custom_components/thermiq_mqtt/` already exists, and its
  `manifest.json` → `version`
- the recorder database: default `home-assistant_v2.db` in the config directory, unless
  `configuration.yaml` sets `recorder:` → `db_url:` (MariaDB/PostgreSQL). Check with
  `grep -A5 '^recorder:' "$CONFIG_DIR/configuration.yaml"`.

## 3. Find the heat pump on MQTT

Do not ask the user for the MQTT node name. Find it.

The ThermIQ device publishes a JSON payload to `<node>/data` roughly every 30 seconds.
The default node is `ThermIQ/ThermIQ-mqtt`, but people change it during wifi setup, and a
wrong value here is the single most common reason the integration ends up with no data.

Subscribe to everything for 45 seconds through Home Assistant's own MQTT connection —
this needs no broker credentials. Use the first of these that is available:

**a. `websocat`**

```bash
printf '%s\n' \
  "{\"type\":\"auth\",\"access_token\":\"$HA_TOKEN\"}" \
  '{"id":1,"type":"mqtt/subscribe","topic":"#"}' \
  | timeout 45 websocat -n "${HA_URL/http/ws}/api/websocket"
```

**b. Python with `websockets` or `websocket-client`, if importable**

```bash
python3 - <<'PY'
import asyncio, json, os, websockets
async def main():
    url = os.environ["HA_URL"].replace("http", "ws", 1) + "/api/websocket"
    async with websockets.connect(url, max_size=None) as ws:
        await ws.recv()                                    # auth_required
        await ws.send(json.dumps({"type": "auth", "access_token": os.environ["HA_TOKEN"]}))
        await ws.recv()                                    # auth_ok
        await ws.send(json.dumps({"id": 1, "type": "mqtt/subscribe", "topic": "#"}))
        seen = {}
        try:
            async with asyncio.timeout(45):
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "event":
                        e = msg["event"]
                        seen[e["topic"]] = e["payload"][:200]
        except TimeoutError:
            pass
        for topic, payload in sorted(seen.items()):
            print(topic, "=>", payload)
asyncio.run(main())
PY
```

**c. `mosquitto_sub`** — only if the user volunteers broker credentials:
`mosquitto_sub -h <broker> -u <user> -P <pass> -t '#' -v -W 45`

**d. Ask the user** (always works, ~15 seconds of their time): *Settings → Devices &
Services → MQTT → Configure → Listen to a topic*, enter `#`, press Start listening, wait
for a message, paste one line back.

### Reading the result

Pick the topic that **ends in `/data`** and whose payload is a JSON object of register
keys. Strip the trailing `/data` — what remains is the **mqtt_node** value.

```
ThermIQ/ThermIQ-mqtt/data => {"d000":-2,"d001":21.4,"d005":34, ... ,"time":"...","vp_read":"Ok"}
                ^^^^^^^^^^ node = ThermIQ/ThermIQ-mqtt
```

The register key style also tells you the firmware convention, which answers the
`hexformat` field:

| Payload keys look like | Firmware | Set `hexformat` to |
|------------------------|----------|--------------------|
| `d000`, `d001`, `d010` (decimal) | current | `false` |
| `r00`, `r01`, `r0a` (hex) | old 1.xx ThermIQ-MQTT | `true` |

The integration reads both formats regardless of the setting — `hexformat` only controls
the key format it uses when *writing* a register, which is why it has to match the
firmware. Treat the payload style as a strong signal, and confirm it with the optional
write test in step 10 if the user cares about the control side.

If nothing matching arrives in 45 seconds, **stop**: the heat pump is not reaching the
broker, and no amount of Home Assistant configuration will fix that. Send the user to
[MQTT Explorer](https://mqtt-explorer.com/) and README steps 3–4.

Report what you found, e.g. *"Found your heat pump publishing to `ThermIQ/ThermIQ-mqtt/data`,
decimal register format, last message 3 seconds ago."*

## 4. Back up first

The integration runs a recorder-history migration the first time a config entry is set up
(it looks for entities from older ThermIQ versions whose units or entity ids changed).
On a genuinely fresh Home Assistant it finds nothing and is effectively a no-op, but it
does read and potentially rewrite recorder tables, so a backup is not optional.

Try these in order and tell the user which one you used:

1. **Home Assistant OS / Supervised**, Tier 2: `ha backups new --name thermiq-preinstall`
2. **A `backup.create` service**, if `ha "$HA_URL/api/services"` lists a `backup` domain
   with a `create` service:
   `ha -X POST "$HA_URL/api/services/backup/create" -d '{}'`
3. **Tier 2, SQLite recorder** — a hot copy that is safe while HA is running:
   `sqlite3 "$CONFIG_DIR/home-assistant_v2.db" ".backup '$CONFIG_DIR/thermiq-preinstall.db'"`
   Without `sqlite3`, stop Home Assistant first, then copy
   `home-assistant_v2.db`, `home-assistant_v2.db-wal` and `home-assistant_v2.db-shm`.
4. **MariaDB / PostgreSQL recorder** — you cannot back this up from here. Tell the user to
   run their own dump (`mysqldump` / `pg_dump`) and wait for confirmation.
5. **Tier 1 with none of the above** — ask the user to create a backup in
   Settings → System → Backups and confirm when it is done.

Never skip this because it is inconvenient. If all five fail, ask the user for an explicit
"go ahead without a backup" before continuing.

## 5. Install the integration

### Tier 2 — copy the files (no HACS needed, fully automatic)

The integration is a plain custom component with no Python dependencies, so copying the
folder is a complete install.

```bash
TAG=$(curl -sS https://api.github.com/repos/larsablixth/thermiq_mqtt-ha/releases/latest \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
cd "$(mktemp -d)"
curl -sSL "https://github.com/larsablixth/thermiq_mqtt-ha/archive/refs/tags/$TAG.tar.gz" | tar xz
ls "thermiq_mqtt-ha-${TAG#v}/custom_components/thermiq_mqtt/manifest.json"
```

Then, into the config directory:

```bash
mkdir -p "$CONFIG_DIR/custom_components"
cp -r "thermiq_mqtt-ha-${TAG#v}/custom_components/thermiq_mqtt" "$CONFIG_DIR/custom_components/"
```

Rules:

- If `custom_components/thermiq_mqtt` already exists, move the old copy **outside**
  `custom_components/` first — e.g. to `$CONFIG_DIR/thermiq_backup_<tag>/`. A leftover
  `thermiq_mqtt.bak/` folder *inside* `custom_components/` makes Home Assistant complain
  that the folder name does not match the manifest domain.
- The final layout must be `<config>/custom_components/thermiq_mqtt/manifest.json` — one
  `thermiq_mqtt` level, not two.
- If the config directory is on another host, `scp -r` or `docker cp` it, then verify with
  a remote `ls` — do not assume the transfer landed.
- Files must be readable by the user Home Assistant runs as.

Mention to the user that a file install is not tracked by HACS, so they will not get
update notifications; if they have HACS, adding the repository as a custom repository
afterwards fixes that without reinstalling.

### Tier 1 — HACS (one click from the user)

1. Tell the user to open this link and press **Download**:
   <https://my.home-assistant.io/redirect/hacs_repository/?owner=larsablixth&repository=thermiq_mqtt-ha&category=integration>
2. If HACS reports that the repository is unknown, they need to add it first:
   HACS → ⋮ (top right) → *Custom repositories* → URL
   `https://github.com/larsablixth/thermiq_mqtt-ha`, category *Integration* → **Add**.
   This fork is not in the HACS default list; without this step HACS installs the upstream
   version instead.
3. Wait for them to confirm, then continue.

Do not guess at HACS's websocket commands to automate this — they have changed between
HACS versions, and a silently wrong call looks like success.

## 6. Restart and confirm the code loaded

Ask first: a restart takes Home Assistant down for roughly a minute, and automations do
not run while it is down.

```bash
ha -X POST "$HA_URL/api/services/homeassistant/restart" -d '{}'
```

Then poll until `/api/config` answers again and check:

```bash
ha "$HA_URL/api/config" | python3 -c 'import json,sys; c=json.load(sys.stdin); print(c["state"], "thermiq_mqtt" in c["components"])'
```

At this point `thermiq_mqtt` is **not** expected in `components` yet — the integration
only loads once a config entry exists. What you are confirming is that Home Assistant came
back up cleanly. Check the log for import errors:

```bash
ha "$HA_URL/api/error_log" | grep -i thermiq | tail -20
```

A `Unable to find integration` or a traceback here means the file copy went to the wrong
place. Fix that before continuing.

## 7. Create the config entry

Start the flow:

```bash
ha -X POST "$HA_URL/api/config/config_entries/flow" \
   -d '{"handler":"thermiq_mqtt","show_advanced_options":false}'
```

The response contains a `flow_id`. Submit the answers to it:

```bash
ha -X POST "$HA_URL/api/config/config_entries/flow/<flow_id>" -d @payload.json
```

<!-- ai-install:config-flow-payload -->
```json
{
  "id_name": "vp1",
  "mqtt_node": "ThermIQ/ThermIQ-mqtt",
  "language": "en",
  "hexformat": false,
  "thermiq_dbg": false,
  "migrate_data": false
}
```

Fill it in like this:

| Field | Where the value comes from | Notes |
|-------|---------------------------|-------|
| `id_name` | Keep `vp1` unless the user has more than one heat pump | Goes verbatim into every entity id (`sensor.thermiq_mqtt_vp1_outdoor_t`). Lowercase letters, digits and underscores only. Renaming it later renames every entity, so confirm it with the user *now* rather than after the dashboard exists. |
| `mqtt_node` | Detected in step 3 | No trailing `/`; the flow strips one if present. |
| `language` | Ask, or infer from `/api/config` → `language`/`country` and confirm | Only affects friendly names — entity ids stay English. One of `en`, `se`, `fi`, `no`, `de`. |
| `hexformat` | Inferred in step 3 from the payload key style | |
| `thermiq_dbg` | `false` | `true` diverts all writes to `<node>/dbg_write` and `<node>/dbg_set` so the pump is never written to. Offer it only if the user explicitly wants a dry run. |
| `migrate_data` | `false` on a fresh install — always | Only for upgrades from pre-3.3.0. See the upgrade section. |

A successful response is `{"type": "create_entry", ...}` with the entry in `result`.
Anything else is a form with an `errors` object:

| Error | Meaning | Fix |
|-------|---------|-----|
| `creation_id` | `id_name` is not slug-safe | Lowercase letters, digits, underscores only |
| `invalid_nodename` | `mqtt_node` is not a valid MQTT topic prefix | Re-check step 3; no `#` or `+` |
| `invalid_language` | Not one of the five supported codes | Use `en` |
| abort `already_configured` | An entry with this `id_name` exists | You skipped step 2 — go look at the existing entry |

## 8. Verify it actually works

Not "the entry was created" — **real values from the real heat pump**.

```bash
ha "$HA_URL/api/states" | python3 -c '
import json, sys
states = [s for s in json.load(sys.stdin) if ".thermiq_mqtt_" in s["entity_id"]]
print(len(states), "ThermIQ entities")
for s in states[:15]:
    print(" ", s["entity_id"], "=", s["state"])
'
```

Expect on the order of a hundred entities across `sensor`, `binary_sensor`, `number`,
`select` and `switch`, all named `<domain>.thermiq_mqtt_<id_name>_<register>`.

Then check a specific one that must have a plausible value:

```bash
ha "$HA_URL/api/states/sensor.thermiq_mqtt_vp1_outdoor_t" | python3 -m json.tool
```

- `unavailable` — no MQTT message has arrived. The entities go unavailable when data stops
  flowing. Wait one minute (messages come every ~30 s); if it persists, `mqtt_node` is
  wrong. Fix it through the integration's options rather than deleting the entry.
- `unknown` — the entry loaded but this register was not in the payload.
- A number — done. Say so, with the value: *"Outdoor temperature reads -2.0 °C, updated 12
  seconds ago."*

Also confirm `thermiq_mqtt` now appears in `/api/config` → `components`, and that
`/api/error_log` has no new ThermIQ errors.

## 9. The dashboard card

Ask whether they want the card. If yes:

**Dependency:** the card uses `custom:fold-entity-row` for its collapsible sections. The
animated widget itself (`custom:thermiq-widget-card`) ships inside the integration and is
already served — nothing to install and no dashboard resource to register for it.

- HACS present → have the user install
  [fold-entity-row](https://github.com/thomasloven/lovelace-fold-entity-row) from
  HACS → Frontend.
- No HACS, Tier 2 → download `fold-entity-row.js` from that repository's latest release
  into `<config>/www/`, then register it as a dashboard resource over the websocket API
  (`{"type":"lovelace/resources/create","res_type":"module","url":"/local/fold-entity-row.js"}`).
  This only works on storage-mode dashboards; in YAML mode, tell the user to add it under
  `lovelace: resources:` themselves. Verify with `{"type":"lovelace/resources"}` and do not
  create a second copy if one is already registered.

**The card itself:** take `ThermIQ_Card.yaml` from the release you installed and replace
every `vp1` with the chosen `id_name`. The safe default is to print the adjusted YAML and
have the user paste it into a manual card — two clicks, zero risk.

Only if the user asks you to add it automatically:

1. Read the dashboard config over the websocket API (`{"type":"lovelace/config","url_path":null}`
   for the default dashboard).
2. **Save that JSON to a file first** and tell the user the path — this is the undo.
3. Append the converted card to a view and write it back with
   `{"type":"lovelace/config/save","url_path":null,"config":{...}}`.
4. Read the config back and confirm the card is there.

If any of those commands errors, stop automating and fall back to printing the YAML. Never
overwrite a dashboard config you have not first saved to disk. Never modify cards the user
already had.

The Energy management section of the card references helper entities
(`input_number.vp1_electricity_price_threshold` and friends) that the user creates
themselves — those rows will show as unavailable until they follow the *ThermIQ Energy
Control* section of the README. Say so, so it does not look like a broken install.

## 10. Optional write test (ask first)

Only if the user wants the control side proven, and only with explicit consent.

Read the current value of a harmless setpoint, then write **the same value** back:

```bash
ha "$HA_URL/api/states/number.thermiq_mqtt_vp1_indoor_requested_t"
ha -X POST "$HA_URL/api/services/number/set_value" \
   -d '{"entity_id":"number.thermiq_mqtt_vp1_indoor_requested_t","value":<the value you just read>}'
```

Nothing about the heat pump's behaviour changes, but the round trip proves the write topic
and the `hexformat` setting are correct: within a minute the pump echoes the register back
in its next `/data` message and the entity stays at that value. If the entity snaps back to
a different value or the log shows the write being rejected, `hexformat` is probably
inverted — change it in the integration's options and retest.

Never do this with a register that affects operation (compressor, EVU block, hot water) as
a test.

## 11. Report

Finish with a short summary the user can act on:

- the detected MQTT node and register format
- where the files were installed, and where the backup is
- the `id_name`, and the entity-id prefix that follows from it
- how many entities exist and one live reading with its value
- whether the card was added, and what is still manual (fold-entity-row, energy helpers)
- **how to undo everything** (see below)
- a reminder to revoke the token or delete the `ai-installer` user

No token. No wall of text.

---

## Upgrading an existing install

Same runbook, with these changes:

- **Read `custom_components/thermiq_mqtt/manifest.json` → `version` first** and tell the
  user what they are moving from and to.
- **The backup in step 4 is mandatory, not best-effort.** There is real history to lose.
- Skip step 7 — the config entry already exists. Replace the files, restart, and verify.
- **Coming from before 3.3.0** (entities were `input_number.*` / `input_select.*` /
  `input_boolean.*`): the recorder migration renames those to `number.*` / `select.*` /
  `switch.*` and carries their history and long-term statistics across. Turn it on through
  the options flow — same shape as step 7, but keyed by `entry_id` and without `id_name`:

  ```bash
  ha -X POST "$HA_URL/api/config/config_entries/options/flow" -d '{"handler":"<entry_id>"}'
  ha -X POST "$HA_URL/api/config/config_entries/options/flow/<flow_id>" -d '{
    "mqtt_node":"<unchanged>","language":"<unchanged>",
    "hexformat":<unchanged>,"thermiq_dbg":<unchanged>,"migrate_data":true}'
  ```

  Read the current values from the entry first and resubmit them unchanged — the options
  form replaces the whole entry data, so a field you omit is a field you have changed. If
  the options endpoint is unavailable on this HA version, have the user tick *Request
  migration of old data in recorder database* in Settings → Devices & Services → ThermIQ →
  Configure instead. Saving options reloads the entry, so the migration starts immediately.
  - It rewrites recorder rows and can take a long time on a large database.
  - It runs once; the flag is cleared automatically afterwards.
  - Afterwards, read the persistent notification
    `thermiq_mqtt_<id_name>_input_platform_migration` (websocket
    `{"type":"persistent_notification/get"}`) — it lists every renamed entity. Automations,
    scripts, templates and dashboards that referenced the old ids need a find-and-replace,
    which the integration deliberately does not do for the user. Offer to help with that
    as a separate, reviewed change.
- **Coming from before 3.5.0**: the dashboard card changed. See *Upgrading the dashboard
  card* in the README — old `www/thermiq/` copies of the widget and their dashboard
  resource must be removed or the card loads twice, and the `vp_base*.png` images, the HTML
  Jinja2 Template card, Number Box and apexcharts-card dependencies can all go.

## Health check mode

If the user asks you to check an existing install rather than install one, run steps 1, 2,
3 and 8 only, and report:

- integration version vs. the latest release tag
- config entry state, and its `mqtt_node` vs. the node actually publishing
- entity count, how many are `unavailable` or `unknown`
- seconds since the last MQTT message
- ThermIQ lines in `/api/error_log`

Change nothing.

## Uninstall / rollback

In this order:

1. Delete the config entry — this removes all its entities:
   ```bash
   ha "$HA_URL/api/config/config_entries/entry?domain=thermiq_mqtt"   # find entry_id
   ha -X DELETE "$HA_URL/api/config/config_entries/entry/<entry_id>"
   ```
2. Remove `<config>/custom_components/thermiq_mqtt/` (or uninstall in HACS).
3. Restart Home Assistant.
4. Recorder history that the migration rewrote is **not** restored by any of this — that is
   what the step 4 backup is for.

## Failure playbook

| Symptom | Check | Fix |
|---------|-------|-----|
| `/api/` returns 401 | Token wrong or revoked | New long-lived token from an admin account |
| Admin endpoints 403 but `/api/` works | Token is from a non-admin user | Admin account required |
| Config flow returns `{"message":"Invalid handler specified"}` | Integration files not loaded | Wrong path or missing restart — recheck step 5, then 6 |
| Entry created, all entities `unavailable` | Wrong `mqtt_node`, or the pump is offline | Redo step 3; check the pump in MQTT Explorer |
| Some entities `unknown` | Those registers are not in this pump's payload | Normal — model-dependent |
| Card shows "Custom element doesn't exist: thermiq-widget-card" | Browser cache | Hard-refresh (Ctrl/Cmd+Shift+R); confirm `thermiq_mqtt` is in `components` |
| Card shows "Custom element doesn't exist: fold-entity-row" | Dependency missing | Step 9 |
| Controls do nothing, sensors fine | `hexformat` inverted, or `thermiq_dbg` left on | Integration options → Configure |
| Entity ids gained a `_2` suffix | Old entities still registered from a previous install | Delete the stale entities in the entity registry, then reload the entry |
| History disappeared after an upgrade | Migration renamed the entities | Read the migration notification for the mapping; restore the backup if needed |
