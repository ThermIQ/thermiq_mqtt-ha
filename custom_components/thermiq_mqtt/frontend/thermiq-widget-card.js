/* thermiq-widget-card
 *
 * Renders the ThermIQ heat-pump SVG widget from a Jinja2 template file
 * served by the integration, using HA's render_template websocket
 * subscription. Updates are applied by DOM *morphing* (in-place diff of
 * attributes and text nodes) instead of innerHTML replacement, so CSS
 * animations keep running across re-renders — the pump clock can tick
 * every 30 s without restarting every arrow and impeller.
 *
 * Usage (as an entities-card row or a standalone card):
 *   type: custom:thermiq-widget-card
 *   entity_prefix: thermiq_mqtt_vp1                   # default; set to
 *                          # thermiq_mqtt_<id> if your entry id isn't vp1
 *
 * There is also a template_url option, but do not set it. It defaults to the
 * path the integration serves, and pinning a path in card config means the
 * card breaks the next time that path changes - which is exactly what
 * happened when the template moved out of www/ and into the integration.
 *
 * Editing workflow: edit heatpump_widget.j2 next to this file in the
 * integration folder and reload the page. The template is fetched with
 * cache: "no-store", which bypasses the HTTP cache, so edits show up on the
 * next reload even though the directory is served with normal cache headers.
 * Editing *this* file needs CARD_VERSION in __init__.py bumped, because the
 * browser caches it against the ?v= in the import URL.
 */

const VERSION = "1.2.0";
const DEFAULT_URL = "/thermiq_mqtt_frontend/heatpump_widget.j2";
const DEFAULT_PREFIX = "thermiq_mqtt_vp1"; // integration domain + entry id

/* ---- Template loading ---------------------------------------------- */

// Home Assistant instantiates a card element several times while laying a
// dashboard out, and each instance used to fetch the 34 kB template again.
// One in-flight request per URL is shared instead. Still one fetch per page
// load, so editing the template and reloading still shows the change.
const templateRequests = new Map();

function loadTemplate(url) {
  let pending = templateRequests.get(url);
  if (!pending) {
    pending = fetch(url, { cache: "no-store" })
      .then((resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp.text();
      })
      .catch((err) => {
        // never cache a failure - a transient error would otherwise stick
        // for the lifetime of the page
        templateRequests.delete(url);
        throw err;
      });
    templateRequests.set(url, pending);
  }
  return pending;
}

/* ---- DOM morphing ------------------------------------------------- */

// Elements are compatible when node type + tag match and their ids (if
// any) agree; incompatible nodes are replaced, compatible ones morphed.
function compatible(a, b) {
  if (a.nodeType !== b.nodeType) return false;
  if (a.nodeType !== Node.ELEMENT_NODE) return true;
  if (a.nodeName !== b.nodeName) return false;
  return (a.id || "") === (b.id || "");
}

function morphElement(live, next) {
  // Sync attributes; skip identical values so style recalc / animation
  // state is only touched when something actually changed.
  for (const attr of Array.from(next.attributes)) {
    if (live.getAttribute(attr.name) !== attr.value) {
      live.setAttribute(attr.name, attr.value);
    }
  }
  for (const attr of Array.from(live.attributes)) {
    if (!next.hasAttribute(attr.name)) live.removeAttribute(attr.name);
  }
  // Rewriting <style> text restarts the animations it defines — only
  // touch it when the CSS itself changed.
  if (live.nodeName === "STYLE") {
    if (live.textContent !== next.textContent) {
      live.textContent = next.textContent;
    }
    return;
  }
  morphChildren(live, next);
}

function morphChildren(live, next) {
  // Map id'd live children for keyed matching: conditional flow paths
  // appearing/disappearing must not knock later siblings out of place.
  const byId = new Map();
  for (const c of live.children) {
    if (c.id) byId.set(c.id, c);
  }
  const kept = new Set();
  let cursor = live.firstChild;

  for (const n of Array.from(next.childNodes)) {
    let match = null;
    if (n.nodeType === Node.ELEMENT_NODE && n.id) {
      const cand = byId.get(n.id);
      if (cand && !kept.has(cand) && cand.nodeName === n.nodeName) match = cand;
    } else {
      // Positional match: advance past already-kept/moved nodes.
      let probe = cursor;
      while (probe && (kept.has(probe) || !compatible(probe, n))) {
        // Only look one step past incompatible whitespace-ish noise;
        // otherwise treat as structural change and insert fresh.
        if (kept.has(probe)) {
          probe = probe.nextSibling;
          continue;
        }
        probe = null;
      }
      match = probe;
    }

    if (match) {
      if (match !== cursor) {
        live.insertBefore(match, cursor); // move into position
      } else {
        cursor = cursor.nextSibling;
      }
      kept.add(match);
      if (n.nodeType === Node.ELEMENT_NODE) {
        morphElement(match, n);
      } else if (match.nodeValue !== n.nodeValue) {
        match.nodeValue = n.nodeValue;
      }
    } else {
      // New structure (a flow that just started): adopt the fresh node.
      const adopted = n; // moving it out of the parsed fragment is fine
      live.insertBefore(adopted, cursor);
      kept.add(adopted);
    }
  }

  // Drop live nodes that no longer exist in the new render.
  for (const c of Array.from(live.childNodes)) {
    if (!kept.has(c)) live.removeChild(c);
  }
}

/* ---- The card ------------------------------------------------------ */

