"""Step 1: download volume and Yes/No prices for Kalshi's Pokémon product price markets.

Kalshi's "Culture" section maps to the "Entertainment" category in the API.
No API key is needed; every endpoint used here is public market data.

Yes/No prices are the current ask prices in dollars, i.e. what the site shows
on the Yes and No buttons as the cost to buy one contract.
"""

import json
import re
import time

import requests

from .config import KALSHI_FILE

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
CATEGORY = "Entertainment"

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


def is_pokemon_product_series(series):
    tags = series.get("tags") or []
    text = f"{series.get('title', '')} {series.get('ticker', '')}".lower()
    mentions_pokemon = "Pokémon" in tags or "pokemon" in text or "pokémon" in text
    return mentions_pokemon and "Video games" not in tags


def product_name(market):
    """The card/product name, e.g. "Squirtle" from "...Ungraded Price of the Squirtle on Collectr..."."""
    match = re.search(r"Price of the (.+?) on ", market["rules_primary"])
    return match.group(1) if match else market["title"]


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
        "product": product_name(market),
        "title": market["title"],
        "status": market["status"],
        "volume": float(market["volume_fp"]),
        "yes_price": yes_price,
        "no_price": no_price,
    }


def main():
    all_series = get_all("/series", "series", {"category": CATEGORY}, limit=None)
    pokemon_series = [s for s in all_series if is_pokemon_product_series(s)]

    markets = []
    for series in pokemon_series:
        markets += get_all("/markets", "markets", {"series_ticker": series["ticker"]})

    rows = [summarize(m) for m in markets]
    KALSHI_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KALSHI_FILE, "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(rows)} markets to {KALSHI_FILE}")
    return active_products()


def active_products():
    """{product name: strike price} for every active market in KALSHI_FILE."""
    with open(KALSHI_FILE) as f:
        rows = json.load(f)
    products = {}
    for row in rows:
        if row["status"] == "active":
            strike = float(row["ticker"].rsplit("-", 1)[-1])
            products.setdefault(row["product"], strike)
    return products


if __name__ == "__main__":
    main()
