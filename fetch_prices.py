import yfinance as yf
import pandas as pd
import os

TICKERS = [
    "ZEEL", "RELIANCE", "TCS", "INFY", "ITC", "HINDUNILVR", "BHARTIARTL", "LT", 
    "HDFCBANK", "SBIN", "YESBANK", "ADANIENT", "TATAMOTORS", "WIPRO", "MARUTI", 
    "ASIANPAINT", "SUNPHARMA", "TITAN", "HCLTECH", "BAJAJ-AUTO", "JSWSTEEL", 
    "TATASTEEL", "ULTRACEMCO", "NTPC", "POWERGRID", "ONGC"
]

os.makedirs("data", exist_ok=True)

for symbol in TICKERS:
    ticker = f"{symbol}.NS"
    print(f"Fetching prices for {ticker}...")
    try:
        data = yf.download(ticker, period="1y")
        if not data.empty:
            data.to_csv(f"data/{ticker}_prices.csv")
    except Exception as e:
        print(f"Failed to fetch {ticker}: {e}")