class ThermiqWidgetCard extends HTMLElement {
  setConfig(config) {
    this._config = { template_url: DEFAULT_URL, ...config };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._started) {
      this._started = true;
      this._init();
    }
  }

  getCardSize() {
    return 5;
  }

  async _init() {
    this.style.display = "block";
    this._root = document.createElement("div");
    // The template positions every element absolutely against its container,
    // so something here has to be that container. Without it the nearest
    // positioned ancestor is hui-view-container and the widget lays itself out
    // against the whole view - drawing over the header, wherever the card
    // happens to sit. It only looked right as an entities row because
    // something in that chain happened to be positioned.
    //
    // No padding here: an absolutely positioned child resolves against the
    // padding *box*, which includes the padding, so padding would add height
    // without insetting anything. The template already insets itself - its
    // outer div starts at left:15px and its topmost pill at top:14px.
    this._root.style.position = "relative";
    // Wrapped in an ha-card so it reads as a card - background, radius and
    // elevation from the active theme, like every other card in the view.
    // `card: false` opts out, for anyone nesting this inside a card of their
    // own and not wanting two.
    if (this._config.card === false) {
      this.appendChild(this._root);
    } else {
      const card = document.createElement("ha-card");
      // On the card, not on the containing block: padding on the containing
      // block would not inset absolutely positioned children at all, because
      // their containing block is its padding box.
      card.style.padding = "16px";
      card.appendChild(this._root);
      this.appendChild(card);
    }
    try {
      this._template = await loadTemplate(this._config.template_url);
      const prefix = this._config.entity_prefix || DEFAULT_PREFIX;
      if (prefix !== DEFAULT_PREFIX) {
        this._template = this._template.split(DEFAULT_PREFIX).join(prefix);
      }
    } catch (e) {
      this._root.innerHTML =
        `<div style="color:var(--error-color,red);padding:8px;">` +
        `thermiq-widget-card: cannot load ${this._config.template_url}: ${e.message}</div>`;
      return;
    }
    if (this.isConnected) this._subscribe();
  }

  _subscribe() {
    if (this._unsubPromise || !this._template || !this._hass) return;
    this._unsubPromise = this._hass.connection.subscribeMessage(
      (msg) => this._onRender(msg),
      {
        type: "render_template",
        template: this._template,
        report_errors: true,
      }
    );
    this._unsubPromise.catch((e) => {
      this._unsubPromise = null;
      this._root.innerHTML =
        `<div style="color:var(--error-color,red);padding:8px;">` +
        `thermiq-widget-card: template subscription failed: ${e.message || e.code || e}</div>`;
    });
  }

  _onRender(msg) {
    if (msg.error) {
      // Transient render errors (entity briefly unavailable): keep the
      // last good frame on screen, log for debugging.
      console.warn("thermiq-widget-card: template error:", msg.error);
      return;
    }
    if (typeof msg.result !== "string") return;
    const tpl = document.createElement("template");
    tpl.innerHTML = msg.result;
    morphChildren(this._root, tpl.content);
    if (!this._fitted) {
      this._fitted = true;
      requestAnimationFrame(() => this._fit());
    }
  }

  /* Shrink the box to the drawing, so the drawing can be centred.
   *
   * Every element in the template is absolutely positioned, and an absolutely
   * positioned child contributes nothing to its container's intrinsic size -
   * so the drawing's width is invisible to CSS. `width: max-content` and
   * friends all resolve to zero here. The only way to know how wide it is, is
   * to look. Measured once, after the first render has laid out.
   *
   * Deliberately not a constant: it comes out of whatever the template drew,
   * so re-vendoring a wider template does not silently mis-centre it. */
  _fit() {
    const box = this._root.getBoundingClientRect();
    if (!box.width) return;
    let left = Infinity;
    let right = 0;
    for (const el of this._root.querySelectorAll("*")) {
      const style = getComputedStyle(el);
      if (style.position !== "absolute") continue;
      if (style.display === "none" || style.visibility === "hidden") continue;
      const rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height) continue;
      left = Math.min(left, rect.left - box.left);
      right = Math.max(right, rect.right - box.left);
    }
    if (!isFinite(left) || right <= 0) return;

    // width = left + right, not right: the drawing does not start at the box's
    // left edge, it starts `left` in. Centring a box of width `right` would
    // leave the drawing off-centre by left/2 - measured at 14px, which is
    // visible. Padding the box by `left` on the right instead makes it
    // symmetric about the drawing, so auto margins centre what you can see.
    const width = Math.ceil(left + right);
    if (width >= box.width) return; // no room to centre into
    this._root.style.width = width + "px";
    this._root.style.marginLeft = "auto";
    this._root.style.marginRight = "auto";
  }

  connectedCallback() {
    if (this._started && this._template) this._subscribe();
  }

  disconnectedCallback() {
    const p = this._unsubPromise;
    this._unsubPromise = null;
    if (p) p.then((unsub) => unsub()).catch(() => {});
  }
}

// Defining a name twice throws, and the throw aborts the rest of this module.
// Two evaluations are possible whenever the browser sees two distinct URLs for
// this file - a stale ?v= alongside a fresh one, or the same card delivered
// both as an extra JS module and as a Lovelace resource - and the module map
// keys on the full URL, so each is fetched and run separately. Losing the
// second race silently is fine; taking the card down with an uncaught
// NotSupportedError is not.
if (!customElements.get("thermiq-widget-card")) {
  customElements.define("thermiq-widget-card", ThermiqWidgetCard);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "thermiq-widget-card",
    name: "ThermIQ Widget Card",
    description:
      "Animated heat-pump schematic rendered from a Jinja2 template file with flicker-free DOM morphing.",
  });

  console.info(
    `%c THERMIQ-WIDGET-CARD %c v${VERSION} `,
    "color:white;background:#0288d1;font-weight:700;",
    "color:#0288d1;background:white;font-weight:700;"
  );
}
