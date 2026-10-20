"""
quant_scorer.py (v3) - Quant Scorer Agent.

Reads real scores from features.py and writes them to SCORE_RUN / RED_FLAG.

Design rules
  * ONE run per company + fiscal year, updated in place on re-run. Runs are never
    deleted, so QUAL_FINDING rows and market flags that other agents attached to a
    run_id survive. Only this agent's own 'Quantitative' flags are replaced.
  * composite_score / severity_band are reset to NULL when scores change, because the
    old composite is stale. Re-run report_generator.py afterwards.
  * FR-20  banks / NBFCs / insurers: no M or Z score, with an explicit 'not applicable' flag.
  * FR-21  a score that cannot be computed is recorded with the missing input.
  * FR-22  deterioration is judged against the PRIOR YEAR's computed scores (no hard-coded year).
  * FR-23  contributors are ranked by contribution to the M-Score, not by distance from 1.0.
  * Altman zone and cut-offs come from the variant used in features.py.

Usage:  py quant_scorer.py          (all companies)
        py quant_scorer.py 1        (one company_id)
"""
import sqlite3
import sys
from datetime import datetime, timezone

from chart_of_accounts import BENEISH_COEFFS, BENEISH_THRESHOLD
from features import build_features

DB_PATH = "data/red_shift.db"
MODEL_PREFIX = "v2.1-features"

# FR-22 thresholds (configurable - agree the values with the team)
M_SCORE_RISE = 0.30        # M-Score increase between consecutive years
F_SCORE_DROP = 2           # F-Score decrease between consecutive years
Z_SCORE_DROP_PCT = 0.15    # relative Z-Score decrease between consecutive years
F_SCORE_WEAK = 3           # F-Score at or below this is "weak"

# value at which an index adds nothing to the M-Score
NEUTRAL = {"DSRI": 1.0, "GMI": 1.0, "AQI": 1.0, "SGI": 1.0,
           "DEPI": 1.0, "SGAI": 1.0, "LVGI": 1.0, "TATA": 0.0}


# --------------------------------------------------------------------------
# FR-23 helpers
# --------------------------------------------------------------------------
def level_contributions(indices):
    """coefficient x (index - neutral). Positive pushes the M-Score up (worse)."""
    return {k: BENEISH_COEFFS[k] * (v - NEUTRAL[k]) for k, v in indices.items()}


def change_contributions(indices, prior_indices):
    """Year-on-year change in each index's contribution to the M-Score."""
    return {k: BENEISH_COEFFS[k] * (v - prior_indices[k]) for k, v in indices.items()}


def top_adverse(contribs, n=3):
    ranked = sorted(contribs.items(), key=lambda kv: kv[1], reverse=True)
    return ", ".join(f"{k} {v:+.3f}" for k, v in ranked[:n] if v > 0) or "none"


