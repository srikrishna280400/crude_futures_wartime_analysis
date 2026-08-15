"""data_validator.py — Step 1 of the directive.

Performs ingestion, normalization, IST conversion, time-window reclassification,
phase tagging, day-type tagging, and column pruning. Outputs:
  - clean_master.parquet  (lossless cleaned dataset)
  - phase_lookup.csv      (already produced by Step 0; copied here as join key)
  - pruning_log.md        (what was dropped and why)

Direction §2.2 mandates:
  - Read raw data only inside the script, never paste into reasoning context
  - Prune only invariant columns (and only after confirming)
  - Vectorized window assignment via pd.cut
  - Phase tagging via pd.merge_asof against phase_lookup.csv
  - Output parquet for downstream engines
"""

from __future__ import annotations

import os
import sys
import tempfile
import shutil
from pathlib import Path
import pandas as pd
import numpy as np

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

# Directive's canonical time windows (IST). Per README §4.
WINDOWS = [
    ("asia_early",        1.5, 3.5),    # 01:30–03:30 (CME/Globex halt gap documented as such)
    ("global_reopen_pre_mcx", 3.5, 9.0),   # 03:30–09:00
    ("mcx_open_drive",    9.0, 10.5),   # 09:00–10:30
    ("india_morning",    10.5, 12.5),   # 10:30–12:30
    ("india_midday",     12.5, 15.5),   # 12:30–15:30
    ("europe_midday",    15.5, 18.0),   # 15:30–18:00 (covers data's europe_open 15:30–17:30)
    ("us_pre_open",      18.0, 20.0),   # 18:00–20:00 (covers data's europe_mid 17:30–20:00)
    ("us_open",          20.0, 23.0),   # 20:00–23:00 (covers data's us_pre_open 20:00–21:00 + us_open 21:00–23:00)
    ("mcx_tail",         23.0, 24.0),   # 23:00–00:00
    ("us_late",           0.0, 1.5),    # 00:00–01:30
]
WINDOW_ORDER = [w[0] for w in WINDOWS] + ["other_valid_hours"]
WINDOW_RANK = {n: i for i, n in enumerate(WINDOW_ORDER)}


# ----------------------------------------------------------------------
# XLSX-as-CSV helper (data files in this repo are XLSX with .csv ext)
# ----------------------------------------------------------------------
from _xlsx_helper import read_csv_as_xlsx as read_xlsx_as_csv


# ----------------------------------------------------------------------
# Time-window reassignment from raw timestamp
# ----------------------------------------------------------------------
def assign_window_ist(ts_ist: pd.Series) -> pd.Series:
    """Vectorized window assignment per directive §4 table."""
    # hour as float: 0-24
    h = ts_ist.dt.hour.astype(float) + ts_ist.dt.minute.astype(float) / 60.0
    out = pd.Series("other_valid_hours", index=ts_ist.index, dtype=object)
    for name, a, b in WINDOWS:
        if a < b:
            mask = (h >= a) & (h < b)
        else:  # wraps midnight (e.g. 23:00-24:00 is single-ended; us_late 0-1.5)
            mask = (h >= a) | (h < b)
        out = out.mask(mask, name)
    return out


# ----------------------------------------------------------------------
# Ingestion per file
# ----------------------------------------------------------------------
FILES = {
    "WTI_5m":   "wti_5m_ist.csv",
    "WTI_15m":  "wti_15m_ist.csv",
    "WTI_60m":  "wti_60m_ist.csv",
    "WTI_daily":"wti_daily_ist.csv",
    "BRENT_5m":   "brent_5m_ist.csv",
    "BRENT_15m":  "brent_15m_ist.csv",
    "BRENT_60m":  "brent_60m_ist.csv",
    "BRENT_daily":"brent_daily_ist.csv",
}


