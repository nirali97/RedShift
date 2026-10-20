import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

DB_PATH = "data/red_shift.db"
STOCK_CSV = "data/ZEEL.NS_prices.csv"
BENCHMARK_CSV = "data/NIFTY50_benchmark.csv"

def load_clean_price_csv(file_path):
    """
    Reads yfinance multi-header CSV, flattens columns, 
    and converts dates and prices to numeric types.
    """
    df = pd.read_csv(file_path, header=[0, 1], index_col=0)
    df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index, errors='coerce')
    df = df[df.index.notnull()]
    
    for col in ["Close", "Volume", "Open", "High", "Low"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    return df

def run_market_analyst(company_id=1, symbol="ZEEL"):
    print(f"\n--- Running Market Analyst Agent for {symbol} ---")
    
    # 1. Load and clean price CSVs
    try:
        stock_df = load_clean_price_csv(STOCK_CSV)
        bench_df = load_clean_price_csv(BENCHMARK_CSV)
    except FileNotFoundError:
        print("Price files missing. Run fetch_prices.py first.")
        return

    # Clean rows missing Close or Volume
    stock_df = stock_df.dropna(subset=["Close", "Volume"])
    bench_df = bench_df.dropna(subset=["Close"])

    # 2. Abnormal Volume Detection (FR-38: volume > 3x trailing 90-day median)
    stock_df["Median_Vol_90"] = stock_df["Volume"].rolling(window=90, min_periods=30).median()
    abnormal_vol_mask = stock_df["Volume"] > (3.0 * stock_df["Median_Vol_90"])
    abnormal_vol_dates = stock_df[abnormal_vol_mask].index

    print(f"Detected {len(abnormal_vol_dates)} abnormal volume spike trading days.")

    # 3. 12-Month Return Calculation (FR-36, FR-37)
    trading_days_1y = 252
    if len(stock_df) >= trading_days_1y and len(bench_df) >= trading_days_1y:
        stock_start = float(stock_df["Close"].iloc[-trading_days_1y])
        stock_end = float(stock_df["Close"].iloc[-1])
        stock_ret_12m = ((stock_end - stock_start) / stock_start) * 100

        bench_start = float(bench_df["Close"].iloc[-trading_days_1y])
        bench_end = float(bench_df["Close"].iloc[-1])
        bench_ret_12m = ((bench_end - bench_start) / bench_start) * 100

        relative_ret_12m = stock_ret_12m - bench_ret_12m
        print(f"12M Stock Return      : {stock_ret_12m:.2f}%")
        print(f"12M Benchmark Return  : {bench_ret_12m:.2f}%")
        print(f"12M Relative Return   : {relative_ret_12m:.2f}%")
    else:
        stock_ret_12m, bench_ret_12m, relative_ret_12m = None, None, None
        print("FR-42: Insufficient price history for complete 12M calculation.")

    # 4. Check for Divergence Red Flag (FR-39) and Record Findings
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
    SELECT fiscal_year, value FROM FINANCIAL_FACT 
    WHERE company_id = ? AND line_item = 'sales' 
    ORDER BY fiscal_year DESC LIMIT 2;
    """
    sales_data = pd.read_sql_query(query, conn, params=(company_id,))

    cursor.execute("SELECT run_id FROM SCORE_RUN WHERE company_id = ? ORDER BY run_id DESC LIMIT 1;", (company_id,))
    row = cursor.fetchone()
    run_id = row[0] if row else None

    if run_id and len(sales_data) == 2 and relative_ret_12m is not None:
        sales_curr = sales_data.iloc[0]["value"]
        sales_prior = sales_data.iloc[1]["value"]
        revenue_grew = sales_curr > sales_prior

        if revenue_grew and relative_ret_12m < -15.0:
            print("ALERT: Fundamental vs Market Divergence detected!")
            cursor.execute("""
            INSERT INTO RED_FLAG (run_id, category, flag_type, severity, explanation, evidence_ref)
            VALUES (?, 'Market-Behaviour', 'Books vs Market Divergence', 'High',
                    'Reported revenue expanded year-over-year while stock experienced sustained underperformance relative to NIFTY50.',
                    ?)
            """, (run_id, f"Sales grew from {sales_prior} to {sales_curr}, but 12M relative return fell to {relative_ret_12m:.2f}%"))

    if run_id and len(abnormal_vol_dates) > 0:
        recent_spikes = [str(d.date()) for d in abnormal_vol_dates[-5:]]
        cursor.execute("""
        INSERT INTO RED_FLAG (run_id, category, flag_type, severity, explanation, evidence_ref)
        VALUES (?, 'Market-Behaviour', 'Abnormal Volume Activity', 'Medium',
                'Trading volume exceeded 3x trailing 90-day median volume across recent sessions.',
                ?)
        """, (run_id, f"Abnormal volume dates observed: {', '.join(recent_spikes)}"))

    conn.commit()
    conn.close()
    print("Market Analyst Agent execution completed and flags recorded.\n")

if __name__ == "__main__":
    run_market_analyst(company_id=1, symbol="ZEEL")