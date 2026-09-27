// Shows TCGplayer sales data from the pipeline's overlay.json on Kalshi pages.
//
// The panel stays on every Kalshi page. On a Pokémon market it shows that market;
// elsewhere it lists all active Pokémon markets. Kalshi is a single-page app, so
// the page is re-checked every second for navigation.

const DATA_URL = "https://raw.githubusercontent.com/milesbhall/volumemaster2/main/data/overlay.json";
const DATA_MAX_AGE_MS = 30 * 60 * 1000;
const RETRY_AFTER_MS = 60 * 1000;

const LEVELS = {
  low: { label: "Low sales volume", order: 0 },
  moderate: { label: "Moderate sales volume", order: 1 },
  high: { label: "High sales volume", order: 2 },
};

let data = null;
let dataLoadedAt = 0;
let failedAt = 0;
let host = null;          // element holding the panel's shadow root
let renderedKey = null;   // what the panel currently shows, to avoid redrawing every second
let collapsed = false;    // remembered across pages and sessions
let chosen = null;        // {href, ticker}: a market or the overview (ticker null) picked in the panel

async function loadData() {
  if (data && Date.now() - dataLoadedAt < DATA_MAX_AGE_MS) return data;
  const resp = await fetch(DATA_URL, { cache: "no-cache" });
  if (!resp.ok) throw new Error(`overlay.json: HTTP ${resp.status}`);
  data = await resp.json();
  dataLoadedAt = Date.now();
  return data;
}

// Find the Kalshi event for this page: by ticker in the URL, else by product name on the page.
function findEvent(events) {
  const fromUrl = location.href.match(/kxpokemon-[a-z0-9]+/i);
  if (fromUrl && events[fromUrl[0].toUpperCase()]) return fromUrl[0].toUpperCase();

  const headings = [...document.querySelectorAll("h1, h2")].map((el) => el.textContent);
  const pageText = [document.title, ...headings].join(" \n ").toLowerCase();
  let best = null;
  for (const [ticker, event] of Object.entries(events)) {
    const name = event.product.toLowerCase();
    if (pageText.includes(name) && (!best || name.length > events[best].product.length)) best = ticker;
  }
  return best;
}

// Tiny element builder; all text goes through textContent.
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "onclick") el.onclick = v;
    else if (k === "style") el.style.cssText = v;
    else el.setAttribute(k, v);
  }
  for (const c of children) if (c != null && c !== false) el.append(c);
  return el;
}

const money = (n) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const dollars = (n) => `$${Math.round(n).toLocaleString()}`;
const compactDollars = (n) =>
  n < 1000 ? dollars(n) : `$${Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(n)}`;
const count = (n) => n.toLocaleString();
const shortDate = (iso) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const weekDate = (day) => shortDate(day + "T00:00");

// --- Kalshi vs. TCGplayer comparison -------------------------------------------------

function compareBars(event, compact) {
  const sv = event.sales_volume;
  const kalshi = event.kalshi_volume ?? 0;
  const tcg = sv ? sv.week.dollars : 0;
  const max = Math.max(kalshi, tcg, 1);
  const row = (cls, label, value) =>
    h("div", { class: `bar-row ${cls}` },
      !compact && h("div", { class: "bar-label" }, label),
      h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: `width:${Math.max(1, (value / max) * 100)}%` })),
      h("div", { class: "bar-value" }, compact ? compactDollars(value) : dollars(value)));
  return h("div", { class: `compare${compact ? " compact" : ""}` },
    row("kalshi", "Kalshi volume, all time", kalshi),
    row("tcg", sv ? `TCGplayer sales, wk of ${weekDate(sv.week.week)}` : "TCGplayer sales, last week", tcg));
}

function warningText(event) {
  const sv = event.sales_volume;
  const { quantity, dollars: spent } = sv.week;
  const vsKalshi = sv.ratio == null ? ""
    : sv.ratio < 1 ? `, ${Math.round(sv.ratio * 100)}% of the Kalshi volume`
    : `, ${sv.ratio.toFixed(1)}× the Kalshi volume`;
  const sold = `${count(quantity)} sold on TCGplayer last week (~${dollars(spent)}${vsKalshi}).`;
  if (sv.level === "low") return `${sold} With this few sales, a handful of trades can move the price this market settles on.`;
  if (sv.level === "moderate") return `${sold} Enough activity that single sales matter less, but the price can still swing.`;
  return `${sold} A busy market: the settlement price is backed by steady sales.`;
}