def load_one(name: str, fname: str) -> pd.DataFrame:
    df = read_xlsx_as_csv(BASE / fname)
    df["__source_file"] = fname
    df["__stream"] = name
    if "session_window_ist" not in df.columns:
        # This is intraday or daily. Build timestamp from existing ts or daily key.
        if "timestamp_ist" in df.columns:
            ts = pd.to_datetime(df["timestamp_ist"], errors="coerce")
        elif "trade_date_ist" in df.columns:
            ts = pd.to_datetime(df["trade_date_ist"], errors="coerce")
        else:
            ts = pd.Series([pd.NaT] * len(df))
        df["timestamp_ist"] = ts
        df["session_window_ist"] = assign_window_ist(ts)
    else:
        # session_windows_summary has its own session_window_ist label
        # but re-classify to use canonical directive naming for consistency.
        old_to_new = {
            "europe_open": "europe_midday",
            "europe_mid": "us_pre_open",     # 17:30-20:00 IST; directive's us_pre_open is 18:00-20:00
            "us_pre_open": "us_open",         # 20-21 IST is part of directive's us_open (20-23)
            "us_open": "us_open",             # 21-23 IST is the second half of us_open; rolled together
            "global_reopen_pre_mcx": "global_reopen_pre_mcx",
            "mcx_open_drive": "mcx_open_drive",
            "india_morning": "india_morning",
            "india_midday": "india_midday",
            "mcx_tail": "mcx_tail",
            "us_late": "us_late",
            "asia_early": "asia_early",
            "other_valid_hours": "other_valid_hours",
        }
        df["session_window_ist"] = df["session_window_ist"].map(old_to_new).fillna(df["session_window_ist"])
    df["trade_date_ist"] = pd.to_datetime(df["trade_date_ist"], errors="coerce")
    df["timestamp_ist"] = pd.to_datetime(df["timestamp_ist"], errors="coerce")

    # FIX: WTI_60m has column misalignment in last ~48 rows (newly added Aug 3-5 dates)
    # where source_timezone ('UTC') shifted into open_native, causing dtype=object.
    # Fix by detecting corrupted rows (open_native == 'UTC') and resampling from WTI_5m.
    if name == "WTI_60m":
        mask_utc = df["open_native"] == "UTC"
        if mask_utc.any():
            print(f"  FIXING WTI_60m: {mask_utc.sum()} corrupted rows detected (open_native='UTC'), resampling from WTI_5m...", flush=True)
            # Load WTI_5m data to resample for the affected date range
            wti_5m_path = BASE / "wti_5m_ist.csv"
            if wti_5m_path.exists():
                wti_5m = read_xlsx_as_csv(wti_5m_path)
                wti_5m["timestamp_ist"] = pd.to_datetime(wti_5m["timestamp_ist"], errors="coerce")
                wti_5m["trade_date_ist"] = pd.to_datetime(wti_5m["trade_date_ist"], errors="coerce")

                # Get affected date range
                corrupted_dates = df.loc[mask_utc, "trade_date_ist"].dropna().unique()
                if len(corrupted_dates) > 0:
                    # Filter 5m data for affected dates
                    wti_5m_affected = wti_5m[wti_5m["trade_date_ist"].isin(corrupted_dates)].copy()
                    if len(wti_5m_affected) > 0:
                        # Resample 5m to 60m
                        wti_5m_affected = wti_5m_affected.sort_values("timestamp_ist")
                        wti_5m_affected = wti_5m_affected.set_index("timestamp_ist")

                        # Resample to 60m OHLCV
                        ohlcv = wti_5m_affected.groupby([pd.Grouper(freq="60min"), "trade_date_ist"]).agg({
                            "open_native": "first",
                            "high_native": "max",
                            "low_native": "min",
                            "close_native": "last",
                            "volume": "sum",
                            "timestamp_original": "first",
                            "instrument_name": "first",
                            "timeframe": "first",
                            "source_resolution_used": "first",
                            "source_resolution_minutes": "first",
                            "currency_native": "first",
                            "source_timezone": "first",
                        }).reset_index()

                        # Replace corrupted rows in df
                        df = df[~mask_utc].copy()
                        # Ensure same columns
                        for c in df.columns:
                            if c not in ohlcv.columns:
                                ohlcv[c] = np.nan
                        ohlcv = ohlcv[df.columns]
                        df = pd.concat([df, ohlcv], ignore_index=True)
                        df = df.sort_values("timestamp_ist").reset_index(drop=True)
                        print(f"  Replaced {mask_utc.sum()} corrupted WTI_60m rows with resampled 5m->60m data", flush=True)

    df["trade_date_ist"] = pd.to_datetime(df["trade_date_ist"], errors="coerce")
    df["timestamp_ist"] = pd.to_datetime(df["timestamp_ist"], errors="coerce")
    return df


