"""
features.py - RedShift feature layer.

Turns normalised FINANCIAL_FACT rows into the inputs the scorers need:
  * 8 Beneish indices + M-Score          (FR-14, FR-15, FR-16)
  * 5 Altman ratios + Z-Score + zone     (FR-17, FR-18)
  * 9 Piotroski signals + F-Score        (FR-19)

Rules enforced here
  FR-87  every division is guarded; an undefined result is None, never inf/nan.
  FR-89  absent (None) is NOT zero. A genuine 0.0 is used as 0.0.
  FR-21  every score that cannot be computed says which input was missing.
  FR-20  M-Score and Z-Score are suppressed for financial-sector companies.
  FR-25  the Altman variant / thresholds used are returned with the result.
There is deliberately no `x or 1.0` fallback anywhere: a missing input never
turns into a neutral number.
"""
import math
import sqlite3

import pandas as pd

from chart_of_accounts import (
    ALTMAN_VARIANT, ALTMAN_VARIANTS, BENEISH_COEFFS, BENEISH_THRESHOLD,
    PIOTROSKI_SIGNALS,
)

DB_PATH = "data/red_shift.db"


# --------------------------------------------------------------------------
# Basics
# --------------------------------------------------------------------------
def _clean(v):
    """NaN / inf / non-numeric -> None (absent). Real zeros stay 0.0."""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(v) or math.isinf(v)) else v


def safe_div(num, den):
    """FR-87 guarded division."""
    num, den = _clean(num), _clean(den)
    if num is None or den is None or den == 0:
        return None
    return num / den


def derive(facts):
    """Clean a {line_item: value} dict and fill derivable items."""
    f = {k: _clean(v) for k, v in facts.items()}
    if f.get("gross_profit") is None and f.get("sales") is not None and f.get("cogs") is not None:
        f["gross_profit"] = f["sales"] - f["cogs"]
    if f.get("total_liabilities") is None and f.get("total_assets") is not None and f.get("equity") is not None:
        f["total_liabilities"] = f["total_assets"] - f["equity"]
    return f


def _missing(c, p, cur=(), pri=()):
    return ([f"{k} (current year)" for k in cur if c.get(k) is None]
            + [f"{k} (prior year)" for k in pri if p.get(k) is None])


# --------------------------------------------------------------------------
# Beneish M-Score
# --------------------------------------------------------------------------
def _ratio_index(c, p, num, den):
    """(num/den)_t / (num/den)_{t-1}"""
    return safe_div(safe_div(c.get(num), c.get(den)), safe_div(p.get(num), p.get(den)))


def _gross_margin(r):
    return safe_div(r.get("gross_profit"), r.get("sales"))


def _asset_quality(r):          # 1 - (current assets + net PPE) / total assets
    ca, ppe = r.get("current_assets"), r.get("net_ppe")
    if ca is None or ppe is None:
        return None
    s = safe_div(ca + ppe, r.get("total_assets"))
    return None if s is None else 1.0 - s


def _dep_rate(r):               # depreciation / (depreciation + net PPE)
    d, ppe = r.get("depreciation"), r.get("net_ppe")
    if d is None or ppe is None:
        return None
    return safe_div(d, d + ppe)


def _leverage(r):               # (current liabilities + long-term debt) / total assets
    cl, ltd = r.get("current_liabilities"), r.get("long_term_debt")
    if cl is None or ltd is None:
        return None
    return safe_div(cl + ltd, r.get("total_assets"))


# name -> (function, inputs needed in current year, inputs needed in prior year)
INDEX_SPEC = {
    "DSRI": (lambda c, p: _ratio_index(c, p, "trade_receivables", "sales"),
             ["trade_receivables", "sales"], ["trade_receivables", "sales"]),
    "GMI":  (lambda c, p: safe_div(_gross_margin(p), _gross_margin(c)),
             ["gross_profit", "sales"], ["gross_profit", "sales"]),
    "AQI":  (lambda c, p: safe_div(_asset_quality(c), _asset_quality(p)),
             ["current_assets", "net_ppe", "total_assets"], ["current_assets", "net_ppe", "total_assets"]),
    "SGI":  (lambda c, p: safe_div(c.get("sales"), p.get("sales")),
             ["sales"], ["sales"]),
    "DEPI": (lambda c, p: safe_div(_dep_rate(p), _dep_rate(c)),
             ["depreciation", "net_ppe"], ["depreciation", "net_ppe"]),
    "SGAI": (lambda c, p: _ratio_index(c, p, "sga", "sales"),
             ["sga", "sales"], ["sga", "sales"]),
    "TATA": (lambda c, p: safe_div(
                 None if c.get("net_income") is None or c.get("operating_cash_flow") is None
                 else c["net_income"] - c["operating_cash_flow"], c.get("total_assets")),
             ["net_income", "operating_cash_flow", "total_assets"], []),
    "LVGI": (lambda c, p: safe_div(_leverage(c), _leverage(p)),
             ["current_liabilities", "long_term_debt", "total_assets"],
             ["current_liabilities", "long_term_debt", "total_assets"]),
}


