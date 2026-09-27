# volumemaster2

This is going to be a great hack.

A Firefox extension that shows TCGplayer sales volume on top of Kalshi's Pokémon price markets, fed by a daily data pipeline.

## Data pipeline

```
python3 run_pipeline.py
```

Runs four steps in order (code in `pipeline/`, output in `data/`):

1. `KalshiData.py` – active Kalshi Pokémon price markets → `data/kalshi_pokemon_data.json`
2. `TCGCSV.py` – matches each product to a TCGplayer ID and confirms it by price → `data/tcgplayer_ids.json`
3. `Apify.py` – TCGplayer weekly sales volume per product, refreshed weekly → `data/sales/`
4. `Summary.py` – combines everything into `data/overlay.json`, which the extension reads

Run a single step with e.g. `python3 -m pipeline.TCGCSV`. Apify needs a token in `APIFY_TOKEN` or `.apify_token`.

### When Kalshi's markets change

Nothing is hardcoded to particular cards, products or months, so each run follows whatever Kalshi currently lists:

- **New series** are found by their Pokémon tag or title, in any Kalshi category. Only price markets ("price of the <product> on <platform>") are kept.
- **New products** are matched to TCGplayer automatically: by exact name, or by closest price when a name fits several printings. Matches are saved in `data/tcgplayer_ids.json` and reused.
- **New months** reuse each product's saved match. Sales are refetched once the new market opens, and the comparison window restarts at the new opening time.
- **Closed markets** drop out of `data/overlay.json` and the extension once they're no longer active.

To override a match, set its `product_id` (and optionally `variant`, the printing) in `data/tcgplayer_ids.json`. Pull first, since the scheduled job commits to that file. Every run prints how far each match's TCGplayer price is from Kalshi's and flags gaps over 30%.

Apify cost grows with the number of active products (about $0.10 per product per week).

## Scheduled job

`.github/workflows/pipeline.yml` runs the pipeline daily at 21:00 UTC on GitHub Actions and commits the updated `data/` folder. It can also be started by hand from the repo's **Actions** tab (**Data pipeline → Run workflow**).

It needs the Apify token as a repository secret named `APIFY_TOKEN` (**Settings → Secrets and variables → Actions → New repository secret**).

## Firefox extension

The extension in `extension/` loads `data/overlay.json` from this repo on GitHub and shows a panel on Kalshi's Pokémon page (https://kalshi.com/category/culture/pok-mon). The panel opens minimized on an overview of every active market; click a row to open that market.

To load it: open `about:debugging#/runtime/this-firefox`, click **Load Temporary Add-on…**, and pick `extension/manifest.json`. Temporary add-ons are removed when Firefox restarts; to keep it installed, sign it as an unlisted add-on on addons.mozilla.org.
