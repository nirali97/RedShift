import sqlite3
import pandas as pd

db_path = "data/red_shift.db"
conn = sqlite3.connect(db_path)

# Let's inspect the facts we loaded into FINANCIAL_FACT
query = """
SELECT fiscal_year, line_item, value, source
FROM FINANCIAL_FACT
WHERE company_id = 1
ORDER BY fiscal_year DESC, line_item ASC;
"""

df = pd.read_sql_query(query, conn)
print("=== Currently Loaded Financial Facts in VS Code ===")
print(df.head(10))

# Next, we simulate the divergence formula from Section 5.3 of your documentation:
# Delta Trade Receivables = (Consolidated TR - Standalone TR) / Standalone TR
# Delta Revenue = (Consolidated Rev - Standalone Rev) / Standalone Rev

def compute_divergence(standalone_val, consolidated_val, metric_name):
    """
    Computes delta percentage between consolidated and standalone line items.
    Flags an anomaly if delta exceeds the threshold defined in SDS Section 5.3.
    """
    if standalone_val is None or standalone_val == 0:
        return None
    
    delta_pct = ((consolidated_val - standalone_val) / standalone_val) * 100
    
    # Thresholds from Technical Doc Section 5.3:
    # > 20% warrants investigation, > 50% is flagged as High severity
    severity = "SAFE"
    if delta_pct > 50:
        severity = "HIGH RED FLAG (Stress concentrated in subsidiaries)"
    elif delta_pct > 20:
        severity = "MEDIUM WARNING (Warrants investigation)"
        
    return delta_pct, severity

print("\n=== Testing Divergence Signal (Tech Docs §5.3) ===")
# Example scenario: Standalone Receivables = 100 Cr, Consolidated Receivables = 175 Cr
delta, alert = compute_divergence(standalone_val=100.0, consolidated_val=175.0, metric_name="Receivables")
print(f"Trade Receivables Delta: {delta:.2f}% -> Status: {alert}")

conn.close()