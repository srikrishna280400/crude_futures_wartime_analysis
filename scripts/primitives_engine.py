"""primitives_engine.py — Step 2 of the directive.

Computes analytical primitives per directive §5:
  - window_return_pct = (close - open)/open * 100
  - Direction classification (regime-relative, per phase) via median(|window_return_pct|)
  - Magnitude tiers (percentile-based within each phase)
  - ATR-equivalent (rolling typical range per phase)
  - "Leg" = direction + magnitude tier (categorical token)

Inputs: clean_master.parquet + phase_lookup.csv
Outputs: primitives.parquet + definitions.md
"""

from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"


def main():
    print(">>> primitives_engine.py starting", flush=True)
    master = pd.read_parquet(ARTIFACTS / "clean_master.parquet")
    phase = pd.read_csv(ARTIFACTS / "phase_lookup.csv")
    print(f">>> loaded master {master.shape}, phase {phase.shape}", flush=True)

    # =========================================================
    # Step 2a: Compute window_return_pct for each (symbol, date, window) row.
    # In our normalized data, "window" is session_window_ist and the
    # OHLCV for that window is already aggregated in the *_session files
    # (which carry OHLC at the session level).
    # For 5m/15m/60m files we need to aggregate up to (date,window) first.
    # =========================================================

    # We work on the session-level rows because they are already aggregated
    # to one row per (date, window). For intraday 5m/15m/60m rows we keep
    # them as granular and compute return_pct per bar.

    # ---- Session-level aggregation ----
    sess = master[master["__stream"].isin(["WTI_session", "BRENT_session"])].copy()
    print(f">>> session rows: {len(sess):,}", flush=True)

    if "open_native" in sess.columns and "close_native" in sess.columns:
        sess["window_return_pct"] = np.where(
            sess["open_native"].notna() & (sess["open_native"] != 0) & sess["close_native"].notna(),
            (sess["close_native"] - sess["open_native"]) / sess["open_native"] * 100.0,
            np.nan,
        )
        sess["window_range_pct"] = np.where(
            sess["open_native"].notna() & (sess["open_native"] != 0) & sess["high_native"].notna() & sess["low_native"].notna(),
            (sess["high_native"] - sess["low_native"]) / sess["open_native"] * 100.0,
            np.nan,
        )
    else:
        sess["window_return_pct"] = np.nan
        sess["window_range_pct"] = np.nan

    # ---- Daily-level: also build primitives for daily rows ----
    daily = master[master["__stream"].isin(["WTI_daily", "BRENT_daily"])].copy()
    if "open_native" in daily.columns and "close_native" in daily.columns:
        daily["window_return_pct"] = np.where(
            daily["open_native"].notna() & (daily["open_native"] != 0) & daily["close_native"].notna(),
            (daily["close_native"] - daily["open_native"]) / daily["open_native"] * 100.0,
            np.nan,
        )
        daily["window_range_pct"] = np.where(
            daily["open_native"].notna() & (daily["open_native"] != 0) & daily["high_native"].notna() & daily["low_native"].notna(),
            (daily["high_native"] - daily["low_native"]) / daily["open_native"] * 100.0,
            np.nan,
        )
        # MFE / MAE use existing columns if present
        daily["window_mfe_pct"] = daily.get("mfe_pct", np.nan)
        daily["window_mae_pct"] = daily.get("mae_pct", np.nan)
    else:
        daily["window_return_pct"] = np.nan
        daily["window_range_pct"] = np.nan
        daily["window_mfe_pct"] = np.nan
        daily["window_mae_pct"] = np.nan

    # ---- Intraday: 5m/15m/60m rows get a per-bar return ----
    intraday = master[master["__stream"].str.contains("m$")].copy()
    # Per-bar return from open to close
    if "open_native" in intraday.columns and "close_native" in intraday.columns:
        intraday["window_return_pct"] = np.where(
            intraday["open_native"].notna() & (intraday["open_native"] != 0) & intraday["close_native"].notna(),
            (intraday["close_native"] - intraday["open_native"]) / intraday["open_native"] * 100.0,
            np.nan,
        )
        intraday["window_range_pct"] = np.where(
            intraday["open_native"].notna() & (intraday["open_native"] != 0) & intraday["high_native"].notna() & intraday["low_native"].notna(),
            (intraday["high_native"] - intraday["low_native"]) / intraday["open_native"] * 100.0,
            np.nan,
        )
    else:
        intraday["window_return_pct"] = np.nan
        intraday["window_range_pct"] = np.nan

    # =========================================================
    # Step 2b: Regime-relative direction threshold
    # =========================================================
    # Per directive §6, threshold = fraction of phase's median(|window_return_pct|).
    # We use median(|return|) as the "noise floor"; a leg is "UP" if return > threshold,
    # "DOWN" if return < -threshold, else "FLAT".
    # Computed PER PHASE on session-level returns.

    abs_ret = sess["window_return_pct"].abs()
    phase_threshold = (
        sess.assign(_abs=abs_ret)
        .groupby("phase_id", observed=True)["_abs"]
        .median()
        .rename("phase_median_abs_return")
        .reset_index()
    )
    sess = sess.merge(phase_threshold, on="phase_id", how="left")
    sess["direction_threshold_pct"] = sess["phase_median_abs_return"] * 0.5  # half the noise floor

    def classify_dir(row):
        r = row.get("window_return_pct")
        thr = row.get("direction_threshold_pct")
        if pd.isna(r) or pd.isna(thr):
            return ""
        if r > thr:
            return "UP"
        if r < -thr:
            return "DOWN"
        return "FLAT"

    sess["direction"] = sess.apply(classify_dir, axis=1)

    # =========================================================
    # Step 2c: Magnitude tiers — percentile within phase × window
    # =========================================================
    # Per directive: <25th, 25-50th, 50-75th, 75-90th, >90th, all in absolute return space
    # Use qcut on abs_return within phase × window.
    # For windows with too few rows (<5), fall back to phase-level only.

    def assign_tier(g):
        r = g["window_return_pct"].abs()
        n = r.notna().sum()
        if n < 5:
            g["magnitude_tier"] = "UNCLASSIFIED"
            g["magnitude_pctile"] = np.nan
            return g
        try:
            q = pd.qcut(r.rank(method="first"), q=[0, 0.25, 0.5, 0.75, 0.9, 1.0],
                        labels=["Q1_0_25", "Q2_25_50", "Q3_50_75", "Q4_75_90", "Q5_90_100"])
            g["magnitude_tier"] = q.astype("string").fillna("UNCLASSIFIED")
        except ValueError:
            g["magnitude_tier"] = "UNCLASSIFIED"
        g["magnitude_pctile"] = r.rank(pct=True)
        return g

    # Vectorized pctile computation; qcut per (phase, window)
    sess["_abs_ret"] = sess["window_return_pct"].abs()
    sess["magnitude_pctile"] = (
        sess.groupby(["phase_id", "session_window_ist"], observed=True, group_keys=False)["_abs_ret"].rank(pct=True)
    )
    # Tier from pd.qcut per (phase, window) - use transform-like apply
    sess["magnitude_tier"] = ""
    for (pid, win), g in sess.groupby(["phase_id", "session_window_ist"], observed=True):
        r = g["_abs_ret"]
        idx = g.index
        if r.notna().sum() < 5:
            sess.loc[idx, "magnitude_tier"] = "UNCLASSIFIED"
            continue
        try:
            q = pd.qcut(r.rank(method="first"), q=[0, 0.25, 0.5, 0.75, 0.9, 1.0],
                        labels=["Q1_0_25", "Q2_25_50", "Q3_50_75", "Q4_75_90", "Q5_90_100"])
            sess.loc[idx, "magnitude_tier"] = q.astype("string").fillna("UNCLASSIFIED").values
        except ValueError:
            sess.loc[idx, "magnitude_tier"] = "UNCLASSIFIED"
    sess["leg"] = sess["direction"].astype(str) + "_" + sess["magnitude_tier"].astype(str)
    sess = sess.drop(columns=["_abs_ret"])
    # Replace empty direction with "FLAT" so leg doesn't start with "_"
    sess["leg"] = sess["leg"].str.replace(r"^_", "FLAT_", regex=True)

    # =========================================================
    # Step 2d: ATR-equivalent — rolling typical range per phase
    # =========================================================
    # For each phase, ATR = mean(window_range_pct) of that phase.
    phase_atr = (
        sess.groupby("phase_id", observed=True)["window_range_pct"]
        .mean()
        .rename("phase_atr_pct")
        .reset_index()
    )
    sess = sess.merge(phase_atr, on="phase_id", how="left")

    # =========================================================
    # Step 2e: Daily MFE/MAE copy
    # =========================================================
    if "mfe_pct" in daily.columns:
        daily["window_mfe_pct"] = daily["mfe_pct"]
        daily["window_mae_pct"] = daily["mae_pct"]

    # =========================================================
    # Write outputs
    # =========================================================
    # Output a unified primitives.parquet with both session and intraday rows
    # We add phase_median_abs_return / direction_threshold_pct to sess only
    primitives = pd.concat(
        [
            sess[
                [
                    "trade_date_ist", "__stream", "session_window_ist", "phase_id", "phase_label",
                    "open_native", "high_native", "low_native", "close_native", "volume",
                    "window_return_pct", "window_range_pct", "direction", "magnitude_tier",
                    "magnitude_pctile", "leg", "phase_median_abs_return",
                    "direction_threshold_pct", "phase_atr_pct",
                ]
            ],
            intraday.assign(direction="", magnitude_tier="INTRADAY_BAR", magnitude_pctile=np.nan, leg="INTRADAY_BAR")[
                ["trade_date_ist", "__stream", "session_window_ist", "phase_id", "phase_label",
                 "open_native", "high_native", "low_native", "close_native", "volume",
                 "window_return_pct", "window_range_pct", "direction", "magnitude_tier",
                 "magnitude_pctile", "leg"]
            ],
            daily.assign(direction="", magnitude_tier="DAILY_BAR", magnitude_pctile=np.nan, leg="DAILY_BAR")[
                ["trade_date_ist", "__stream", "session_window_ist", "phase_id", "phase_label",
                 "open_native", "high_native", "low_native", "close_native", "volume",
                 "window_return_pct", "window_range_pct", "direction", "magnitude_tier",
                 "magnitude_pctile", "leg"]
            ],
        ],
        ignore_index=True,
    )
    out = ARTIFACTS / "primitives.parquet"
    primitives.to_parquet(out, index=False)
    print(f">>> wrote {out} ({len(primitives):,} rows)", flush=True)

    # =========================================================
    # Per-phase threshold & ATR compact summary
    # =========================================================
    summary = (
        sess.groupby("phase_id", observed=True)
        .agg(
            n_rows=("window_return_pct", "size"),
            n_non_null=("window_return_pct", "count"),
            median_abs_return=("window_return_pct", lambda x: x.abs().median()),
            mean_return=("window_return_pct", "mean"),
            mean_range_pct=("window_range_pct", "mean"),
            phase_atr_pct=("phase_atr_pct", "first"),
            direction_threshold_pct=("direction_threshold_pct", "first"),
            n_up=("direction", lambda x: (x == "UP").sum()),
            n_down=("direction", lambda x: (x == "DOWN").sum()),
            n_flat=("direction", lambda x: (x == "FLAT").sum()),
        )
        .reset_index()
    )
    summary["phase_label"] = summary["phase_id"].map(dict(zip(phase["phase_id"], phase["phase_label"])))
    summary.to_csv(ARTIFACTS / "primitives_summary.csv", index=False)
    print(summary.to_string(index=False), flush=True)

    # =========================================================
    # Write definitions.md
    # =========================================================
    with open(ARTIFACTS / "definitions.md", "w") as f:
        f.write("# Definitions — primitives_engine.py\n\n")
        f.write("## Formulas (per directive §5)\n\n")
        f.write("- `window_return_pct = (close - open) / open * 100`\n")
        f.write("- `window_range_pct = (high - low) / open * 100`\n")
        f.write("- `direction_threshold_pct = 0.5 * median(|window_return_pct|) per phase` — regime-relative noise floor\n")
        f.write("- `direction ∈ {UP, DOWN, FLAT}` per above threshold (FLAT when |return| ≤ threshold)\n")
        f.write("- `magnitude_tier ∈ {Q1_0_25, Q2_25_50, Q3_50_75, Q4_75_90, Q5_90_100}` from pd.qcut on |return| within (phase × window); UNCLASSIFIED if n<5\n")
        f.write("- `leg = direction + magnitude_tier` (categorical token for sequential mining)\n")
        f.write("- `phase_atr_pct = mean(window_range_pct) within phase` (ATR-equivalent)\n")
        f.write("- `magnitude_pctile = rank(|return|, pct=True) within phase × window`\n\n")
        f.write("## Aggregation level\n\n")
        f.write("- One row per `(trade_date, symbol, session_window)` in `*_session_windows_summary.csv`\n")
        f.write("- One row per 5m/15m/60m bar in `*_5m/15m/60m_ist.csv` (with leg = INTRADAY_BAR)\n")
        f.write("- One row per day in `*_daily_ist.csv` (with leg = DAILY_BAR)\n\n")
        f.write("## Source\n\n")
        f.write("Directive README v3 §5 (analytical primitives).\n")
    print(">>> wrote definitions.md", flush=True)


if __name__ == "__main__":
    main()
