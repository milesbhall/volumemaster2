"""File locations shared by every pipeline step."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

KALSHI_FILE = DATA_DIR / "kalshi_pokemon_data.json"  # step 1 output
CATALOG_CACHE = DATA_DIR / "tcgcsv_catalog.json"     # TCGplayer Pokémon catalog, refreshed daily
ID_MAP_PATH = DATA_DIR / "tcgplayer_ids.json"        # step 2 output: Kalshi name -> TCGplayer product ID
SALES_DIR = DATA_DIR / "sales"                       # step 3 output: one file per product

APIFY_TOKEN_FILE = ROOT / ".apify_token"
