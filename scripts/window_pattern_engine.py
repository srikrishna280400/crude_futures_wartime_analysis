"""window_pattern_engine.py — Step 3, 4 of the directive.

Per directive §6-7:
  - For every window × phase: direction split (up/down/flat) with counts and %
  - Mean/median/dispersion of window_return_pct per direction
  - Which window most often sets the day's high; which most often sets the day's low — counts, by phase
  - A transition/Markov-style matrix: P(window i+1 direction | window i direction), per phase
  - Magnitude tier % per window × phase

Output:
  - transition_matrices/{phase_id}.csv
  - window_stats.csv (frequency/direction tables)
  - magnitude_crosstabs.csv
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
TM_DIR = ARTIFACTS / "transition_matrices"
TM_DIR.mkdir(exist_ok=True)


WINDOW_ORDER = [
    "asia_early", "us_late", "global_reopen_pre_mcx", "mcx_open_drive",
    "india_morning", "india_midday", "europe_midday", "us_pre_open",
    "us_open", "mcx_tail",
]


def main():
    print(">>> window_pattern_engine.py starting", flush=True)
    p = pd.read_parquet(ARTIFACTS / "primitives.parquet")
    phase = pd.read_csv(ARTIFACTS / "phase_lookup.csv")

    # Only session-level rows have meaningful direction+leg for window analysis
    sess = p[p["__stream"].isin(["WTI_session", "BRENT_session"])].copy()
    print(f">>> session rows: {len(sess):,}", flush=True)

    # Sort by (symbol, date, window order) so transition makes sense
    sess["_win_rank"] = sess["session_window_ist"].map({w: i for i, w in enumerate(WINDOW_ORDER)})
    sess = sess.sort_values(["__stream", "trade_date_ist", "_win_rank"]).reset_index(drop=True)

    # =========================================================
    # Step 3a: Direction split per window × phase
    # =========================================================
    rows = []
    for (sym, win, pid), g in sess.groupby(["__stream", "session_window_ist", "phase_id"], observed=True):
        n = len(g)
        nu = (g["direction"] == "UP").sum()
        nd = (g["direction"] == "DOWN").sum()
        nf = (g["direction"] == "FLAT").sum()
        nna = g["direction"].isna().sum()
        valid = nu + nd + nf
        if valid == 0:
            continue
        rows.append({
            "stream": sym,
            "session_window_ist": win,
            "phase_id": pid,
            "phase_label": g["phase_label"].iloc[0] if "phase_label" in g.columns else "",
            "n_total": n,
            "n_valid": valid,
            "n_up": int(nu),
            "n_down": int(nd),
            "n_flat": int(nf),
            "pct_up": nu / valid * 100 if valid else np.nan,
            "pct_down": nd / valid * 100 if valid else np.nan,
            "pct_flat": nf / valid * 100 if valid else np.nan,
            "mean_return_pct": g["window_return_pct"].mean(),
            "median_return_pct": g["window_return_pct"].median(),
            "std_return_pct": g["window_return_pct"].std(),
            "low_confidence_flag": valid < 5,
        })
    win_stats = pd.DataFrame(rows).sort_values(["stream", "phase_id", "session_window_ist"])
    win_stats.to_csv(ARTIFACTS / "window_stats.csv", index=False)
    print(f">>> wrote window_stats.csv ({len(win_stats)} rows)", flush=True)

    # =========================================================
    # Step 3b: Daily high / low window attribution
    # =========================================================
    # For each (date, symbol), find which window had the day's high and which had the day's low.
    # Use session-level high_native vs all-windows for that day/symbol.
    daily_hl = []
    for (sym, d), g in sess.groupby(["__stream", "trade_date_ist"], observed=True):
        if g["high_native"].isna().all() or len(g) == 0:
            continue
        idx_max = g["high_native"].idxmax()
        idx_min = g["low_native"].idxmin()
        daily_hl.append({
            "stream": sym,
            "trade_date_ist": d,
            "phase_id": g["phase_id"].iloc[0],
            "phase_label": g["phase_label"].iloc[0] if "phase_label" in g.columns else "",
            "high_window": g.loc[idx_max, "session_window_ist"] if pd.notna(idx_max) else "",
            "low_window": g.loc[idx_min, "session_window_ist"] if pd.notna(idx_min) else "",
            "day_high": g["high_native"].max(),
            "day_low": g["low_native"].min(),
        })
    daily_hl_df = pd.DataFrame(daily_hl)
    daily_hl_df.to_csv(ARTIFACTS / "daily_high_low_window.csv", index=False)

    # Per-phase counts of high_window / low_window
    if not daily_hl_df.empty:
        high_counts = (
            daily_hl_df.groupby(["phase_id", "high_window"], observed=True)
            .size().reset_index(name="n").rename(columns={"high_window": "window"})
        )
        low_counts = (
            daily_hl_df.groupby(["phase_id", "low_window"], observed=True)
            .size().reset_index(name="n").rename(columns={"low_window": "window"})
        )
        hl_summary = pd.merge(high_counts, low_counts, on=["phase_id", "window"], how="outer", suffixes=("_high", "_low")).fillna(0)
        hl_summary.to_csv(ARTIFACTS / "daily_high_low_counts_by_phase.csv", index=False)

    # =========================================================
    # Step 3c: Transition matrices per phase — direction-state based
    # =========================================================
    # P(direction_{i+1} | direction_i) per phase, conditioned on (stream+phase)
    states = ["UP", "DOWN", "FLAT"]

    for pid in sorted(sess["phase_id"].unique()):
        ps = sess[sess["phase_id"] == pid].copy()
        # For each stream, compute transition counts
        for sym in ps["__stream"].unique():
            sub = ps[ps["__stream"] == sym].sort_values(["trade_date_ist", "_win_rank"]).copy()
            # shift(-1) gives next state within same date
            sub["next_direction"] = sub.groupby("trade_date_ist")["direction"].shift(-1)
            sub = sub.dropna(subset=["next_direction"])
            ct = pd.crosstab(sub["direction"], sub["next_direction"])
            # Ensure all states present
            for s in states:
                if s not in ct.columns: ct[s] = 0
                if s not in ct.index: ct.loc[s] = 0
            ct = ct.loc[states, states]
            # Normalize row-wise → conditional probabilities
            row_sums = ct.sum(axis=1).replace(0, np.nan)
            prob = ct.div(row_sums, axis=0).fillna(0)
            # Add n row
            ct_long = ct.reset_index().melt(id_vars="direction", var_name="next_direction", value_name="count")
            prob_long = prob.reset_index().melt(id_vars="direction", var_name="next_direction", value_name="probability")
            tm = ct_long.merge(prob_long, on=["direction", "next_direction"])
            tm["n_total_in_row"] = tm["direction"].map(ct.sum(axis=1))
            tm["phase_id"] = pid
            tm["stream"] = sym
            fname = TM_DIR / f"phase_{pid}_{sym}.csv"
            tm.to_csv(fname, index=False)

    # Also write a combined transition matrix per phase (both streams combined)
    for pid in sorted(sess["phase_id"].unique()):
        ps = sess[sess["phase_id"] == pid].copy()
        ps["next_direction"] = ps.groupby(["__stream", "trade_date_ist"])["direction"].shift(-1)
        ps = ps.dropna(subset=["next_direction"])
        ct = pd.crosstab(ps["direction"], ps["next_direction"])
        for s in states:
            if s not in ct.columns: ct[s] = 0
            if s not in ct.index: ct.loc[s] = 0
        ct = ct.loc[states, states]
        row_sums = ct.sum(axis=1).replace(0, np.nan)
        prob = ct.div(row_sums, axis=0).fillna(0)
        ct_long = ct.reset_index().melt(id_vars="direction", var_name="next_direction", value_name="count")
        prob_long = prob.reset_index().melt(id_vars="direction", var_name="next_direction", value_name="probability")
        tm = ct_long.merge(prob_long, on=["direction", "next_direction"])
        tm["n_total_in_row"] = tm["direction"].map(ct.sum(axis=1))
        tm["phase_id"] = pid
        fname = TM_DIR / f"phase_{pid}_combined.csv"
        tm.to_csv(fname, index=False)

    # =========================================================
    # Step 3d: Adjacent window-position transitions
    # P(window_{i+1} | window_i) for the WTI/Brent combined stream per phase
    # =========================================================
    for pid in sorted(sess["phase_id"].unique()):
        ps = sess[sess["phase_id"] == pid].copy()
        ps["next_window"] = ps.groupby(["__stream", "trade_date_ist"])["session_window_ist"].shift(-1)
        ps = ps.dropna(subset=["next_window"])
        ct = pd.crosstab(ps["session_window_ist"], ps["next_window"])
        # Only keep WINDOW_ORDER rows & cols (might add extras)
        for w in WINDOW_ORDER:
            if w not in ct.columns: ct[w] = 0
            if w not in ct.index: ct.loc[w] = 0
        ct = ct.loc[WINDOW_ORDER, WINDOW_ORDER]
        row_sums = ct.sum(axis=1).replace(0, np.nan)
        prob = ct.div(row_sums, axis=0).fillna(0)
        ct_long = ct.reset_index().melt(id_vars="session_window_ist", var_name="next_window", value_name="count")
        prob_long = prob.reset_index().melt(id_vars="session_window_ist", var_name="next_window", value_name="probability")
        tm = ct_long.merge(prob_long, on=["session_window_ist", "next_window"])
        tm["n_total_in_row"] = tm["session_window_ist"].map(ct.sum(axis=1))
        tm["phase_id"] = pid
        fname = TM_DIR / f"phase_{pid}_window_to_window.csv"
        tm.to_csv(fname, index=False)

    # =========================================================
    # Step 4: Magnitude tier distributions per window × phase
    # =========================================================
    # For each (phase, window): % of days in each magnitude tier, with n
    rows = []
    for (sym, win, pid), g in sess.groupby(["__stream", "session_window_ist", "phase_id"], observed=True):
        if g["magnitude_tier"].isna().all() or (g["magnitude_tier"] == "UNCLASSIFIED").all():
            continue
        tier_counts = g["magnitude_tier"].value_counts()
        n = tier_counts.sum()
        if n < 5:
            continue  # LOW-CONFIDENCE
        for tier, c in tier_counts.items():
            rows.append({
                "stream": sym,
                "session_window_ist": win,
                "phase_id": pid,
                "phase_label": g["phase_label"].iloc[0] if "phase_label" in g.columns else "",
                "magnitude_tier": tier,
                "count": int(c),
                "pct": c / n * 100,
                "n_total": int(n),
                "low_confidence_flag": n < 5,
            })
    mag_df = pd.DataFrame(rows).sort_values(["stream", "phase_id", "session_window_ist", "magnitude_tier"])
    mag_df.to_csv(ARTIFACTS / "magnitude_crosstabs.csv", index=False)
    print(f">>> wrote magnitude_crosstabs.csv ({len(mag_df)} rows)", flush=True)

    # =========================================================
    # Step 4b: Magnitude × weekday factors (EIA Wed, Mon, Fri, expiry-week)
    # =========================================================
    sess["trade_date_ist"] = pd.to_datetime(sess["trade_date_ist"])
    sess["is_wed"] = (sess["trade_date_ist"].dt.dayofweek == 2).astype(int)
    sess["is_mon"] = (sess["trade_date_ist"].dt.dayofweek == 0).astype(int)
    sess["is_fri"] = (sess["trade_date_ist"].dt.dayofweek == 4).astype(int)
    rows = []
    for (sym, win, pid, daybit), g in sess.groupby(
        ["__stream", "session_window_ist", "phase_id", "is_wed"], observed=True
    ):
        if g["magnitude_tier"].isna().all() or (g["magnitude_tier"] == "UNCLASSIFIED").all():
            continue
        n = len(g)
        if n < 5:
            continue
        # Find top tier
        tier_counts = g["magnitude_tier"].value_counts()
        top_tier = tier_counts.index[0] if len(tier_counts) > 0 else ""
        rows.append({
            "stream": sym,
            "session_window_ist": win,
            "phase_id": pid,
            "factor": "is_wednesday_eia_day" if daybit else "non_wednesday",
            "n": int(n),
            "top_magnitude_tier": top_tier,
            "pct_top_tier": tier_counts.iloc[0] / n * 100 if n else np.nan,
            "mean_return_pct": g["window_return_pct"].mean(),
        })
    eia_crosstab = pd.DataFrame(rows)
    if not eia_crosstab.empty:
        eia_crosstab.to_csv(ARTIFACTS / "magnitude_x_eia.csv", index=False)
    print(f">>> wrote magnitude_x_eia.csv ({len(eia_crosstab)} rows)", flush=True)

    # =========================================================
    # Window_stats high-level summary table
    # =========================================================
    print("\n>>> Sample window_stats (first 12 rows):", flush=True)
    print(win_stats.head(12).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()