def classify_m(m_score, threshold=BENEISH_THRESHOLD):
    if m_score is None:
        return None
    return "probable_manipulator" if m_score > threshold else "not_flagged"


def compute_beneish(c, p):
    indices, missing = {}, []
    for name, (fn, need_c, need_p) in INDEX_SPEC.items():
        miss = _missing(c, p, need_c, need_p)
        val = None if miss else fn(c, p)
        if val is None and not miss:
            miss = ["zero or undefined denominator"]
        indices[name] = val
        missing += [f"{name}: {m}" for m in miss]

    m_score = None
    if all(v is not None for v in indices.values()):
        m_score = BENEISH_COEFFS["const"] + sum(BENEISH_COEFFS[k] * v for k, v in indices.items())
    return {"indices": indices, "m_score": m_score, "threshold": BENEISH_THRESHOLD,
            "classification": classify_m(m_score), "missing": missing}


# --------------------------------------------------------------------------
# Altman Z
# --------------------------------------------------------------------------
def altman_zone(z, cutoffs):
    if z is None:
        return None
    lo, hi = cutoffs
    return "distress" if z < lo else ("safe" if z > hi else "grey")


def compute_altman(c, market_cap=None, variant=ALTMAN_VARIANT):
    spec = ALTMAN_VARIANTS[variant]
    ta = c.get("total_assets")
    wc = (None if c.get("current_assets") is None or c.get("current_liabilities") is None
          else c["current_assets"] - c["current_liabilities"])
    equity_basis = market_cap if spec["x4"] == "market" else c.get("equity")
    x = {
        "X1": safe_div(wc, ta),
        "X2": safe_div(c.get("retained_earnings"), ta),
        "X3": safe_div(c.get("ebit"), ta),
        "X4": safe_div(equity_basis, c.get("total_liabilities")),
        "X5": safe_div(c.get("sales"), ta),
    }
    labels = {"X1": "working capital / total assets", "X2": "retained earnings / total assets",
              "X3": "EBIT / total assets",
              "X4": ("market cap" if spec["x4"] == "market" else "book equity") + " / total liabilities",
              "X5": "sales / total assets"}
    weights = dict(zip(x, spec["coeffs"]))
    missing = [f"{k} ({labels[k]})" for k, w in weights.items() if w != 0 and x[k] is None]
    z = None
    if not missing:
        z = spec["const"] + sum(w * x[k] for k, w in weights.items() if w != 0)
    return {"variant": variant, "ratios": x, "z_score": z, "cutoffs": spec["cutoffs"],
            "zone": altman_zone(z, spec["cutoffs"]), "missing": missing}


# --------------------------------------------------------------------------
# Piotroski F-Score
# --------------------------------------------------------------------------
def _cmp(a, b, op):
    return None if a is None or b is None else int(op(a, b))


def _sub(a, b):
    return None if a is None or b is None else a - b


def compute_piotroski(c, p):
    roa = lambda r: safe_div(r.get("net_income"), r.get("total_assets"))
    ltd_ta = lambda r: safe_div(r.get("long_term_debt"), r.get("total_assets"))
    cur_ratio = lambda r: safe_div(r.get("current_assets"), r.get("current_liabilities"))
    turnover = lambda r: safe_div(r.get("sales"), r.get("total_assets"))

    s = dict.fromkeys(PIOTROSKI_SIGNALS)
    s["ROA>0"] = _cmp(roa(c), 0.0, lambda a, b: a > b)
    s["CFO>0"] = _cmp(c.get("operating_cash_flow"), 0.0, lambda a, b: a > b)
    s["dROA>0"] = _cmp(_sub(roa(c), roa(p)), 0.0, lambda a, b: a > b)
    s["CFO>NI"] = _cmp(c.get("operating_cash_flow"), c.get("net_income"), lambda a, b: a > b)
    s["dLeverage<0"] = _cmp(ltd_ta(c), ltd_ta(p), lambda a, b: a < b)
    s["dCurrentRatio>0"] = _cmp(cur_ratio(c), cur_ratio(p), lambda a, b: a > b)
    s["NoNewShares"] = _cmp(c.get("shares_outstanding"), p.get("shares_outstanding"), lambda a, b: a <= b)
    s["dGrossMargin>0"] = _cmp(_gross_margin(c), _gross_margin(p), lambda a, b: a > b)
    s["dAssetTurnover>0"] = _cmp(turnover(c), turnover(p), lambda a, b: a > b)

    missing = [k for k, v in s.items() if v is None]
    f = None if missing else sum(s.values())
    return {"signals": s, "f_score": f, "signals_available": 9 - len(missing), "missing": missing}


