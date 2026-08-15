"""cross_factor_engine.py — Step 9 of the directive.

Tests:
  1. Brent vs WTI spot lead-lag — does one's window move precede the other's?
  2. Wednesday EIA inventory day effect
  3. Weekly structure (Monday, Friday)
  4. OPEC+ meeting calendar effect
  5. Contract roll/expiry proximity

Outputs:
  - cross_factor_stats.csv
  - opec_calendar.csv (already produced in Step 0)
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"


def main():
    print(">>> cross_factor_engine.py starting", flush=True)
    p = pd.read_parquet(ARTIFACTS / "primitives.parquet")
    # Daily master is XLSX-as-CSV, use helper (stable location: scripts/_xlsx_helper.py)
    from _xlsx_helper import read_csv_as_xlsx

    daily_master = read_csv_as_xlsx(BASE / "daily_master_summary.csv")
    opec = pd.read_csv(ARTIFACTS / "opec_calendar.csv")

    # =========================================================
    # Test 1: Brent vs WTI lead-lag at session level
    # =========================================================
    sess = p[p["__stream"].isin(["WTI_session", "BRENT_session"])].copy()
    WINDOW_ORDER = [
        "asia_early", "us_late", "global_reopen_pre_mcx", "mcx_open_drive",
        "india_morning", "india_midday", "europe_midday", "us_pre_open",
        "us_open", "mcx_tail",
    ]
    sess["_win_rank"] = sess["session_window_ist"].map({w: i for i, w in enumerate(WINDOW_ORDER)})
    sess = sess.sort_values(["__stream", "trade_date_ist", "_win_rank"])

    # Pivot to wide: one row per (date, window_rank) with WTI & BRENT return columns
    wide = sess.pivot_table(
        index=["trade_date_ist", "session_window_ist", "_win_rank"],
        columns="__stream",
        values="window_return_pct",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None

    lead_lag_rows = []
    for lag in [-2, -1, 0, 1, 2]:
        # WTI leads BRENT by 'lag' sessions
        wide_sorted = wide.sort_values(["trade_date_ist", "_win_rank"]).copy()
        # For WTI leads BRENT by 1: corr(WTI return[t], BRENT return[t+1])
        if lag > 0:
            wide_sorted["brent_lag"] = wide_sorted.groupby("trade_date_ist")["BRENT_session"].shift(-lag)
            x = wide_sorted["WTI_session"]
            y = wide_sorted["brent_lag"]
            label = f"WTI leads BRENT by {lag} window(s)"
        elif lag < 0:
            wide_sorted["wti_lag"] = wide_sorted.groupby("trade_date_ist")["WTI_session"].shift(lag)
            x = wide_sorted["wti_lag"]
            y = wide_sorted["BRENT_session"]
            label = f"BRENT leads WTI by {-lag} window(s)"
        else:
            x = wide_sorted["WTI_session"]
            y = wide_sorted["BRENT_session"]
            label = "Contemporaneous"
        valid = x.notna() & y.notna()
        if valid.sum() < 5:
            continue
        corr, pval = stats.pearsonr(x[valid], y[valid])
        lead_lag_rows.append({
            "test": "lead_lag_window",
            "lag_windows": lag,
            "label": label,
            "n": int(valid.sum()),
            "corr": corr,
            "p_value": pval,
            "low_confidence_flag": valid.sum() < 5,
        })

    # Lead-lag at daily level
    daily_wide = daily_master[["trade_date_ist", "wti_close_native", "brent_close_native", "wti_gap_pct", "brent_gap_pct", "wti_net_day_return_pct" if "wti_net_day_return_pct" in daily_master.columns else None]].copy()
    daily_wide = daily_wide.dropna(subset=["wti_close_native", "brent_close_native"])
    daily_wide["wti_ret"] = daily_wide["wti_close_native"].pct_change() * 100
    daily_wide["brent_ret"] = daily_wide["brent_close_native"].pct_change() * 100
    for lag in [-3, -2, -1, 0, 1, 2, 3]:
        if lag > 0:
            daily_wide["brent_lag"] = daily_wide["brent_ret"].shift(-lag)
            x = daily_wide["wti_ret"]; y = daily_wide["brent_lag"]
        elif lag < 0:
            daily_wide["wti_lag"] = daily_wide["wti_ret"].shift(lag)
            x = daily_wide["wti_lag"]; y = daily_wide["brent_ret"]
        else:
            x = daily_wide["wti_ret"]; y = daily_wide["brent_ret"]
        valid = x.notna() & y.notna()
        if valid.sum() < 5:
            continue
        corr, pval = stats.pearsonr(x[valid], y[valid])
        lead_lag_rows.append({
            "test": "lead_lag_daily",
            "lag_days": lag,
            "label": f"WTI leads BRENT by {lag}d" if lag > 0 else (f"BRENT leads WTI by {-lag}d" if lag < 0 else "Contemporaneous"),
            "n": int(valid.sum()),
            "corr": corr,
            "p_value": pval,
            "low_confidence_flag": valid.sum() < 5,
        })

    lead_lag_df = pd.DataFrame(lead_lag_rows)

    # =========================================================
    # Test 2: Wednesday EIA effect
    # =========================================================
    daily_wide["trade_date_ist"] = pd.to_datetime(daily_wide["trade_date_ist"])
    daily_wide["is_wed"] = (daily_wide["trade_date_ist"].dt.dayofweek == 2).astype(int)

    # Need phase_id on daily_wide for proper phase filtering
    phase_lookup = pd.read_csv(ARTIFACTS / "phase_lookup.csv")
    daily_wide["trade_date_ist_dt"] = pd.to_datetime(daily_wide["trade_date_ist"])
    pl = phase_lookup.copy()
    pl["start_dt"] = pd.to_datetime(pl["start_datetime_ist"])
    pl["end_dt"] = pd.to_datetime(pl["end_datetime_ist"])
    daily_wide["phase_id"] = np.nan
    for _, prow in pl.iterrows():
        mask = (daily_wide["trade_date_ist_dt"] >= prow["start_dt"]) & (daily_wide["trade_date_ist_dt"] <= prow["end_dt"])
        daily_wide.loc[mask, "phase_id"] = prow["phase_id"]

    eia_rows = []
    for phase_id in [1, 2, 5, 6]:  # focus on substantive phases
        ph = daily_wide[daily_wide["phase_id"] == phase_id].copy()
        if len(ph) < 3:
            continue
        ph_wed = ph[ph["is_wed"] == 1]
        ph_nonwed = ph[ph["is_wed"] == 0]
        if len(ph_wed) < 2 or len(ph_nonwed) < 2:
            continue
        eia_rows.append({
            "test": "eia_wednesday",
            "phase_id": phase_id,
            "factor": "is_wed",
            "n": len(ph_wed),
            "mean_wti_ret": ph_wed["wti_ret"].mean(),
            "mean_brent_ret": ph_wed["brent_ret"].mean(),
            "std_wti_ret": ph_wed["wti_ret"].std(),
            "std_brent_ret": ph_wed["brent_ret"].std(),
        })
        eia_rows.append({
            "test": "eia_wednesday",
            "phase_id": phase_id,
            "factor": "non_wed",
            "n": len(ph_nonwed),
            "mean_wti_ret": ph_nonwed["wti_ret"].mean(),
            "mean_brent_ret": ph_nonwed["brent_ret"].mean(),
            "std_wti_ret": ph_nonwed["wti_ret"].std(),
            "std_brent_ret": ph_nonwed["brent_ret"].std(),
        })

    eia_df = pd.DataFrame(eia_rows)

    # =========================================================
    # Test 3: Monday / Friday weekly structure
    # =========================================================
    daily_wide["is_mon"] = (daily_wide["trade_date_ist"].dt.dayofweek == 0).astype(int)
    daily_wide["is_fri"] = (daily_wide["trade_date_ist"].dt.dayofweek == 4).astype(int)
    weekly_rows = []
    for dayname, col in [("monday", "is_mon"), ("friday", "is_fri"), ("other", None)]:
        if col:
            sub = daily_wide[daily_wide[col] == 1]
        else:
            sub = daily_wide[(daily_wide["is_mon"] == 0) & (daily_wide["is_fri"] == 0)]
        if len(sub) < 5:
            continue
        weekly_rows.append({
            "test": "weekly_structure",
            "phase_id": 0,
            "factor": dayname,
            "n": len(sub),
            "mean_wti_ret": sub["wti_ret"].mean(),
            "mean_brent_ret": sub["brent_ret"].mean(),
            "std_wti_ret": sub["wti_ret"].std(),
            "std_brent_ret": sub["brent_ret"].std(),
        })
    weekly_df = pd.DataFrame(weekly_rows)

    # =========================================================
    # Test 4: OPEC+ meeting day effect
    # =========================================================
    opec["meeting_date"] = pd.to_datetime(opec["meeting_date"])
    daily_wide["opec_meeting_day"] = daily_wide["trade_date_ist"].isin(opec["meeting_date"]).astype(int)
    opec_rows = []
    for is_meeting in [0, 1]:
        sub = daily_wide[daily_wide["opec_meeting_day"] == is_meeting]
        if len(sub) < 3:
            continue
        opec_rows.append({
            "test": "opec_meeting_day",
            "phase_id": 0,
            "factor": "opec_meeting_day" if is_meeting else "non_opec_day",
            "n": len(sub),
            "mean_wti_ret": sub["wti_ret"].mean(),
            "mean_brent_ret": sub["brent_ret"].mean(),
            "std_wti_ret": sub["wti_ret"].std(),
            "std_brent_ret": sub["brent_ret"].std(),
        })
    opec_df = pd.DataFrame(opec_rows)

    # =========================================================
    # Combine & write
    # =========================================================
    out = pd.concat([lead_lag_df, eia_df, weekly_df, opec_df], ignore_index=True, sort=False)
    out.to_csv(ARTIFACTS / "cross_factor_stats.csv", index=False)
    print(f">>> wrote cross_factor_stats.csv ({len(out)} rows)", flush=True)

    # Lead-lag summary
    print("\nLead-lag results:", flush=True)
    print(lead_lag_df.to_string(index=False), flush=True)

    print("\nEIA Wed effect:", flush=True)
    print(eia_df.to_string(index=False), flush=True)

    print("\nWeekly structure:", flush=True)
    print(weekly_df.to_string(index=False), flush=True)

    print("\nOPEC+ meeting day effect:", flush=True)
    print(opec_df.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
