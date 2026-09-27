"""Step 2: match each active Kalshi product to a TCGplayer product ID, confirmed by price.

Uses TCGCSV (free, no key), which mirrors TCGplayer's catalog and current
market prices. A Kalshi name matching exactly one TCGplayer product is used
as-is. A bare card name that fits many printings is matched to the one whose
market price is closest to the Kalshi strike, since Kalshi sets strikes near
the current price.

Every run re-checks each ID against today's TCGplayer price and warns when it
is far from Kalshi's. It also records the printing ("variant", e.g. Holofoil or
Reverse Holofoil) whose price is closest to Kalshi's, so sales can be counted
for that printing only. IDs are saved in data/tcgplayer_ids.json; paste a
different product_id or variant there to override a match, and it will be kept.
"""

import json
import re
import time

import requests

from .config import CATALOG_CACHE, ID_MAP_PATH
from .KalshiData import active_products

TCGCSV_URL = "https://tcgcsv.com/tcgplayer/3"  # categoryId 3 = Pokémon
TCGCSV_HEADERS = {"User-Agent": "volumemaster2/0.1"}
REFRESH_SECONDS = 86400
WARN_GAP = 0.30  # flag matches whose TCGplayer price is this far from Kalshi's


def normalize(name):
    name = name.lower().replace("é", "e")
    return " ".join(re.findall(r"[a-z0-9]+", name))


def load_catalog():
    """All Pokémon products with market prices, from TCGCSV (cached for a day)."""
    if CATALOG_CACHE.exists() and time.time() - CATALOG_CACHE.stat().st_mtime < REFRESH_SECONDS:
        with open(CATALOG_CACHE) as f:
            catalog = json.load(f)
        if catalog and "variant_prices" in catalog[0]:  # older caches lack per-printing prices
            return catalog

    print("Downloading TCGplayer Pokémon catalog from TCGCSV (takes a minute or two)...")
    session = requests.Session()
    session.headers.update(TCGCSV_HEADERS)
    catalog = []
    for group in session.get(f"{TCGCSV_URL}/groups", timeout=30).json()["results"]:
        gid = group["groupId"]
        products = session.get(f"{TCGCSV_URL}/{gid}/products", timeout=30).json()["results"]
        time.sleep(0.1)
        prices = session.get(f"{TCGCSV_URL}/{gid}/prices", timeout=30).json()["results"]
        time.sleep(0.1)
        market = {}  # productId -> {printing: market price}
        for p in prices:
            if p.get("marketPrice") is not None:
                market.setdefault(p["productId"], {})[p["subTypeName"]] = p["marketPrice"]
        for p in products:
            variant_prices = market.get(p["productId"], {})
            catalog.append({
                "product_id": p["productId"],
                "name": p["name"],
                "set": group["name"],
                "url": p["url"],
                "market_prices": list(variant_prices.values()),
                "variant_prices": variant_prices,
            })

    CATALOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_CACHE, "w") as f:
        json.dump(catalog, f)
    return catalog


def base_name(product_name):
    """Card name without its number or note: "<Name> - 083/112" or "<Name> (Promo)" -> "<name>"."""
    return normalize(re.split(r" - | \(", product_name)[0])


def price_gap(product, price):
    """Relative gap between the Kalshi strike and the product's closest TCGplayer market price."""
    if not product["market_prices"]:
        return None
    return min(abs(mp - price) for mp in product["market_prices"]) / price


def closest_variant(product, price):
    """The printing (e.g. "Reverse Holofoil") whose market price is closest to the Kalshi strike."""
    variants = product["variant_prices"]
    return min(variants, key=lambda v: abs(variants[v] - price)) if variants else None


def match_product(name, price, catalog):
    """Return (product, other candidates, how it was matched)."""
    exact = [p for p in catalog if normalize(p["name"]) == normalize(name)]
    if len(exact) == 1:
        return exact[0], [], "exact name"

    pool = [p for p in catalog if base_name(p["name"]) == normalize(name)]
    if not pool:
        words = set(normalize(name).split())
        pool = [p for p in catalog if words <= set(normalize(p["name"]).split())]
    candidates = sorted((p for p in pool if p["market_prices"]), key=lambda p: price_gap(p, price))[:8]
    if not candidates:
        return None, [], "no match"
    return candidates[0], candidates[1:], "closest price"


def main(products=None):
    """Return {Kalshi product name: TCGplayer product ID or None} for the active products."""
    products = products or active_products()
    id_map = {}
    if ID_MAP_PATH.exists():
        with open(ID_MAP_PATH) as f:
            id_map = json.load(f)

    catalog = load_catalog()
    by_id = {p["product_id"]: p for p in catalog}

    for name, price in products.items():
        entry = id_map.get(name, {})
        if entry.get("product_id") is None:
            product, others, how = match_product(name, price, catalog)
            entry = {"product_id": product and product["product_id"], "matched_by": how}
            if others:
                entry["other_candidates"] = others

        # Confirm the ID against today's prices on both sides.
        product = by_id.get(entry["product_id"])
        entry["kalshi_price"] = price
        if product:
            gap = price_gap(product, price)
            if entry.get("variant") not in product["variant_prices"]:
                entry["variant"] = closest_variant(product, price)
            entry.update({
                "tcgplayer_name": product["name"],
                "set": product["set"],
                "tcgplayer_market_prices": product["market_prices"],
                "price_gap": None if gap is None else f"{gap:.0%}",
            })
            label = f"{product['name']} ({product['set']}, {entry['variant'] or 'no printing'})"
            if gap is None:
                print(f"  [warn] {name}: {label} has no TCGplayer market price to confirm against")
            elif gap > WARN_GAP:
                print(f"  [warn] {name}: {label} is {gap:.0%} from Kalshi's ${price}; check {ID_MAP_PATH.name}")
            else:
                print(f"{name}: {label}, {gap:.0%} from Kalshi's ${price}")
        elif entry["product_id"] is not None:
            print(f"  [warn] {name}: product_id {entry['product_id']} is not in the TCGplayer catalog")
        else:
            print(f"  [warn] {name}: no TCGplayer match found")
        id_map[name] = entry

    with open(ID_MAP_PATH, "w") as f:
        json.dump(id_map, f, indent=2, ensure_ascii=False)
    return {name: id_map[name]["product_id"] for name in products}


if __name__ == "__main__":
    main()
