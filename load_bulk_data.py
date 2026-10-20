import sqlite3
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf
from chart_of_accounts import YF_MAP

DB_PATH = "data/red_shift.db"

# A mix of NIFTY50 companies + Case Studies from team reports
COMPANIES = [
    {"symbol": "ZEEL", "name": "Zee Entertainment", "ticker": "ZEEL.NS", "sector": "Media", "is_financial": 0},
    {"symbol": "RELIANCE", "name": "Reliance Industries", "ticker": "RELIANCE.NS", "sector": "Energy", "is_financial": 0},
    {"symbol": "TCS", "name": "Tata Consultancy Services", "ticker": "TCS.NS", "sector": "IT", "is_financial": 0},
    {"symbol": "INFY", "name": "Infosys", "ticker": "INFY.NS", "sector": "IT", "is_financial": 0},
    {"symbol": "ITC", "name": "ITC Limited", "ticker": "ITC.NS", "sector": "FMCG", "is_financial": 0},
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever", "ticker": "HINDUNILVR.NS", "sector": "FMCG", "is_financial": 0},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel", "ticker": "BHARTIARTL.NS", "sector": "Telecom", "is_financial": 0},
    {"symbol": "LT", "name": "Larsen & Toubro", "ticker": "LT.NS", "sector": "Infrastructure", "is_financial": 0},
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "ticker": "HDFCBANK.NS", "sector": "Banking", "is_financial": 1},
    {"symbol": "SBIN", "name": "State Bank of India", "ticker": "SBIN.NS", "sector": "Banking", "is_financial": 1},
    {"symbol": "YESBANK", "name": "Yes Bank", "ticker": "YESBANK.NS", "sector": "Banking", "is_financial": 1},
    {"symbol": "ADANIENT", "name": "Adani Enterprises", "ticker": "ADANIENT.NS", "sector": "Conglomerate", "is_financial": 0},
    {"symbol": "TATAMOTORS", "name": "Tata Motors", "ticker": "TATAMOTORS.NS", "sector": "Auto", "is_financial": 0},
    {"symbol": "WIPRO", "name": "Wipro", "ticker": "WIPRO.NS", "sector": "IT", "is_financial": 0},
    {"symbol": "MARUTI", "name": "Maruti Suzuki", "ticker": "MARUTI.NS", "sector": "Auto", "is_financial": 0},
    {"symbol": "ASIANPAINT", "name": "Asian Paints", "ticker": "ASIANPAINT.NS", "sector": "Materials", "is_financial": 0},
    {"symbol": "SUNPHARMA", "name": "Sun Pharma", "ticker": "SUNPHARMA.NS", "sector": "Pharma", "is_financial": 0},
    {"symbol": "TITAN", "name": "Titan", "ticker": "TITAN.NS", "sector": "Consumer", "is_financial": 0},
    {"symbol": "HCLTECH", "name": "HCL Tech", "ticker": "HCLTECH.NS", "sector": "IT", "is_financial": 0},
    {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto", "ticker": "BAJAJ-AUTO.NS", "sector": "Auto", "is_financial": 0},
    {"symbol": "JSWSTEEL", "name": "JSW Steel", "ticker": "JSWSTEEL.NS", "sector": "Metals", "is_financial": 0},
    {"symbol": "TATASTEEL", "name": "Tata Steel", "ticker": "TATASTEEL.NS", "sector": "Metals", "is_financial": 0},
    {"symbol": "ULTRACEMCO", "name": "UltraTech", "ticker": "ULTRACEMCO.NS", "sector": "Materials", "is_financial": 0},
    {"symbol": "NTPC", "name": "NTPC", "ticker": "NTPC.NS", "sector": "Utilities", "is_financial": 0},
    {"symbol": "POWERGRID", "name": "Power Grid", "ticker": "POWERGRID.NS", "sector": "Utilities", "is_financial": 0},
    {"symbol": "ONGC", "name": "ONGC", "ticker": "ONGC.NS", "sector": "Energy", "is_financial": 0}
]

def find_value(statements, candidates, year):
    for stmt, label in candidates:
        df = statements[stmt]
        if df is None or label not in df.index:
            continue
        for col in df.columns:
            if col.year == year:
                v = df.loc[label, col]
                if pd.notna(v):
                    return float(v), label
    return None, None

def load_company(conn, cursor, comp_data):
    symbol = comp_data["symbol"]
    ticker = comp_data["ticker"]
    
    print(f"\nFetching data for {symbol} ({ticker})...")
    
    # 1. Insert/Update Company in the COMPANY table
    cursor.execute("""
        INSERT OR IGNORE INTO COMPANY (symbol, name, sector, is_financial)
        VALUES (?, ?, ?, ?)
    """, (symbol, comp_data["name"], comp_data["sector"], comp_data["is_financial"]))
    conn.commit()
    
    # Get company_id
    cursor.execute("SELECT company_id FROM COMPANY WHERE symbol = ?", (symbol,))
    company_id = cursor.fetchone()[0]

    # 2. Fetch from yfinance
    try:
        t = yf.Ticker(ticker)
        statements = {"income": t.financials, "balance": t.balance_sheet, "cashflow": t.cashflow}
        years = sorted({c.year for df in statements.values() if df is not None for c in df.columns})
        
        if not years:
            print(f"  -> No data found for {symbol}. Skipping.")
            return
            
        now_ts = datetime.now(timezone.utc).isoformat()
        saved = 0

        # 3. Map the line items using YF_MAP from chart_of_accounts.py
        for item, candidates in YF_MAP.items():
            for year in years:
                value, label = find_value(statements, candidates, year)
                if value is None:
                    continue
                
                cursor.execute("""
                    INSERT OR REPLACE INTO FINANCIAL_FACT
                    (company_id, fiscal_year, period_type, line_item, value, source, retrieved_at)
                    VALUES (?, ?, 'annual', ?, ?, 'YFINANCE', ?)
                """, (company_id, year, item, value, now_ts))
                saved += 1
        
        conn.commit()
        print(f"  -> Successfully saved {saved} facts for {symbol} across years {years[0]}-{years[-1]}")
        
    except Exception as e:
        print(f"  -> Error loading {symbol}: {e}")

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for comp in COMPANIES:
        load_company(conn, cursor, comp)
        
    conn.close()
    print("\nBulk data loading complete!")

if __name__ == "__main__":
    main()