def main():
    print(">>> data_validator.py starting", flush=True)

    # ---- Load all data ----
    frames: list[pd.DataFrame] = []
    for name, fname in FILES.items():
        path = BASE / fname
        if not path.exists():
            print(f"  skip missing: {fname}", flush=True)
            continue
        print(f"  load {fname}", flush=True)
        df = load_one(name, fname)
        frames.append(df)
        print(f"    rows={len(df):,}  cols={len(df.columns)}", flush=True)

    # ---- Load session_windows_summary (already has window labels) ----
    for fname in ("wti_session_windows_summary.csv", "brent_session_windows_summary.csv"):
        path = BASE / fname
        if not path.exists():
            continue
        print(f"  load {fname}", flush=True)
        df = read_xlsx_as_csv(path)
        df["__source_file"] = fname
        df["__stream"] = "WTI_session" if fname.startswith("wti") else "BRENT_session"
        df["timestamp_ist"] = pd.to_datetime(df["trade_date_ist"], errors="coerce")
        df["trade_date_ist"] = pd.to_datetime(df["trade_date_ist"], errors="coerce")
        # Window re-mapping (data has different label conventions)
        old_to_new = {
            "europe_open": "europe_midday",
            "europe_mid": "us_pre_open",
            "us_pre_open": "us_open",
            "us_open": "us_open",
            "global_reopen_pre_mcx": "global_reopen_pre_mcx",
            "mcx_open_drive": "mcx_open_drive",
            "india_morning": "india_morning",
            "india_midday": "india_midday",
            "mcx_tail": "mcx_tail",
            "us_late": "us_late",
            "asia_early": "asia_early",
            "other_valid_hours": "other_valid_hours",
        }
        if "session_window_ist" in df.columns:
            df["session_window_ist"] = df["session_window_ist"].map(old_to_new).fillna(df["session_window_ist"])
        else:
            df["session_window_ist"] = "session_summary"
        frames.append(df)
        print(f"    rows={len(df):,}  cols={len(df.columns)}", flush=True)

    if not frames:
        sys.exit("No frames loaded.")

    # ---- Union all rows (vertical stack), preserving per-file granularity ----
    # Pad columns to union of all column sets
    all_cols: list[str] = []
    for f in frames:
        for c in f.columns:
            if c not in all_cols:
                all_cols.append(c)
    aligned = []
    for f in frames:
        for c in all_cols:
            if c not in f.columns:
                f[c] = np.nan
        aligned.append(f[all_cols])
    master = pd.concat(aligned, ignore_index=True, sort=False)
    print(f"\n>>> master rows: {len(master):,}", flush=True)

    # ---- Phase tagging via join with phase_lookup.csv ----
    # Use trade_date_ist for daily-aligned rows; for intraday rows also use trade_date_ist
    phase_lookup = pd.read_csv(ARTIFACTS / "phase_lookup.csv")
    phase_lookup["start_date"] = pd.to_datetime(phase_lookup["start_datetime_ist"]).dt.date
    phase_lookup["end_date"] = pd.to_datetime(phase_lookup["end_datetime_ist"]).dt.date

    # Use merge_asof to tag every row by trade_date_ist
    master["_trade_date_sort"] = pd.to_datetime(master["trade_date_ist"]).dt.normalize()

    # Build a small sorted phase-key table for merge_asof
    pl_sorted = phase_lookup.sort_values("start_date")[["phase_id", "phase_label", "start_date", "end_date"]].copy()
    pl_sorted["start_date"] = pd.to_datetime(pl_sorted["start_date"])

    # Use merge_asof on start_date (then filter by end_date)
    # Drop rows with no trade_date (e.g. all-empty rows from padded columns)
    n_before = len(master)
    master = master[master["_trade_date_sort"].notna()].copy()
    print(f">>> dropped {n_before - len(master):,} rows with no trade_date", flush=True)
    # Both sides must be identical datetime64 dtype
    master = master.sort_values("_trade_date_sort").reset_index(drop=True)
    master["_trade_date_sort"] = master["_trade_date_sort"].astype("datetime64[us]")
    pl_sorted = pl_sorted.sort_values("start_date").reset_index(drop=True)
    pl_sorted["_trade_date_sort"] = pl_sorted["start_date"].astype("datetime64[us]")
    pl_sorted["end_date"] = pl_sorted["end_date"].astype("datetime64[us]")
    merged = pd.merge_asof(
        master,
        pl_sorted[["_trade_date_sort", "phase_id", "phase_label", "end_date"]],
        on="_trade_date_sort",
        direction="backward",
    )
    # Now restrict to rows where trade_date <= end_date of the matched phase
    merged["phase_id"] = merged["phase_id"].where(
        merged["_trade_date_sort"] <= merged["end_date"], other=np.nan
    )
    merged["phase_label"] = merged["phase_label"].where(
        merged["_trade_date_sort"] <= merged["end_date"], other=np.nan
    )
    merged = merged.drop(columns=["end_date"], errors="ignore")
    master = merged

    # ---- Day-type tags (weekday, EIA-Wed, days-to-expiry, etc.) ----
    td = pd.to_datetime(master["trade_date_ist"])
    master["weekday"] = td.dt.day_name()
    master["is_monday"] = (td.dt.dayofweek == 0).astype(int)
    master["is_friday"] = (td.dt.dayofweek == 4).astype(int)
    master["is_wednesday_eia_day"] = (td.dt.dayofweek == 2).astype(int)

    # ---- Column pruning per Section 2.2 rule ----
    # Prune only columns confirmed invariant across the full dataset.
    pruning_log: list[str] = []
    n = len(master)
    drop_cols: list[str] = []
    keep_invariant_candidate: list[str] = []
    for c in master.columns:
        if c in ("__source_file", "__stream", "_trade_date_sort"):
            continue
        nunq = master[c].nunique(dropna=True)
        if nunq <= 1 and master[c].notna().sum() > 0:
            drop_cols.append(c)
            pruning_log.append(f"  - {c}: only {nunq} unique non-null value(s) across {n} rows → DROP")
        elif master[c].isna().sum() == n:
            drop_cols.append(c)
            pruning_log.append(f"  - {c}: 100% NaN → DROP")
        elif nunq == 1 and master[c].isna().sum() == n:
            drop_cols.append(c)
    # NEVER prune: timestamp_ist, trade_date_ist, OHLC, volume, session_window_ist, phase_id, phase_label
    never_drop = {"timestamp_ist", "trade_date_ist", "open_native", "high_native", "low_native",
                  "close_native", "volume", "session_window_ist", "phase_id", "phase_label",
                  "data_quality_flags", "weekday", "is_monday", "is_friday",
                  "is_wednesday_eia_day", "instrument_name", "symbol", "__source_file", "__stream"}
    safe_drop = [c for c in drop_cols if c not in never_drop]
    master = master.drop(columns=safe_drop, errors="ignore")

    # ---- Dtypes optimization ----
    for c in master.columns:
        if master[c].dtype == object:
            # Only categorize if low cardinality
            nunq = master[c].nunique(dropna=True)
            if nunq <= 50:
                try:
                    master[c] = master[c].astype("category")
                except Exception:
                    pass

    # ---- Write parquet ----
    out = ARTIFACTS / "clean_master.parquet"
    master.to_parquet(out, index=False)
    print(f"\n>>> wrote {out} ({len(master):,} rows × {len(master.columns)} cols)", flush=True)

    # ---- Write pruning log ----
    log_path = ARTIFACTS / "pruning_log.md"
    with open(log_path, "w") as f:
        f.write("# Pruning log — data_validator.py\n\n")
        f.write(f"Total input rows after vertical union: {n:,}\n")
        f.write(f"Total input columns before pruning: {len(all_cols)}\n")
        f.write(f"Columns pruned: {len(safe_drop)}\n\n")
        f.write("## Dropped columns\n")
        for line in pruning_log:
            f.write(line + "\n")
        f.write("\n## Kept invariant candidates (must NOT drop):\n")
        f.write("- timestamp_ist, trade_date_ist (timestamps)\n")
        f.write("- open_native/high_native/low_native/close_native (OHLC)\n")
        f.write("- volume\n")
        f.write("- session_window_ist, phase_id, phase_label (downstream joins)\n")
        f.write("- data_quality_flags, weekday, is_monday, is_friday, is_wednesday_eia_day\n")
        f.write("- instrument_name, symbol, __source_file, __stream (auditability)\n")

    print(f">>> wrote {log_path}", flush=True)

    # ---- Summary stats per stream & per window ----
    summary = (
        master.groupby(["__stream", "session_window_ist"], observed=True)
        .size()
        .reset_index(name="rows")
        .sort_values(["__stream", "rows"], ascending=[True, False])
    )
    summary.to_csv(ARTIFACTS / "data_validator_summary.csv", index=False)
    print("\n>>> Stream × window row counts:", flush=True)
    print(summary.to_string(index=False), flush=True)

    # ---- Phase × stream counts ----
    phase_summary = (
        master.groupby("phase_id", observed=True)["__stream"]
        .value_counts()
        .reset_index(name="rows")
    )
    phase_summary.to_csv(ARTIFACTS / "data_validator_phase_summary.csv", index=False)
    print("\n>>> Phase × stream row counts:", flush=True)
    print(phase_summary.to_string(index=False), flush=True)

    return master


if __name__ == "__main__":
    main()