function badge(level) {
  return h("span", { class: `badge ${level}` }, LEVELS[level].label.replace(" sales volume", ""));
}

// --- Views ---------------------------------------------------------------------------

function overviewView(overlay) {
  const rows = Object.entries(overlay.events).sort(([, a], [, b]) =>
    (LEVELS[a.sales_volume?.level]?.order ?? 3) - (LEVELS[b.sales_volume?.level]?.order ?? 3) ||
    (b.kalshi_volume ?? 0) - (a.kalshi_volume ?? 0));

  return [
    h("div", { class: "legend" },
      h("span", { class: "key kalshi" }, "Kalshi volume"),
      h("span", { class: "key tcg" }, "TCGplayer sales, last week")),
    h("div", { class: "list" }, ...rows.map(([ticker, event]) =>
      h("button", { class: "row", onclick: () => choose(ticker) },
        h("div", { class: "row-head" },
          h("span", { class: "row-name" }, event.product),
          event.sales_volume && badge(event.sales_volume.level)),
        compareBars(event, true)))),
  ];
}

function eventView(event) {
  const tcg = event.tcgplayer;
  const sales = event.sales;
  const sv = event.sales_volume;
  const strike = event.markets[0]?.strike;
  const body = [];

  body.push(compareBars(event, false));
  if (sv) {
    body.push(h("div", { class: `warning ${sv.level}` },
      h("strong", {}, (sv.level === "low" ? "⚠ " : "") + LEVELS[sv.level].label),
      h("div", {}, warningText(event))));
  }

  if (tcg) {
    const closest = strike != null && tcg.market_prices?.length
      ? tcg.market_prices.reduce((a, b) => (Math.abs(b - strike) < Math.abs(a - strike) ? b : a))
      : null;
    body.push(
      h("a", { class: "match", href: tcg.url, target: "_blank", rel: "noopener" }, `${tcg.name} · ${tcg.set}`),
      h("div", { class: "prices" },
        closest != null ? `TCGplayer ${money(closest)}` : "No TCGplayer market price",
        strike != null ? ` · Kalshi strike ${money(strike)}` : "",
        tcg.price_gap ? ` (${tcg.price_gap} apart)` : ""),
    );
    if (tcg.matched_by === "closest price") {
      body.push(h("div", { class: "note" }, "Printing matched by price; Kalshi doesn't name the set."));
    }
  } else {
    body.push(h("div", { class: "note" }, "No TCGplayer product matched yet."));
  }

  if (sales && sales.weeks.length) {
    const weeks = sales.weeks;
    const last = weeks[weeks.length - 1];
    const recent = weeks.slice(-4);
    const avg = recent.reduce((s, w) => s + w.quantity, 0) / recent.length;
    body.push(
      h("div", { class: "stats" },
        stat("sold last week", count(last.quantity)),
        stat("4-wk avg / wk", count(Math.round(avg))),
        stat("sold, 52 wks", count(sales.total_quantity))),
      sparkline(weeks),
      h("div", { class: "axis" },
        h("span", {}, new Date(weeks[0].week + "T00:00").toLocaleDateString(undefined, { month: "short", year: "numeric" })),
        h("span", {}, "units sold per week")),
    );
  } else if (tcg) {
    body.push(h("div", { class: "note" }, "No TCGplayer sales data yet."));
  }
  return body;
}

function stat(label, value) {
  return h("div", { class: "stat" }, h("div", { class: "value" }, value), h("div", { class: "label" }, label));
}

function sparkline(weeks) {
  const ns = "http://www.w3.org/2000/svg";
  const width = 280, height = 44, gap = 1;
  const max = Math.max(1, ...weeks.map((w) => w.quantity));
  const barWidth = width / weeks.length - gap;
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "spark");
  weeks.forEach((w, i) => {
    const barHeight = Math.max(1, (w.quantity / max) * height);
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x", i * (barWidth + gap));
    rect.setAttribute("y", height - barHeight);
    rect.setAttribute("width", barWidth);
    rect.setAttribute("height", barHeight);
    if (i === weeks.length - 1) rect.setAttribute("class", "latest");
    const title = document.createElementNS(ns, "title");
    title.textContent = `Week of ${w.week}: ${w.quantity} sold in ${w.transactions} transactions`;
    rect.append(title);
    svg.append(rect);
  });
  return svg;
}

