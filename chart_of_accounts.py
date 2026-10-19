"""
chart_of_accounts.py
Single place for (a) the internal chart of accounts, (b) how source labels map
onto it (FR-7) and (c) the model coefficients / thresholds (NFR-23).
Nothing in features.py hard-codes a coefficient.
"""

# ---------------------------------------------------------------------------
# (a)+(b) internal line-item id -> ordered list of (yfinance statement, label)
# The loader takes the FIRST candidate that has a non-NaN value for that year.
# yfinance labels change between versions, so verify with the coverage report
# that load_financials.py prints.
# ---------------------------------------------------------------------------
YF_MAP = {
    # profit & loss
    "sales":        [("income", "Total Revenue"), ("income", "Operating Revenue")],
    "cogs":         [("income", "Cost Of Revenue"), ("income", "Reconciled Cost Of Revenue")],
    "gross_profit": [("income", "Gross Profit")],
    "sga":          [("income", "Selling General And Administration")],
    "depreciation": [("income", "Reconciled Depreciation"),
                     ("income", "Depreciation And Amortization In Income Statement"),
                     ("cashflow", "Depreciation And Amortization"),
                     ("cashflow", "Depreciation Amortization Depletion")],
    "ebit":         [("income", "EBIT"), ("income", "Operating Income")],
    "net_income":   [("income", "Net Income From Continuing Operation Net Minority Interest"),
                     ("income", "Net Income Continuous Operations"),
                     ("income", "Net Income")],
    # balance sheet
    "total_assets":        [("balance", "Total Assets")],
    "current_assets":      [("balance", "Current Assets")],
    "current_liabilities": [("balance", "Current Liabilities")],
    "trade_receivables":   [("balance", "Accounts Receivable"), ("balance", "Receivables"),
                            ("balance", "Gross Accounts Receivable")],
    "net_ppe":             [("balance", "Net PPE")],
    "retained_earnings":   [("balance", "Retained Earnings")],
    "total_liabilities":   [("balance", "Total Liabilities Net Minority Interest")],
    "long_term_debt":      [("balance", "Long Term Debt"),
                            ("balance", "Long Term Debt And Capital Lease Obligation")],
    "equity":              [("balance", "Stockholders Equity"), ("balance", "Common Stock Equity")],
    "shares_outstanding":  [("balance", "Ordinary Shares Number"), ("balance", "Share Issued")],
    # cash flow
    "operating_cash_flow": [("cashflow", "Operating Cash Flow"),
                            ("cashflow", "Cash Flow From Continuing Operating Activities")],
}

# ---------------------------------------------------------------------------
# (c) model configuration
# ---------------------------------------------------------------------------
BENEISH_COEFFS = {            # SDD Eq. (1)
    "const": -4.840, "DSRI": 0.920, "GMI": 0.528, "AQI": 0.404, "SGI": 0.892,
    "DEPI": 0.115, "SGAI": -0.172, "TATA": 4.679, "LVGI": -0.327,
}
BENEISH_THRESHOLD = -1.78     # FR-16

# Altman variants. The SRS names Z'' but Eq. (4) and the 1.81 / 2.99 cut-offs are
# the ORIGINAL 1968 Z. Both are kept here so the team can decide (FR-18).
#   x4 = "market": market cap / total liabilities   |  "book": book equity / total liabilities
ALTMAN_VARIANTS = {
    "z_original":     {"coeffs": (1.2, 1.4, 3.3, 0.6, 1.0),   "const": 0.0,  "x4": "market", "cutoffs": (1.81, 2.99)},
    "z_double_prime": {"coeffs": (6.56, 3.26, 6.72, 1.05, 0.0), "const": 0.0,  "x4": "book",   "cutoffs": (1.10, 2.60)},
    "z_emerging":     {"coeffs": (6.56, 3.26, 6.72, 1.05, 0.0), "const": 3.25, "x4": "book",   "cutoffs": (4.15, 5.85)},
}
ALTMAN_VARIANT = "z_double_prime"   # <- change here once the team agrees

PIOTROSKI_SIGNALS = [
    "ROA>0", "CFO>0", "dROA>0", "CFO>NI", "dLeverage<0",
    "dCurrentRatio>0", "NoNewShares", "dGrossMargin>0", "dAssetTurnover>0",
]