# --------------------------------------------------------------------------
# DB helpers
# --------------------------------------------------------------------------
def _upsert_run(cur, company_id, fy, status, m, z, f, model_version, now_ts):
    row = cur.execute("SELECT MAX(run_id) FROM SCORE_RUN WHERE company_id = ? AND fiscal_year = ?",
                      (company_id, fy)).fetchone()
    rnd = lambda v: None if v is None else round(v, 4)
    if row and row[0] is not None:
        run_id = row[0]
        cur.execute("""UPDATE SCORE_RUN SET run_ts = ?, status = ?, m_score = ?, z_score = ?, f_score = ?,
                       composite_score = NULL, severity_band = NULL, model_version = ? WHERE run_id = ?""",
                    (now_ts, status, rnd(m), rnd(z), f, model_version, run_id))
        cur.execute("DELETE FROM RED_FLAG WHERE run_id = ? AND category = 'Quantitative'", (run_id,))
    else:
        cur.execute("""INSERT INTO SCORE_RUN (company_id, fiscal_year, run_ts, status, m_score, z_score,
                       f_score, model_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (company_id, fy, now_ts, status, rnd(m), rnd(z), f, model_version))
        run_id = cur.lastrowid
    return run_id


def _flag(cur, run_id, flag_type, severity, explanation, evidence):
    cur.execute("""INSERT INTO RED_FLAG (run_id, category, flag_type, severity, explanation, evidence_ref)
                   VALUES (?, 'Quantitative', ?, ?, ?, ?)""",
                (run_id, flag_type, severity, explanation, evidence))


# --------------------------------------------------------------------------
# Main logic
# --------------------------------------------------------------------------
def score_company(conn, company_id, db_path=DB_PATH):
    cur = conn.cursor()
    comp = cur.execute("SELECT symbol, sector, is_financial FROM COMPANY WHERE company_id = ?",
                       (company_id,)).fetchone()
    if not comp:
        print(f"company_id {company_id} not found.")
        return
    symbol, sector, is_financial = comp

    feats = build_features(company_id=company_id, db_path=db_path)
    years = feats["years"]
    if not years:
        print(f"{symbol}: no facts loaded - run the loader first.")
        return

    now_ts = datetime.now(timezone.utc).isoformat()
    print(f"\n--- Quant Scorer: {symbol} ({sector}) ---")

    for fy in sorted(years):
        r = years[fy]
        if not r["has_prior_year"]:
            print(f"FY{fy}: skipped (no contiguous prior year)")
            continue

        # ---- FR-20: financial sector ----
        if is_financial:
            version = f"{MODEL_PREFIX}/not-applicable"
            run_id = _upsert_run(cur, company_id, fy, "Completed", None, None, None, version, now_ts)
            _flag(cur, run_id, "Model Not Applicable (FR-20)", "Info",
                  "Beneish and Altman models were estimated on non-financial companies and are not "
                  "valid for banks, NBFCs or insurers. No score is reported.",
                  f"sector={sector}; is_financial=1")
            print(f"FY{fy}: not applicable (financial sector)")
            continue

        b, a, p = r["beneish"], r["altman"], r["piotroski"]
        m, z, f = b.get("m_score"), a.get("z_score"), p.get("f_score")
        status = "Completed" if None not in (m, z, f) else "Degraded"
        version = f"{MODEL_PREFIX}/{a.get('variant')}"
        run_id = _upsert_run(cur, company_id, fy, status, m, z, f, version, now_ts)

        fmt = lambda v, d=3: "n/a" if v is None else f"{v:.{d}f}"
        print(f"FY{fy}: M={fmt(m)}  Z={fmt(z)} ({a.get('zone')})  F={f if f is not None else 'n/a'}  [{status}]")

        # ---- FR-21: scores that could not be computed ----
        gaps = ([("M-Score", b.get("missing"))] if m is None else []) \
             + ([("Z-Score", a.get("missing"))] if z is None else []) \
             + ([("F-Score", p.get("missing"))] if f is None else [])
        if gaps:
            ev = " | ".join(f"{name}: {', '.join(miss[:4])}{' ...' if len(miss) > 4 else ''}"
                            for name, miss in gaps)
            _flag(cur, run_id, "Score Not Computable (FR-21)", "Info",
                  "One or more scores could not be computed because inputs were missing.", ev)

        contrib_notes = []

        # ---- Beneish ----
        if m is not None and m > BENEISH_THRESHOLD:
            top = top_adverse(level_contributions(b["indices"]))
            _flag(cur, run_id, "Beneish Manipulation Flag", "High",
                  f"M-Score exceeds the {BENEISH_THRESHOLD} threshold, which indicates elevated earnings-manipulation risk.",
                  f"M-Score={m:.4f} > {BENEISH_THRESHOLD}; main contributors: {top}")
            contrib_notes.append(f"level vs neutral: {top}")

        # ---- Altman ----
        if a.get("zone") == "distress":
            lo, hi = a["cutoffs"]
            _flag(cur, run_id, "Altman Distress Flag", "High",
                  "Z-Score is in the distress zone.",
                  f"Z-Score={z:.4f} < {lo} (variant {a['variant']}, cut-offs {lo}/{hi})")

        # ---- Piotroski ----
        if f is not None and f <= F_SCORE_WEAK:
            failed = [k for k, v in p["signals"].items() if v == 0]
            _flag(cur, run_id, "Weak Fundamentals (Piotroski)", "Medium",
                  f"F-Score is {F_SCORE_WEAK} or below.", f"F-Score={f}/9; failed: {', '.join(failed)}")

        # ---- FR-22: deterioration vs the prior year's computed scores ----
        prev = years.get(fy - 1)
        if prev and prev["has_prior_year"] and not is_financial:
            pb, pa, pp = prev["beneish"], prev["altman"], prev["piotroski"]
            changes = []
            if m is not None and pb.get("m_score") is not None and m - pb["m_score"] >= M_SCORE_RISE:
                changes.append(f"M-Score {pb['m_score']:.3f} -> {m:.3f} (+{m - pb['m_score']:.3f})")
                top_chg = top_adverse(change_contributions(b["indices"], pb["indices"]))
                contrib_notes.append(f"change vs FY{fy - 1}: {top_chg}")
            if f is not None and pp.get("f_score") is not None and pp["f_score"] - f >= F_SCORE_DROP:
                changes.append(f"F-Score {pp['f_score']} -> {f}")
            if z is not None and pa.get("z_score") not in (None, 0) and \
                    (pa["z_score"] - z) / abs(pa["z_score"]) >= Z_SCORE_DROP_PCT:
                changes.append(f"Z-Score {pa['z_score']:.3f} -> {z:.3f}")
            if changes:
                _flag(cur, run_id, "Score Deterioration (FR-22)", "Medium",
                      "Scores worsened by more than the configured amount versus the prior year, "
                      "even if they remain inside an acceptable band.", "; ".join(changes))

        # ---- FR-23: one place listing the contributors ----
        if contrib_notes:
            _flag(cur, run_id, "Top Contributors (FR-23)", "Info",
                  "Beneish indices contributing most to the adverse result, ranked by contribution to the M-Score.",
                  " | ".join(contrib_notes))
            print(f"   contributors: {' | '.join(contrib_notes)}")

    conn.commit()


def run_quant_scorer(company_id=None, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    ids = [company_id] if company_id else [r[0] for r in conn.execute("SELECT company_id FROM COMPANY ORDER BY company_id")]
    for cid in ids:
        score_company(conn, cid, db_path)
    conn.close()
    print("\nDone. Now re-run report_generator.py so composite scores are recalculated.")


if __name__ == "__main__":
    run_quant_scorer(int(sys.argv[1]) if len(sys.argv) > 1 else None)