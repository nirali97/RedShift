import sqlite3
from datetime import datetime
import yfinance as yf

db_path = "data/red_shift.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Register Zee Entertainment (ZEEL) as our test company
cursor.execute("""
INSERT OR IGNORE INTO COMPANY (symbol, name, sector, is_financial)
VALUES ('ZEEL', 'Zee Entertainment Enterprises Ltd', 'Media & Entertainment', 0);
""")
conn.commit()

# Retrieve the assigned company_id
cursor.execute("SELECT company_id FROM COMPANY WHERE symbol = 'ZEEL';")
company_id = cursor.fetchone()[0]

print(f"Acquiring annual financial statement facts for company_id: {company_id} (ZEEL)...")

# We use yfinance financial statements as our standard multi-year feed
ticker = yf.Ticker("ZEEL.NS")
income_stmt = ticker.financials      # Profit & Loss
balance_sheet = ticker.balance_sheet # Balance Sheet
cashflow = ticker.cashflow           # Cash Flow

now_ts = datetime.utcnow().isoformat()
records_saved = 0

def store_fact(year, line_item, value, source="YFINANCE"):
    global records_saved
    if value is not None and str(value) != 'nan':
        cursor.execute("""
        INSERT OR REPLACE INTO FINANCIAL_FACT 
        (company_id, fiscal_year, period_type, line_item, value, source, retrieved_at)
        VALUES (?, ?, 'annual', ?, ?, ?, ?)
        """, (company_id, year, line_item, float(value), source, now_ts))
        records_saved += 1

# Extract key line items across all available financial years
for date_col in income_stmt.columns:
    year = date_col.year
    
    # 1. Sales / Revenue
    if "Total Revenue" in income_stmt.index:
        store_fact(year, "sales", income_stmt.loc["Total Revenue", date_col])
        
    # 2. Operating Cash Flow (Crucial for Beneish TATA index)
    if "Operating Cash Flow" in cashflow.index:
        store_fact(year, "operating_cash_flow", cashflow.loc["Operating Cash Flow", date_col])
        
    # 3. Total Assets
    if "Total Assets" in balance_sheet.index:
        store_fact(year, "total_assets", balance_sheet.loc["Total Assets", date_col])
        
    # 4. Receivables (Crucial for Beneish DSRI index)
    if "Receivables" in balance_sheet.index:
        store_fact(year, "trade_receivables", balance_sheet.loc["Receivables", date_col])
        
    # 5. Current Assets & Current Liabilities (For Altman working capital)
    if "Current Assets" in balance_sheet.index:
        store_fact(year, "current_assets", balance_sheet.loc["Current Assets", date_col])
    if "Current Liabilities" in balance_sheet.index:
        store_fact(year, "current_liabilities", balance_sheet.loc["Current Liabilities", date_col])

conn.commit()
conn.close()

print(f"Done! Successfully acquired and loaded {records_saved} financial facts into SQLite.")