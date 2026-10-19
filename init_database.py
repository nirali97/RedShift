import sqlite3
import os

# Ensure the data directory exists
os.makedirs("data", exist_ok=True)

db_path = "data/red_shift.db"

# Connect to SQLite (creates the file if it doesn't exist yet)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Create the COMPANY table (SDS Table 6)
cursor.execute("""
CREATE TABLE IF NOT EXISTS COMPANY (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT(20) NOT NULL UNIQUE,
    name TEXT(200) NOT NULL,
    sector TEXT(80) NOT NULL,
    is_financial INTEGER NOT NULL DEFAULT 0
);
""")

# 2. Create the FINANCIAL_FACT table (SDS Table 7)
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

# 3. Create the SCORE_RUN table (SDS Table 8)
cursor.execute("""
CREATE TABLE IF NOT EXISTS SCORE_RUN (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    run_ts TEXT NOT NULL,
    status TEXT(12) NOT NULL,
    m_score REAL,
    z_score REAL,
    f_score INTEGER,
    composite_score REAL,
    severity_band TEXT(12),
    model_version TEXT NOT NULL,
    FOREIGN KEY (company_id) REFERENCES COMPANY(company_id)
);
""")

# 4. Create the RED_FLAG table (SDS Table 9)
cursor.execute("""
CREATE TABLE IF NOT EXISTS RED_FLAG (
    flag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    category TEXT(30) NOT NULL,
    flag_type TEXT(60) NOT NULL,
    severity TEXT(10) NOT NULL,
    explanation TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES SCORE_RUN(run_id)
);
""")

# 5. Create the QUAL_FINDING table (SDS Table 10)
cursor.execute("""
CREATE TABLE IF NOT EXISTS QUAL_FINDING (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    theme TEXT(60) NOT NULL,
    severity TEXT(10) NOT NULL,
    finding_text TEXT NOT NULL,
    quotation TEXT NOT NULL,
    verification_status TEXT(20) NOT NULL,
    FOREIGN KEY (run_id) REFERENCES SCORE_RUN(run_id)
);
""")

conn.commit()
conn.close()

print(f"All database tables initialized successfully at: {db_path}")