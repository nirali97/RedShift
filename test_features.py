"""Unit tests for features.py (SDD section 5.1). Run:  pytest -q"""
import math

import pytest

from features import (altman_zone, classify_m, compute_altman, compute_beneish,
                      compute_piotroski, derive, safe_div)

PRIOR = dict(sales=1000, cogs=600, trade_receivables=150, current_assets=400, net_ppe=300,
             total_assets=1000, depreciation=50, sga=100, current_liabilities=200,
             long_term_debt=100, net_income=80, operating_cash_flow=90, shares_outstanding=100)
CURR = dict(sales=1200, cogs=720, trade_receivables=240, current_assets=480, net_ppe=330,
            total_assets=1200, depreciation=54, sga=132, current_liabilities=264,
            long_term_debt=120, net_income=96, operating_cash_flow=60, shares_outstanding=100,
            retained_earnings=300, ebit=150, equity=600, total_liabilities=600)


# ---- guarded division (FR-87) -------------------------------------------
@pytest.mark.parametrize("num,den", [(1, 0), (1, None), (None, 1), (float("nan"), 1), (1, float("inf"))])
def test_safe_div_returns_none_not_inf_or_nan(num, den):
    assert safe_div(num, den) is None


def test_safe_div_negative_denominator_and_zero_numerator():
    assert safe_div(10, -2) == -5
    assert safe_div(0, 5) == 0.0          # a real zero is NOT absent (FR-89)


# ---- Beneish: worked example computed by hand ---------------------------
def test_beneish_indices_match_hand_calculation():
    r = compute_beneish(derive(CURR), derive(PRIOR))
    i = r["indices"]
    assert i["DSRI"] == pytest.approx(1.333333, abs=1e-5)
    assert i["GMI"] == pytest.approx(1.0)
    assert i["AQI"] == pytest.approx(1.083333, abs=1e-5)
    assert i["SGI"] == pytest.approx(1.2)
    assert i["DEPI"] == pytest.approx(1.015873, abs=1e-5)
    assert i["SGAI"] == pytest.approx(1.1)
    assert i["TATA"] == pytest.approx(0.03)
    assert i["LVGI"] == pytest.approx(1.066667, abs=1e-5)
    assert r["m_score"] == pytest.approx(-1.858071, abs=1e-5)
    assert r["classification"] == "not_flagged"
    assert r["missing"] == []


def test_beneish_missing_input_is_reported_not_defaulted():
    c = dict(CURR)
    del c["trade_receivables"]
    r = compute_beneish(derive(c), derive(PRIOR))
    assert r["m_score"] is None
    assert r["indices"]["DSRI"] is None
    assert any("DSRI: trade_receivables (current year)" in m for m in r["missing"])


def test_beneish_zero_denominator_is_not_computable():
    c = dict(CURR, sales=0)
    r = compute_beneish(derive(c), derive(PRIOR))
    assert r["m_score"] is None


def test_absent_is_not_zero():
    """net_income = 0.0 is a real value (TATA computable); absent is not."""
    r0 = compute_beneish(derive(dict(CURR, net_income=0.0)), derive(PRIOR))
    assert r0["indices"]["TATA"] == pytest.approx(-60 / 1200)
    c = dict(CURR)
    del c["net_income"]
    assert compute_beneish(derive(c), derive(PRIOR))["indices"]["TATA"] is None


def test_m_score_threshold_boundary():
    assert classify_m(-1.78) == "not_flagged"            # exactly at threshold: NOT flagged
    assert classify_m(-1.7799) == "probable_manipulator"
    assert classify_m(None) is None


# ---- Altman ---------------------------------------------------------------
def test_altman_double_prime_matches_hand_calculation():
    r = compute_altman(derive(CURR), variant="z_double_prime")
    assert r["ratios"]["X1"] == pytest.approx(0.18)
    assert r["z_score"] == pytest.approx(3.8858, abs=1e-4)
    assert r["zone"] == "safe"


def test_altman_original_uses_market_cap():
    r = compute_altman(derive(CURR), market_cap=900, variant="z_original")
    assert r["z_score"] == pytest.approx(2.8785, abs=1e-4)
    assert r["zone"] == "grey"
    assert compute_altman(derive(CURR), market_cap=None, variant="z_original")["z_score"] is None


@pytest.mark.parametrize("z,expected", [(1.80, "distress"), (1.81, "grey"), (2.99, "grey"), (3.00, "safe")])
def test_altman_zone_boundaries_original(z, expected):
    assert altman_zone(z, (1.81, 2.99)) == expected


@pytest.mark.parametrize("z,expected", [(1.09, "distress"), (1.10, "grey"), (2.60, "grey"), (2.61, "safe")])
def test_altman_zone_boundaries_double_prime(z, expected):
    assert altman_zone(z, (1.10, 2.60)) == expected


# ---- Piotroski ------------------------------------------------------------
def test_piotroski_all_nine_pass():
    p = dict(net_income=10, total_assets=100, sales=100, cogs=80, operating_cash_flow=30,
             long_term_debt=40, current_assets=50, current_liabilities=40, shares_outstanding=10)
    c = dict(net_income=20, total_assets=100, sales=120, cogs=90, operating_cash_flow=30,
             long_term_debt=30, current_assets=60, current_liabilities=40, shares_outstanding=10)
    r = compute_piotroski(derive(c), derive(p))
    assert r["f_score"] == 9 and all(v == 1 for v in r["signals"].values())


def test_piotroski_all_nine_fail():
    p = dict(net_income=20, total_assets=100, sales=120, cogs=90, operating_cash_flow=30,
             long_term_debt=30, current_assets=60, current_liabilities=40, shares_outstanding=10)
    c = dict(net_income=-5, total_assets=100, sales=100, cogs=90, operating_cash_flow=-10,
             long_term_debt=40, current_assets=40, current_liabilities=40, shares_outstanding=12)
    r = compute_piotroski(derive(c), derive(p))
    assert r["f_score"] == 0 and all(v == 0 for v in r["signals"].values())


def test_piotroski_missing_signal_gives_no_score():
    r = compute_piotroski(derive({"operating_cash_flow": 5, "total_assets": 10}), derive({"total_assets": 10}))
    assert r["f_score"] is None
    assert "CFO>0" not in r["missing"]
    assert r["signals_available"] < 9


# ---- derive ---------------------------------------------------------------
def test_derive_cleans_nan_and_fills_gross_profit():
    d = derive({"sales": 100, "cogs": 60, "net_income": float("nan")})
    assert d["gross_profit"] == 40
    assert d["net_income"] is None
    assert not any(isinstance(v, float) and math.isnan(v) for v in d.values() if v is not None)
