# volumemaster2

This is going to be a great hack.
## Data pipeline

```
python3 run_pipeline.py
```

Runs three steps in order (code in `pipeline/`, output in `data/`):

1. `KalshiData.py` – active Kalshi Pokémon price markets → `data/kalshi_pokemon_data.json`
2. `TCGCSV.py` – matches each product to a TCGplayer ID and confirms it by price → `data/tcgplayer_ids.json`
3. `Apify.py` – TCGplayer weekly sales volume per product → `data/sales/`

Run a single step with e.g. `python3 -m pipeline.TCGCSV`. Apify needs a token in `APIFY_TOKEN` or `.apify_token`.
