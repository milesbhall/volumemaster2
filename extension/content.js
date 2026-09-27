// Shows TCGplayer sales data from the pipeline's overlay.json on Kalshi Pokémon market pages.
// Kalshi is a single-page app, so the page is re-checked every second for navigation.

const DATA_URL = "https://raw.githubusercontent.com/milesbhall/volumemaster2/main/data/overlay.json";
const DATA_MAX_AGE_MS = 30 * 60 * 1000;
const RETRY_AFTER_MS = 60 * 1000;

let data = null;
let dataLoadedAt = 0;
let failedAt = 0;
let host = null;          // element holding the panel's shadow root
let shownKey = null;      // page + event the panel is currently showing
let dismissedHref = null; // page where the user closed the panel

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
    else el.setAttribute(k, v);
  }
  for (const c of children) if (c != null) el.append(c);
  return el;
}

const money = (n) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const count = (n) => n.toLocaleString();
const shortDate = (iso) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function sparkline(weeks) {
  const ns = "http://www.w3.org/2000/svg";
  const width = 280, height = 48, gap = 1;
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

function stat(label, value) {
  return h("div", { class: "stat" }, h("div", { class: "value" }, value), h("div", { class: "label" }, label));
}

function renderPanel(event, generatedAt) {
  const tcg = event.tcgplayer;
  const sales = event.sales;
  const strike = event.markets[0]?.strike;
  const body = [];

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
      h("div", { class: "axis" }, h("span", {}, new Date(weeks[0].week + "T00:00").toLocaleDateString(undefined, { month: "short", year: "numeric" })), h("span", {}, "units sold per week")),
    );
  } else if (tcg) {
    body.push(h("div", { class: "note" }, "No TCGplayer sales data yet."));
  }

  body.push(h("div", { class: "footer" },
    `All conditions & printings. Sales as of ${sales ? shortDate(sales.fetched_at) : "—"}; data updated ${shortDate(generatedAt)}.`));

  const collapse = h("button", { class: "icon", title: "Collapse", "aria-label": "Collapse" }, "–");
  const close = h("button", { class: "icon", title: "Close", "aria-label": "Close" }, "×");
  const panel = h("section", { class: "panel" },
    h("header", {}, h("div", { class: "title" }, "TCGplayer sales · ", h("strong", {}, event.product)), collapse, close),
    h("div", { class: "body" }, ...body));

  collapse.onclick = () => panel.classList.toggle("collapsed");
  close.onclick = () => { dismissedHref = location.href; removePanel(); };
  return panel;
}

function removePanel() {
  host?.remove();
  host = null;
  shownKey = null;
}

function showPanel(event, generatedAt) {
  removePanel();
  host = document.createElement("div");
  host.id = "volumemaster2-overlay";
  const root = host.attachShadow({ mode: "open" });
  root.append(h("style", {}, STYLES), renderPanel(event, generatedAt));
  document.documentElement.append(host);
}

async function check() {
  if (location.href === dismissedHref) return;
  dismissedHref = null;
  if (Date.now() - failedAt < RETRY_AFTER_MS) return;
  let overlay;
  try {
    overlay = await loadData();
  } catch (err) {
    failedAt = Date.now();
    console.warn("[volumemaster2] could not load overlay data:", err);
    return;
  }
  const ticker = findEvent(overlay.events);
  const key = ticker && `${location.href}|${ticker}`;
  if (!ticker) return removePanel();
  if (key === shownKey && host?.isConnected) return;
  showPanel(overlay.events[ticker], overlay.generated_at);
  shownKey = key;
}

const STYLES = `
  :host { all: initial; }
  .panel {
    --bg: #ffffff; --fg: #111418; --muted: #5f6b7a; --border: #dde2e8; --bar: #9db4d0; --accent: #1f6feb;
    position: fixed; right: 16px; bottom: 16px; z-index: 2147483647;
    width: 312px; max-width: calc(100vw - 32px);
    background: var(--bg); color: var(--fg); border: 1px solid var(--border); border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0,0,0,.12);
    font: 13px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    .panel { --bg: #16191d; --fg: #e8ebef; --muted: #98a2ae; --border: #2c323a; --bar: #4a6285; --accent: #6ea8ff; }
  }
  header { display: flex; align-items: center; gap: 4px; padding: 10px 10px 10px 14px; border-bottom: 1px solid var(--border); }
  .title { flex: 1; min-width: 0; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .title strong { color: var(--fg); font-weight: 600; }
  .icon { all: unset; cursor: pointer; width: 24px; height: 24px; text-align: center; border-radius: 6px; color: var(--muted); font-size: 16px; line-height: 24px; }
  .icon:hover { background: var(--border); color: var(--fg); }
  .body { padding: 12px 14px 12px; display: grid; gap: 8px; }
  .collapsed .body { display: none; }
  .collapsed header { border-bottom: none; }
  .match { color: var(--accent); text-decoration: none; font-weight: 600; }
  .match:hover { text-decoration: underline; }
  .prices, .note, .footer, .axis, .stat .label { color: var(--muted); }
  .note, .footer { font-size: 12px; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 4px; }
  .stat .value { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .stat .label { font-size: 11px; }
  .spark { width: 100%; height: 48px; display: block; }
  .spark rect { fill: var(--bar); }
  .spark rect.latest { fill: var(--accent); }
  .axis { display: flex; justify-content: space-between; font-size: 11px; margin-top: -4px; }
  .footer { border-top: 1px solid var(--border); padding-top: 8px; }
`;

check();
setInterval(check, 1000);
