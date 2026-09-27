"""Step 4: build data/overlay.json, the one file the Firefox extension reads.

Keyed by Kalshi event ticker (e.g. "KXPOKEMON-26SEPSQU"); each active event
gets its markets, its matched TCGplayer product, TCGplayer sales totals per
week (summed over every condition/printing of the product), and a sales-volume
level comparing last week's TCGplayer spending with the Kalshi volume.
"""

import json
from datetime import datetime, timezone

from .Apify import sales_path
from .config import ID_MAP_PATH, KALSHI_FILE, OVERLAY_FILE

# Sales-volume levels. "ratio" is last week's TCGplayer dollar sales divided by
# the Kalshi event's total volume (contracts, $1 face value each). A thin
# underlying market means a handful of sales can move the price Kalshi settles on.
LOW_UNITS = 5      # fewer units than this sold last week -> low
LOW_RATIO = 1.0    # TCGplayer spent less last week than was traded on Kalshi -> low
HIGH_UNITS = 20    # high needs at least this many units sold last week...
HIGH_RATIO = 5.0   # ...and at least this multiple of the Kalshi volume


def weekly_sales(path):
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)

    weeks = {}
    for sku in data["skus"]:
        for bucket in sku.get("buckets") or []:
            week = weeks.setdefault(bucket["bucketStartDate"], {"transactions": 0, "quantity": 0, "dollars": 0.0})
            week["transactions"] += int(bucket["transactionCount"])
            week["quantity"] += int(bucket["quantitySold"])
            # Estimated spend: units sold at that week's TCGplayer market price.
            week["dollars"] += int(bucket["quantitySold"]) * float(bucket["marketPrice"] or 0)

    return {
        "fetched_at": data["fetched_at"],
        "total_transactions": sum(w["transactions"] for w in weeks.values()),
        "total_quantity": sum(w["quantity"] for w in weeks.values()),
        "weeks": [{"week": day, **weeks[day], "dollars": round(weeks[day]["dollars"], 2)} for day in sorted(weeks)],
    }


def sales_level(sales, kalshi_volume):
    if not sales or not sales["weeks"]:
        return None
    last = sales["weeks"][-1]
    ratio = last["dollars"] / kalshi_volume if kalshi_volume else None
    if last["quantity"] < LOW_UNITS or (ratio is not None and ratio < LOW_RATIO):
        level = "low"
    elif last["quantity"] >= HIGH_UNITS and (ratio is None or ratio >= HIGH_RATIO):
        level = "high"
    else:
        level = "moderate"
    return {"level": level, "ratio": ratio and round(ratio, 3), "week": last}


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

    for event in events.values():
        event["kalshi_volume"] = round(sum(m["volume"] for m in event["markets"]), 2)
        event["sales_volume"] = sales_level(event["sales"], event["kalshi_volume"])

    with open(OVERLAY_FILE, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "events": events,
        }, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(events)} events to {OVERLAY_FILE}")


if __name__ == "__main__":
    main()
