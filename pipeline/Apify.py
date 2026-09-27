"""Step 3: TCGplayer sales volume for the active Kalshi products, via Apify.

Runs the Apify actor "scraped/tcgplayer-sales-history" once per product ID
from step 2. The actor returns one item per SKU (condition/printing/language)
with weekly buckets of transactionCount and quantitySold for the past year.

Output: data/sales/<product>.json for each product.

Cost: the actor charges $0.10 per run plus $0.003 per result. Its data is in
weekly buckets, so each product is refreshed at most once a week. New
products, and products whose Kalshi market opened after their last fetch
(e.g. at the start of a new month), are fetched immediately.

The Apify token is read from the APIFY_TOKEN environment variable, or from
the git-ignored .apify_token file in the project root.
"""

import json
import os
import time
from datetime import datetime, timezone

from apify_client import ApifyClient
from apify_client.errors import ApifyApiError, ForbiddenError, UnauthorizedError

from . import KalshiData, TCGCSV
from .config import APIFY_TOKEN_FILE, SALES_DIR

ACTOR_ID = "scraped/tcgplayer-sales-history"
REFRESH_SECONDS = 7 * 86400


def load_token():
    token = os.environ.get("APIFY_TOKEN")
    if not token and APIFY_TOKEN_FILE.exists():
        token = APIFY_TOKEN_FILE.read_text().strip()
    if not token:
        raise SystemExit(f"Set APIFY_TOKEN or put your Apify token in {APIFY_TOKEN_FILE}.")
    return token


def sales_path(name):
    return SALES_DIR / (TCGCSV.normalize(name).replace(" ", "_") + ".json")


def fetched_recently(path, market_opened=None):
    """True if the saved sales are under a week old and newer than the Kalshi market."""
    # Uses the saved fetched_at rather than file mtime, which a git checkout resets.
    if not path.exists():
        return False
    with open(path) as f:
        fetched_at = datetime.fromisoformat(json.load(f)["fetched_at"])
    if market_opened and fetched_at < market_opened:
        return False
    return time.time() - fetched_at.timestamp() < REFRESH_SECONDS


def main(ids=None):
    """Download sales history for {Kalshi product name: TCGplayer product ID}."""
    ids = ids or TCGCSV.main()
    client = ApifyClient(load_token())
    opened = KalshiData.open_times()
    SALES_DIR.mkdir(parents=True, exist_ok=True)

    for name, pid in ids.items():
        if pid is None:
            print(f"{name}: no TCGplayer product ID, skipping")
            continue
        path = sales_path(name)
        if fetched_recently(path, opened.get(name)):
            print(f"{name}: fetched within the last week, skipping")
            continue

        url = f"https://www.tcgplayer.com/product/{pid}"
        try:
            run = client.actor(ACTOR_ID).call(run_input={"url": url}, logger=None)
        except (ForbiddenError, UnauthorizedError) as e:
            raise SystemExit(f"Apify refused the run, so no products were fetched: {e}")
        except ApifyApiError as e:
            print(f"[error] {name}: {e}")
            continue
        if run is None or run.status != "SUCCEEDED":
            print(f"[error] {name}: actor run {getattr(run, 'status', 'failed to start')}")
            continue
        skus = list(client.dataset(run.default_dataset_id).iterate_items())

        with open(path, "w") as f:
            json.dump({
                "product": name,
                "product_id": pid,
                "tcgplayer_url": url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "skus": skus,
            }, f, indent=2, ensure_ascii=False)
        print(f"{name}: saved {len(skus)} SKUs to {path.relative_to(SALES_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
