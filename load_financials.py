
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from chart_of_accounts import YF_MAP

DB_PATH = "data/red_shift.db"
SYMBOL, YF_TICKER = "ZEEL", "ZEEL.NS"


def find_value(statements, candidates, year):
    """First candidate (statement, label) with a non-NaN value for `year`."""
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


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""INSERT OR IGNORE INTO COMPANY (symbol, name, sector, is_financial)
                   VALUES (?, 'Zee Entertainment Enterprises Ltd', 'Media & Entertainment', 0)""", (SYMBOL,))
    conn.commit()
    company_id = cur.execute("SELECT company_id FROM COMPANY WHERE symbol = ?", (SYMBOL,)).fetchone()[0]

    t = yf.Ticker(YF_TICKER)
    statements = {"income": t.financials, "balance": t.balance_sheet, "cashflow": t.cashflow}
    for name, df in statements.items():
        print(f"[{name}] labels available: {len(df.index)}   years: {sorted({c.year for c in df.columns})}")

    years = sorted({c.year for df in statements.values() for c in df.columns})
    now_ts = datetime.now(timezone.utc).isoformat()
    saved, coverage = 0, {}

    for item, candidates in YF_MAP.items():
        coverage[item] = {}
        for year in years:
            value, label = find_value(statements, candidates, year)
            coverage[item][year] = label
            if value is None:
                continue
            cur.execute("""INSERT OR REPLACE INTO FINANCIAL_FACT
                           (company_id, fiscal_year, period_type, line_item, value, source, retrieved_at)
                           VALUES (?, ?, 'annual', ?, ?, 'YFINANCE', ?)""",
                        (company_id, year, item, value, now_ts))
            saved += 1
    conn.commit()
    conn.close()

    print(f"\nCOVERAGE ({saved} facts saved)   '-' = not found for that year")
    print(f"{'line item':<22}" + "".join(f"{y:>8}" for y in years) + "   matched label")
    for item, by_year in coverage.items():
        marks = "".join(f"{'ok' if by_year[y] else '-':>8}" for y in years)
        used = next((l for l in by_year.values() if l), "NOT FOUND in any candidate")
        print(f"{item:<22}{marks}   {used}")


if __name__ == "__main__":
    main()