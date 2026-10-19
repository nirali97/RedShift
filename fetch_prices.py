import os
import yfinance as yf

# Create a data directory to store our downloads locally (FR-9 reproducibility requirement)
os.makedirs("data", exist_ok=True)

# NSE stock symbols use the '.NS' suffix in yfinance
# Example: ZEEL.NS (Zee Entertainment), TATAMOTORS.NS, RELIANCE.NS
stock_symbol = "ZEEL.NS"
benchmark_symbol = "^NSEI"  # Nifty 50 Index

print(f"Downloading trading data for {stock_symbol} and {benchmark_symbol}...")

# Download daily OHLCV data from Jan 1, 2022 to current date
stock_data = yf.download(stock_symbol, start="2022-01-01")
benchmark_data = yf.download(benchmark_symbol, start="2022-01-01")

# Save directly to CSV inside the data folder
stock_file = f"data/{stock_symbol}_prices.csv"
bench_file = "data/NIFTY50_benchmark.csv"

stock_data.to_csv(stock_file)
benchmark_data.to_csv(bench_file)

print(f"Successfully saved {stock_symbol} prices to: {stock_file}")
print(f"Successfully saved NIFTY50 index to: {bench_file}")