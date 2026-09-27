"""Step 4: build data/overlay.json, the one file the Firefox extension reads.

Keyed by Kalshi event ticker (e.g. "KXPOKEMON-26SEPSQU"); each active event
gets its markets, its matched TCGplayer product, TCGplayer sales totals per
week for the matched printing (English, all conditions), and a sales-volume
level comparing TCGplayer spending with Kalshi volume since the (monthly)
market opened.
"""

import json
from datetime import datetime, timedelta, timezone

from .Apify import sales_path
from .config import ID_MAP_PATH, KALSHI_FILE, OVERLAY_FILE
from .KalshiData import traded_volume

# Sales-volume levels, measured from when the Kalshi market opened until the
# TCGplayer sales were fetched. "ratio" is TCGplayer dollar sales divided by the
# Kalshi contracts ($1 face value each) traded over that same period. Unit
# thresholds are per week, averaged over the period, since it grows through the
# month. A thin underlying market means a handful of sales can move the price
# Kalshi settles on.
LOW_UNITS = 5      # fewer units than this sold per week -> low
LOW_RATIO = 1.0    # less spent on TCGplayer than traded on Kalshi -> low
HIGH_UNITS = 20    # high needs at least this many units sold per week...
HIGH_RATIO = 5.0   # ...and at least this multiple of the Kalshi volume


def weekly_sales(path, variant):
    """Weekly TCGplayer sales for one printing of a product (English, all conditions)."""
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)

    skus = [s for s in data["skus"] if s.get("language") == "English" and s.get("variant") == variant]
    printing_only = bool(skus)
    if not printing_only:  # printing unknown or named differently: fall back to every SKU
        skus = data["skus"]

    weeks = {}
    for sku in skus:
        for bucket in sku.get("buckets") or []:
            week = weeks.setdefault(bucket["bucketStartDate"], {"transactions": 0, "quantity": 0, "dollars": 0.0})
            week["transactions"] += int(bucket["transactionCount"])
            week["quantity"] += int(bucket["quantitySold"])
            # Estimated spend: units sold at that week's TCGplayer market price.
            week["dollars"] += int(bucket["quantitySold"]) * float(bucket["marketPrice"] or 0)

    return {
        "fetched_at": data["fetched_at"],
        "variant": variant if printing_only else None,
        "total_transactions": sum(w["transactions"] for w in weeks.values()),
        "total_quantity": sum(w["quantity"] for w in weeks.values()),
        "weeks": [{"week": day, **weeks[day], "dollars": round(weeks[day]["dollars"], 2)} for day in sorted(weeks)],
    }


def sales_since(sales, start, end):
    """TCGplayer sales between start and end.

    Buckets are weeks starting on Mondays, so a week that is only partly inside
    the window counts that share of its sales (assuming sales spread evenly).
    The newest bucket runs only until the data was fetched.
    """
    fetched_at = datetime.fromisoformat(sales["fetched_at"])
    totals = {"quantity": 0.0, "transactions": 0.0, "dollars": 0.0}
    for week in sales["weeks"]:
        b_start = datetime.fromisoformat(week["week"]).replace(tzinfo=timezone.utc)
        b_end = min(b_start + timedelta(days=7), fetched_at)
        overlap = (min(b_end, end) - max(b_start, start)).total_seconds()
        if overlap <= 0 or b_end <= b_start:
            continue
        share = overlap / (b_end - b_start).total_seconds()
        for key in totals:
            totals[key] += week[key] * share
    return {key: round(value, 2) for key, value in totals.items()}


def sales_level(sales, markets):
    """Compare TCGplayer sales with Kalshi volume from market open until the sales were fetched."""
    if not sales or not sales["weeks"]:
        return None
    start = min(datetime.fromisoformat(m["open_time"]) for m in markets)
    end = datetime.fromisoformat(sales["fetched_at"])
    if end <= start:
        return None  # sales predate this market; the next Apify run refreshes them
    tcg = sales_since(sales, start, end)
    kalshi = sum(traded_volume(m["ticker"], int(start.timestamp()), int(end.timestamp())) for m in markets)

    weeks = (end - start).total_seconds() / (7 * 86400)
    units_per_week = tcg["quantity"] / weeks
    ratio = tcg["dollars"] / kalshi if kalshi else None
    if units_per_week < LOW_UNITS or (ratio is not None and ratio < LOW_RATIO):
        level = "low"
    elif units_per_week >= HIGH_UNITS and (ratio is None or ratio >= HIGH_RATIO):
        level = "high"
    else:
        level = "moderate"
    return {
        "level": level,
        "ratio": ratio and round(ratio, 3),
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": round(weeks * 7, 1)},
        "tcgplayer": {**tcg, "units_per_week": round(units_per_week, 1)},
        "kalshi_volume": round(kalshi, 2),
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
                    "variant": match.get("variant"),
                    "market_prices": match.get("tcgplayer_market_prices"),
                    "price_gap": match.get("price_gap"),
                    "matched_by": match.get("matched_by"),
                },
                "sales": weekly_sales(sales_path(name), match.get("variant")),
            }
        events[event_ticker]["markets"].append({
            "ticker": m["ticker"],
            "strike": float(strike),
            "yes_price": m["yes_price"],
            "no_price": m["no_price"],
            "volume": m["volume"],
            "open_time": m["open_time"],
            "close_time": m["close_time"],
        })

    for event in events.values():
        event["kalshi_volume"] = round(sum(m["volume"] for m in event["markets"]), 2)
        event["sales_volume"] = sales_level(event["sales"], event["markets"])

    with open(OVERLAY_FILE, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "events": events,
        }, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(events)} events to {OVERLAY_FILE}")


if __name__ == "__main__":
    main()