// --- Panel -----------------------------------------------------------------------------

function renderPanel(overlay, ticker) {
  const event = ticker && overlay.events[ticker];
  const toggle = h("button", { class: "icon", title: collapsed ? "Expand" : "Minimize", "aria-label": collapsed ? "Expand" : "Minimize" },
    collapsed ? "+" : "–");
  toggle.onclick = () => setCollapsed(!collapsed);

  const title = event
    ? h("div", { class: "title" },
        h("button", { class: "back", title: "All markets", onclick: () => choose(null) }, "‹"),
        h("strong", {}, event.product))
    : h("div", { class: "title" }, h("strong", {}, "Pokémon markets"), ` · ${Object.keys(overlay.events).length} active`);

  const header = h("header", {}, title, event?.sales_volume && collapsed ? badge(event.sales_volume.level) : null, toggle);
  if (collapsed) header.onclick = (e) => { if (e.target === header) setCollapsed(false); };

  return h("section", { class: `panel${collapsed ? " collapsed" : ""}` },
    header,
    h("div", { class: "body" },
      ...(event ? eventView(event) : overviewView(overlay)),
      h("div", { class: "footer" },
        "Kalshi volume is contracts traded at $1 face value. TCGplayer sales are units × market price, all conditions & printings. ",
        `Data updated ${shortDate(overlay.generated_at)}.`)));
}

function draw(overlay, ticker) {
  if (!host?.isConnected) {
    host = document.createElement("div");
    host.id = "volumemaster2-overlay";
    host.attachShadow({ mode: "open" });
    document.documentElement.append(host);
  }
  const scrollTop = host.shadowRoot.querySelector(".list")?.scrollTop ?? 0;
  host.shadowRoot.replaceChildren(h("style", {}, STYLES), renderPanel(overlay, ticker));
  const list = host.shadowRoot.querySelector(".list");
  if (list) list.scrollTop = scrollTop;
}

function choose(ticker) {
  chosen = { href: location.href, ticker };
  renderedKey = null;
  check();
}

function setCollapsed(value) {
  collapsed = value;
  browser.storage.local.set({ collapsed }).catch(() => {});
  renderedKey = null;
  check();
}

async function check() {
  if (Date.now() - failedAt < RETRY_AFTER_MS) return;
  let overlay;
  try {
    overlay = await loadData();
  } catch (err) {
    failedAt = Date.now();
    console.warn("[volumemaster2] could not load overlay data:", err);
    return;
  }

  // A market picked in the panel wins until the page changes; then follow the page.
  if (chosen && chosen.href !== location.href) chosen = null;
  const ticker = chosen ? chosen.ticker : findEvent(overlay.events);

  const key = [location.href, ticker, collapsed, overlay.generated_at].join("|");
  if (key === renderedKey && host?.isConnected) return;
  draw(overlay, ticker);
  renderedKey = key;
}

