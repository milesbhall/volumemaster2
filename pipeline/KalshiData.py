"""Step 1: download volume and Yes/No prices for Kalshi's Pokémon product price markets.

Series are found by their Pokémon tag or title in any Kalshi category, and a
market is kept only if its rules name a price ("... price of the <product> on
<platform> ..."), so new cards and products are picked up without code changes.
No API key is needed; every endpoint used here is public market data.

Yes/No prices are the current ask prices in dollars, i.e. what the site shows
on the Yes and No buttons as the cost to buy one contract.
"""

import json
import re
import time
from datetime import datetime

import requests

from .config import KALSHI_FILE

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
PRODUCT_PATTERN = re.compile(r"price of (?:the )?(.+?) on ", re.IGNORECASE)

session = requests.Session()


def get(path, params=None, retries=5):
    """GET a public endpoint, backing off when rate limited."""
    for attempt in range(retries):
        resp = session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Gave up on {path} after {retries} attempts")


def get_all(path, key, params=None, limit: int | None = 1000):
    """Follow cursor pagination and return every item under `key`."""
    params = dict(params or {}, limit=limit)
    items = []
    while True:
        data = get(path, params)
        items.extend(data.get(key) or [])
        cursor = data.get("cursor")
        if not cursor:
            return items
        params["cursor"] = cursor


def is_pokemon_series(series):
    tags = [t.lower() for t in series.get("tags") or []]
    text = f"{series.get('title', '')} {series.get('ticker', '')}".lower()
    return "pokémon" in tags or "pokemon" in tags or "pokemon" in text or "pokémon" in text


def product_name(market):
    """The product a price market is about, from its rules or title; None if it isn't a price market."""
    for text in (market.get("rules_primary") or "", market.get("title") or ""):
        match = PRODUCT_PATTERN.search(text)
        if match:
            return match.group(1).strip()
    return None


def strike(market):
    return market.get("floor_strike") if market.get("floor_strike") is not None else market.get("cap_strike")


def summarize(market):
    if market["result"] in ("yes", "no"):
        # Settled markets have no asks left; report the payout instead.
        yes_price = 1.0 if market["result"] == "yes" else 0.0
        no_price = 1.0 - yes_price
    else:
        yes_price = float(market["yes_ask_dollars"])
        no_price = float(market["no_ask_dollars"])
    return {
        "ticker": market["ticker"],
        "event_ticker": market["event_ticker"],
        "product": product_name(market),
        "strike": strike(market),
        "title": market["title"],
        "status": market["status"],
        "volume": float(market["volume_fp"]),
        "open_time": market["open_time"],
        "close_time": market["close_time"],
        "yes_price": yes_price,
        "no_price": no_price,
    }


def main():
    all_series = get_all("/series", "series", limit=None)
    pokemon_series = [s for s in all_series if is_pokemon_series(s)]

    markets = []
    for series in pokemon_series:
        markets += get_all("/markets", "markets", {"series_ticker": series["ticker"]})
    markets = [m for m in markets if product_name(m)]

    rows = [summarize(m) for m in markets]
    KALSHI_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KALSHI_FILE, "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(rows)} markets to {KALSHI_FILE}")
    return active_products()


def traded_volume(ticker, start_ts, end_ts):
    """Contracts traded in one market between two Unix timestamps."""
    trades = get_all("/markets/trades", "trades", {"ticker": ticker, "min_ts": start_ts, "max_ts": end_ts})
    return sum(float(t["count_fp"]) for t in trades)


def active_products():
    """{product name: strike price} for every active market in KALSHI_FILE."""
    with open(KALSHI_FILE) as f:
        rows = json.load(f)
    products = {}
    for row in rows:
        if row["status"] == "active" and row["strike"] is not None:
            products.setdefault(row["product"], row["strike"])
    return products


def open_times():
    """{product name: when its earliest active market opened} from KALSHI_FILE."""
    with open(KALSHI_FILE) as f:
        rows = json.load(f)
    opened = {}
    for row in rows:
        if row["status"] == "active":
            t = datetime.fromisoformat(row["open_time"])
            opened[row["product"]] = min(t, opened.get(row["product"], t))
    return opened


if __name__ == "__main__":
    main()