# --------------------------------------------------------------------------
# Market cap helper (only needed for the z_original variant)
# --------------------------------------------------------------------------
def load_prices(csv_path):
    """Reads the yfinance CSV that has the extra 'Ticker' / 'Date' header rows."""
    return pd.read_csv(csv_path, skiprows=[1, 2], index_col=0, parse_dates=True)


def year_end_close(prices, fiscal_year, max_gap_days=10):
    """Last close on/before 31 March of fiscal_year (Indian FY end)."""
    end = pd.Timestamp(f"{fiscal_year}-03-31")
    s = prices.loc[:end, "Close"].dropna()
    if s.empty or (end - s.index[-1]).days > max_gap_days:
        return None
    return float(s.iloc[-1])


# --------------------------------------------------------------------------
# Orchestration: facts in the database -> features per fiscal year
# --------------------------------------------------------------------------
def build_features(company_id=1, db_path=DB_PATH, variant=ALTMAN_VARIANT, prices_csv=None):
    conn = sqlite3.connect(db_path)
    comp = conn.execute("SELECT symbol, sector, is_financial FROM COMPANY WHERE company_id = ?",
                        (company_id,)).fetchone()
    if comp is None:
        conn.close()
        raise ValueError(f"company_id {company_id} not found")
    df = pd.read_sql_query(
        "SELECT fiscal_year, line_item, value FROM FINANCIAL_FACT "
        "WHERE company_id = ? AND period_type = 'annual'", conn, params=(company_id,))
    conn.close()

    symbol, sector, is_financial = comp
    out = {"symbol": symbol, "sector": sector, "years": {}}
    if df.empty:
        return out

    pivot = df.pivot(index="fiscal_year", columns="line_item", values="value")
    prices = load_prices(prices_csv) if prices_csv else None

    for fy in sorted(pivot.index):
        cur = derive(pivot.loc[fy].to_dict())
        prior = derive(pivot.loc[fy - 1].to_dict()) if (fy - 1) in pivot.index else None   # FR-86 contiguity
        res = {"has_prior_year": prior is not None}

        if is_financial:                                                                    # FR-20
            na = {"status": "not_applicable", "reason": "financial-sector company"}
            res["beneish"], res["altman"] = dict(na), dict(na)
        else:
            if prior is None:
                res["beneish"] = {"m_score": None, "missing": ["no contiguous prior year"]}
            else:
                res["beneish"] = compute_beneish(cur, prior)
            mcap = None
            if prices is not None and cur.get("shares_outstanding") is not None:
                px = year_end_close(prices, fy)
                mcap = None if px is None else px * cur["shares_outstanding"]
            res["altman"] = compute_altman(cur, market_cap=mcap, variant=variant)

        res["piotroski"] = (compute_piotroski(cur, prior) if prior is not None
                            else {"f_score": None, "signals": {}, "missing": ["no contiguous prior year"]})
        out["years"][int(fy)] = res
    return out


if __name__ == "__main__":
    feats = build_features(company_id=1, prices_csv="data/ZEEL.NS_prices.csv")
    print(f"Company: {feats['symbol']}  ({feats['sector']})")
    for fy, r in feats["years"].items():
        print(f"\n=== FY {fy} ===")
        b, a, f = r["beneish"], r["altman"], r["piotroski"]
        print("Beneish M :", b.get("m_score"), b.get("classification"))
        for name, v in b.get("indices", {}).items():
            print(f"   {name:<5}", None if v is None else round(v, 4))
        print("   missing:", b.get("missing"))
        print(f"Altman Z  : {a.get('z_score')}  zone={a.get('zone')}  variant={a.get('variant')}")
        print("   missing:", a.get("missing"))
        print("Piotroski :", f.get("f_score"), f"({f.get('signals_available', 0)}/9 signals available)")
        print("   missing:", f.get("missing"))
