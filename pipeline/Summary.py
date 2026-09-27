"""Step 4: build data/overlay.json, the one file the Firefox extension reads.

Keyed by Kalshi event ticker (e.g. "KXPOKEMON-26SEPSQU"); each active event
gets its markets, its matched TCGplayer product, and TCGplayer sales totals
per week (summed over every condition/printing of the product).
"""

import json
from datetime import datetime, timezone

from .Apify import sales_path
from .config import ID_MAP_PATH, KALSHI_FILE, OVERLAY_FILE


def weekly_sales(path):
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)

    weeks = {}
    for sku in data["skus"]:
        for bucket in sku.get("buckets") or []:
            week = weeks.setdefault(bucket["bucketStartDate"], {"transactions": 0, "quantity": 0})
            week["transactions"] += int(bucket["transactionCount"])
            week["quantity"] += int(bucket["quantitySold"])

    return {
        "fetched_at": data["fetched_at"],
        "total_transactions": sum(w["transactions"] for w in weeks.values()),
        "total_quantity": sum(w["quantity"] for w in weeks.values()),
        "weeks": [{"week": day, **weeks[day]} for day in sorted(weeks)],
    }


def main():
    with open(KALSHI_FILE) as f:
        markets = json.load(f)
    with open(ID_MAP_PATH) as f:
        id_map = json.load(f)

    events = {}
    for m in markets:
        if m["status"] != "active":
            continue
        event_ticker, strike = m["ticker"].rsplit("-", 1)
        name = m["product"]
        if event_ticker not in events:
            match = id_map.get(name, {})
            pid = match.get("product_id")
            events[event_ticker] = {
                "product": name,
                "markets": [],
                "tcgplayer": pid and {
                    "product_id": pid,
                    "url": f"https://www.tcgplayer.com/product/{pid}",
                    "name": match.get("tcgplayer_name"),
                    "set": match.get("set"),
                    "market_prices": match.get("tcgplayer_market_prices"),
                    "price_gap": match.get("price_gap"),
                    "matched_by": match.get("matched_by"),
                },
                "sales": weekly_sales(sales_path(name)),
            }
        events[event_ticker]["markets"].append({
            "ticker": m["ticker"],
            "strike": float(strike),
            "yes_price": m["yes_price"],
            "no_price": m["no_price"],
            "volume": m["volume"],
        })

    with open(OVERLAY_FILE, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "events": events,
        }, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(events)} events to {OVERLAY_FILE}")


if __name__ == "__main__":
    main()
