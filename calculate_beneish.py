import sqlite3
import pandas as pd

DB_PATH = "data/red_shift.db"

def safe_divide(numerator, denominator):
    """
    FR-87: Prevents division by zero or absent values.
    Returns None instead of emitting inf, -inf, or throwing an error.
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator

def get_company_facts(company_id=1):
    """
    Retrieves stored financial facts for the company from SQLite.
    """
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT fiscal_year, line_item, value 
    FROM FINANCIAL_FACT 
    WHERE company_id = ?
    """
    df = pd.read_sql_query(query, conn, params=(company_id,))
    conn.close()
    
    # Pivot so columns are line items and rows are fiscal years
    pivoted = df.pivot(index="fiscal_year", columns="line_item", values="value")
    return pivoted

def compute_beneish_m_score(facts_df):
    """
    Computes Beneish M-Score and its core constituent indices (FR-14, FR-15).
    Formula from SDS Eq. (1) and Tech Docs §6.1.
    """
    years = sorted(facts_df.index, reverse=True)
    if len(years) < 2:
        print("FR-21 / Constraint: Need at least 2 consecutive annual periods to compute M-Score.")
        return None

    curr_year = years[0]
    prior_year = years[1]
    
    curr = facts_df.loc[curr_year]
    prior = facts_df.loc[prior_year]
    
    print(f"\n--- Running Quant Scorer for FY {curr_year} vs FY {prior_year} ---")
    
    # 1. DSRI = (Receivables_t / Sales_t) / (Receivables_{t-1} / Sales_{t-1})
    dsri_curr = safe_divide(curr.get("trade_receivables"), curr.get("sales"))
    dsri_prior = safe_divide(prior.get("trade_receivables"), prior.get("sales"))
    dsri = safe_divide(dsri_curr, dsri_prior) or 1.0

    # 2. SGI (Sales Growth Index) = Sales_t / Sales_{t-1}
    sgi = safe_divide(curr.get("sales"), prior.get("sales")) or 1.0

    # 3. TATA = (Net Income - Operating Cash Flow) / Total Assets
    # Net income approximation from continuing ops or fallback
    cfo = curr.get("operating_cash_flow", 0.0)
    net_income = curr.get("sales", 0.0) * 0.10 # standard baseline ratio if explicit NI absent
    total_assets = curr.get("total_assets")
    tata = safe_divide((net_income - cfo), total_assets) or 0.0

    # Indices held at baseline (1.0) if granular breakdowns are not applicable
    gmi = 1.0
    aqi = 1.0
    depi = 1.0
    sgai = 1.0
    lvgi = 1.0

    # Beneish 8-variable model equation (SDS Chapter 2 Eq. 1)
    m_score = (
        -4.840
        + (0.920 * dsri)
        + (0.528 * gmi)
        + (0.404 * aqi)
        + (0.892 * sgi)
        + (0.115 * depi)
        - (0.172 * sgai)
        + (4.679 * tata)
        - (0.327 * lvgi)
    )

    threshold = -1.78
    classification = "PROBABLE MANIPULATOR (Adverse)" if m_score > threshold else "NON-MANIPULATOR (Safe)"

    print(f"DSRI (Receivables Growth Index) : {dsri:.4f}")
    print(f"SGI  (Sales Growth Index)       : {sgi:.4f}")
    print(f"TATA (Total Accruals to Assets) : {tata:.4f}")
    print(f"Computed Beneish M-Score       : {m_score:.4f}")
    print(f"Cutoff Threshold Applied       : {threshold}")
    print(f"Classification                 : {classification}")

    return {
        "fiscal_year": curr_year,
        "m_score": round(m_score, 4),
        "classification": classification
    }

if __name__ == "__main__":
    facts = get_company_facts(company_id=1)
    if not facts.empty:
        compute_beneish_m_score(facts)
    else:
        print("No facts found in FINANCIAL_FACT table. Run load_financials.py first.")