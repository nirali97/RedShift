import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "data/red_shift.db"

# Weights from SDS Section 2.2.3 Component 5 and Tech Docs Section 3.2
WEIGHT_QUANT = 0.40       # w1: 40%
WEIGHT_QUAL = 0.35        # w2: 35%
WEIGHT_MARKET = 0.25      # w3: 25%

def run_report_generator(company_id=1, symbol="ZEEL"):
    print("\n=======================================================")
    print(f"   RUNNING REPORT GENERATOR AGENT FOR {symbol}")
    print("=======================================================")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Find the latest screening run
    cursor.execute("""
    SELECT run_id, fiscal_year, m_score, z_score, f_score 
    FROM SCORE_RUN 
    WHERE company_id = ? 
    ORDER BY run_id DESC LIMIT 1;
    """, (company_id,))
    row = cursor.fetchone()

    if not row:
        print("No screening runs found in SCORE_RUN. Execute quant_scorer.py first.")
        conn.close()
        return

    run_id, fiscal_year, m_score, z_score, f_score = row

    # 1. Normalize Quantitative Stream (Q: 0.0 to 1.0 risk level)
    q_penalties = 0.0
    if m_score is not None and m_score > -1.78:
        q_penalties += 0.50
    if z_score is not None and z_score < 1.81:
        q_penalties += 0.30
    elif z_score is not None and z_score <= 2.99:
        q_penalties += 0.15
    if f_score is not None and f_score <= 3:
        q_penalties += 0.20

    q_stream = min(q_penalties, 1.0)

    # 2. Normalize Qualitative Stream (L: 0.0 to 1.0 risk level)
    cursor.execute("""
    SELECT severity FROM QUAL_FINDING 
    WHERE run_id = ? AND verification_status = 'Verified';
    """, (run_id,))
    qual_rows = cursor.fetchall()

    l_penalties = 0.0
    for (sev,) in qual_rows:
        if sev == "High":
            l_penalties += 0.35
        elif sev == "Medium":
            l_penalties += 0.20
        elif sev == "Low":
            l_penalties += 0.10

    l_stream = min(l_penalties, 1.0)

    # 3. Normalize Market Stream (B: 0.0 to 1.0 risk level)
    cursor.execute("""
    SELECT flag_type, severity FROM RED_FLAG 
    WHERE run_id = ? AND category = 'Market-Behaviour';
    """, (run_id,))
    market_flags = cursor.fetchall()

    b_penalties = 0.0
    for ftype, sev in market_flags:
        if "Divergence" in ftype:
            b_penalties += 0.60
        if "Volume" in ftype:
            b_penalties += 0.40

    b_stream = min(b_penalties, 1.0)

    # 4. Compute Normalized Composite Risk Score (0 - 100)
    composite_score = 100.0 * (
        (WEIGHT_QUANT * q_stream) + 
        (WEIGHT_QUAL * l_stream) + 
        (WEIGHT_MARKET * b_stream)
    )
    composite_score = round(composite_score, 2)

    # Assign Severity Band (FR-44)
    if composite_score >= 65.0:
        severity_band = "High Risk"
    elif composite_score >= 35.0:
        severity_band = "Moderate Risk"
    else:
        severity_band = "Low Risk"

    # 5. Persist Composite Score and Severity Band to SCORE_RUN
    cursor.execute("""
    UPDATE SCORE_RUN 
    SET composite_score = ?, severity_band = ?
    WHERE run_id = ?;
    """, (composite_score, severity_band, run_id))

    conn.commit()

    # 6. Print Executive Forensic Summary
    print(f"\n--- SCORECARD BREAKDOWN (Run #{run_id} | FY {fiscal_year}) ---")
    print(f"Quantitative Stream (Weight 40%) : Risk Score = {q_stream * 100:.1f} / 100")
    print(f"Qualitative Stream  (Weight 35%) : Risk Score = {l_stream * 100:.1f} / 100")
    print(f"Market Stream       (Weight 25%) : Risk Score = {b_stream * 100:.1f} / 100")
    print("-------------------------------------------------------")
    print(f"FINAL COMPOSITE RISK SCORE       : {composite_score} / 100")
    print(f"ASSIGNED SEVERITY BAND           : {severity_band.upper()}")
    print("-------------------------------------------------------")

    flags_df = pd.read_sql_query("""
    SELECT category, flag_type, severity, evidence_ref 
    FROM RED_FLAG 
    WHERE run_id = ?;
    """, conn, params=(run_id,))

    print(f"\nTOTAL FLAGS RAISED: {len(flags_df)}")
    for idx, row in flags_df.iterrows():
        print(f"[{row['severity']}] {row['category']} -> {row['flag_type']}")
        print(f"       Evidence: {row['evidence_ref']}")

    conn.close()
    print("\nReport generation completed and stored to SQLite.")

if __name__ == "__main__":
    run_report_generator(company_id=1, symbol="ZEEL")