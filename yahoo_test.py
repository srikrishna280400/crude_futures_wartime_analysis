import yfinance as yf
import pandas as pd

SYMBOLS = {
    "WTI": "CL=F",
    "BRENT": "BZ=F",
}

def fetch_and_report(name: str, symbol: str):
    print(f"\n=== {name} | {symbol} ===")

    ticker = yf.Ticker(symbol)

    daily = ticker.history(start="2026-03-01", end="2026-05-09", interval="1d", auto_adjust=False)
    print("Daily rows:", len(daily))
    if not daily.empty:
        print(daily.tail(5).to_string())

    intraday = ticker.history(period="5d", interval="1m", auto_adjust=False)
    print("\n1m rows:", len(intraday))
    if not intraday.empty:
        print(intraday.tail(5).to_string())

    print("\nInfo test complete.")

for name, symbol in SYMBOLS.items():
    fetch_and_report(name, symbol)