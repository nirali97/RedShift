import sqlite3
import os

# Ensure the data folder exists
os.makedirs("data", exist_ok=True)

db_path = "data/red_shift.db"

# Connect to SQLite (creates the file if it doesn't exist yet)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Create the COMPANY table (from SDS Table 6)
cursor.execute("""
CREATE TABLE IF NOT EXISTS COMPANY (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT(20) NOT NULL UNIQUE,
    name TEXT(200) NOT NULL,
    sector TEXT(80) NOT NULL,
    is_financial INTEGER NOT NULL DEFAULT 0
);
""")

# 2. Create the FINANCIAL_FACT table (from SDS Table 7)
cursor.execute("""
CREATE TABLE IF NOT EXISTS FINANCIAL_FACT (
    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    period_type TEXT(10) NOT NULL,
    line_item TEXT(60) NOT NULL,
    value REAL,
    source TEXT(40) NOT NULL,
    retrieved_at TEXT NOT NULL,
    FOREIGN KEY (company_id) REFERENCES COMPANY(company_id),
    UNIQUE(company_id, fiscal_year, period_type, line_item)
);
""")

conn.commit()
conn.close()

print(f"Database initialized successfully at: {db_path}")