const STYLES = `
  :host { all: initial; }
  .panel {
    --bg: #ffffff; --fg: #111418; --muted: #5f6b7a; --border: #dde2e8; --hover: #f2f4f7;
    --kalshi: #0e9f6e; --tcg: #1f6feb; --spark: #9db4d0; --track: #eef1f4;
    --low: #cf222e; --low-bg: #ffebe9; --mod: #9a6700; --mod-bg: #fff8c5; --high: #1a7f37; --high-bg: #dafbe1;
    position: fixed; right: 16px; bottom: 16px; z-index: 2147483647;
    width: 328px; max-width: calc(100vw - 32px);
    background: var(--bg); color: var(--fg); border: 1px solid var(--border); border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0,0,0,.12);
    font: 13px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    .panel {
      --bg: #16191d; --fg: #e8ebef; --muted: #98a2ae; --border: #2c323a; --hover: #1f2329;
      --kalshi: #34c38f; --tcg: #6ea8ff; --spark: #4a6285; --track: #242a31;
      --low: #ff7b72; --low-bg: #3b1d1f; --mod: #e3b341; --mod-bg: #332a12; --high: #56d364; --high-bg: #16301f;
    }
  }
  button { font: inherit; color: inherit; }
  header { display: flex; align-items: center; gap: 6px; padding: 8px 8px 8px 12px; border-bottom: 1px solid var(--border); }
  .collapsed header { border-bottom: none; cursor: pointer; }
  .collapsed .body { display: none; }
  .title { flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px; color: var(--muted); white-space: nowrap; overflow: hidden; }
  .title strong { color: var(--fg); font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
  .icon, .back { all: unset; cursor: pointer; width: 24px; height: 24px; flex: none; text-align: center; border-radius: 6px; color: var(--muted); font-size: 16px; line-height: 24px; }
  .back { font-size: 20px; }
  .icon:hover, .back:hover { background: var(--hover); color: var(--fg); }
  .body { padding: 12px; display: grid; gap: 10px; max-height: min(560px, calc(100vh - 110px)); overflow-y: auto; }

  .legend { display: flex; gap: 12px; font-size: 11px; color: var(--muted); }
  .key::before { content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 5px; vertical-align: 0; }
  .key.kalshi::before { background: var(--kalshi); }
  .key.tcg::before { background: var(--tcg); }
  .list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 2px; margin: 0 -6px; }
  .row { all: unset; cursor: pointer; display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; padding: 8px 6px; border-radius: 8px; box-sizing: border-box; width: 100%; min-width: 0; }
  .row:hover { background: var(--hover); }
  .row:focus-visible { outline: 2px solid var(--tcg); }
  .row-head { display: flex; align-items: center; gap: 8px; }
  .row-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }

  .badge { flex: none; font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 999px; }
  .badge.low { color: var(--low); background: var(--low-bg); }
  .badge.moderate { color: var(--mod); background: var(--mod-bg); }
  .badge.high { color: var(--high); background: var(--high-bg); }

  .compare { display: grid; gap: 6px; }
  .compare.compact { gap: 3px; }
  .bar-row { display: grid; grid-template-columns: minmax(0, 1fr) 52px; align-items: center; gap: 8px; }
  .compare:not(.compact) .bar-row { grid-template-columns: minmax(0, 1fr) 64px; grid-template-areas: "label label" "track value"; row-gap: 2px; }
  .bar-label { grid-area: label; font-size: 11px; color: var(--muted); }
  .bar-track { height: 6px; background: var(--track); border-radius: 3px; overflow: hidden; }
  .compare:not(.compact) .bar-track { grid-area: track; height: 10px; border-radius: 5px; }
  .bar-fill { height: 100%; border-radius: inherit; }
  .kalshi .bar-fill { background: var(--kalshi); }
  .tcg .bar-fill { background: var(--tcg); }
  .bar-value { text-align: right; font-size: 11px; font-variant-numeric: tabular-nums; color: var(--muted); }
  .compare:not(.compact) .bar-value { grid-area: value; font-size: 13px; font-weight: 600; color: var(--fg); }

  .warning { padding: 8px 10px; border-radius: 8px; font-size: 12px; display: grid; gap: 2px; }
  .warning strong { font-size: 13px; }
  .warning.low { background: var(--low-bg); } .warning.low strong { color: var(--low); }
  .warning.moderate { background: var(--mod-bg); } .warning.moderate strong { color: var(--mod); }
  .warning.high { background: var(--high-bg); } .warning.high strong { color: var(--high); }

  .match { color: var(--tcg); text-decoration: none; font-weight: 600; }
  .match:hover { text-decoration: underline; }
  .prices, .note, .footer, .axis, .stat .label { color: var(--muted); }
  .note, .footer { font-size: 12px; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .stat .value { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .stat .label { font-size: 11px; }
  .spark { width: 100%; height: 44px; display: block; }
  .spark rect { fill: var(--spark); }
  .spark rect.latest { fill: var(--tcg); }
  .axis { display: flex; justify-content: space-between; font-size: 11px; margin-top: -6px; }
  .footer { border-top: 1px solid var(--border); padding-top: 8px; font-size: 11px; }
`;

browser.storage.local.get("collapsed")
  .then((saved) => { collapsed = Boolean(saved.collapsed); })
  .catch(() => {})
  .finally(() => {
    check();
    setInterval(check, 1000);
  });
