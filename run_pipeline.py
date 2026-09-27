"""Run the whole data pipeline in order. Everything it gathers lands in data/.

  1. KalshiData: find the active Kalshi Pokémon markets
  2. TCGCSV:     match and confirm each product's TCGplayer ID by price
  3. Apify:      download TCGplayer sales volume for those products

Usage: python3 run_pipeline.py
Each step can also be run alone, e.g. python3 -m pipeline.TCGCSV
"""

from pipeline import Apify, KalshiData, TCGCSV


def main():
    print("== 1/3 Kalshi: active markets ==")
    products = KalshiData.main()
    print(f"{len(products)} active products\n")

    print("== 2/3 TCGCSV: TCGplayer product IDs ==")
    ids = TCGCSV.main(products)
    print()

    print("== 3/3 Apify: sales volume ==")
    Apify.main(ids)


if __name__ == "__main__":
    main()
