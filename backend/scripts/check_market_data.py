"""Manually verify Yahoo Finance daily bars for a representative NSE universe."""

from app.integrations.stocks.yfinance_provider import YFinanceProvider


SYMBOLS = ["RELIANCE", "HDFCBANK", "TCS", "ICICIBANK", "BHARTIARTL", "INFY", "LT", "ITC"]


def main() -> None:
    provider = YFinanceProvider()
    successes = 0
    for symbol in SYMBOLS:
        try:
            bars = provider.fetch_history(f"{symbol}.NS", "5d")
            latest = bars[-1] if bars else None
            if latest:
                successes += 1
                print(f"{symbol}: OK close={latest['close']:.2f} volume={latest['volume']} as_of={latest['date']}")
            else:
                print(f"{symbol}: UNAVAILABLE (no daily bars returned)")
        except Exception as exc:
            print(f"{symbol}: ERROR {str(exc)[:180]}")
    print(f"Result: {successes}/{len(SYMBOLS)} tickers returned daily data")


if __name__ == "__main__":
    main()
