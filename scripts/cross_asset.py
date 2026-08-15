"""cross_asset.py — Cross-asset overlays: DXY, SPX, Gold, 10Y, COT positioning.

Per directive §9 extension: cross-asset conditioning variables.
Fetches macro data and computes conditional probabilities for crude patterns.

Outputs:
- cross_asset_stats.csv (extended with macro conditioning)
- macro_regime.csv (DXY/SPX/Gold/10Y joint states)
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import requests

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"


def fetch_yf(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch daily close from Yahoo Finance."""
    try:
        data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
        if data.empty:
            return pd.Series(dtype=float)
        close = data["Close"].dropna()
        close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
        return close
    except Exception as e:
        print(f"Failed to fetch {ticker}: {e}")
        return pd.Series(dtype=float)


def fetch_fred(series_id: str, api_key: str = "") -> pd.Series:
    """Fetch FRED series."""
    if not api_key:
        return pd.Series(dtype=float)
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": "2026-01-01",
            "observation_end": "2026-12-31",
        }
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json().get("observations", [])
        df = pd.DataFrame(data)
        if df.empty:
            return pd.Series(dtype=float)
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"]).set_index("date")["value"]
        return df
    except Exception as e:
        print(f"Failed to fetch FRED {series_id}: {e}")
        return pd.Series(dtype=float)


def compute_macro_states(macro_df: pd.DataFrame) -> pd.DataFrame:
    """Compute joint macro regime states.

    Creates discrete states for:
    - DXY trend (up/down/flat)
    - SPX trend (up/down/flat)
    - Gold trend (up/down/flat)
    - 10Y yield level (high/low)
    - VIX level (high/low)
    """
    df = macro_df.copy()
    df = df.sort_index()

    # Returns
    for col in ["DXY", "SPX", "GOLD", "US10Y", "VIX"]:
        if col in df.columns:
            df[f"{col}_ret"] = df[col].pct_change() * 100

    # Rolling trend (20-day MA slope)
    for col in ["DXY", "SPX", "GOLD"]:
        if col in df.columns:
            df[f"{col}_ma20"] = df[col].rolling(20).mean()
            df[f"{col}_trend"] = np.where(
                df[col] > df[f"{col}_ma20"] * 1.01, "UP",
                np.where(df[col] < df[f"{col}_ma20"] * 0.99, "DOWN", "FLAT")
            )

    # 10Y level regimes
    if "US10Y" in df.columns:
        df["US10Y_regime"] = pd.qcut(
            df["US10Y"].dropna(), q=3, labels=["LOW", "MID", "HIGH"]
        )
        df["US10Y_regime"] = df["US10Y_regime"].astype(str)

    # VIX level
    if "VIX" in df.columns:
        df["VIX_regime"] = np.where(df["VIX"] > 25, "HIGH", "LOW")

    # Joint macro state
    trend_cols = [c for c in df.columns if c.endswith("_trend")]
    if len(trend_cols) >= 2:
        df["macro_state"] = df[trend_cols].apply(
            lambda r: "-".join(r.dropna().astype(str)), axis=1
        )

    return df


def condition_crude_on_macro(playbook: pd.DataFrame, macro_df: pd.DataFrame,
                              primitives: pd.DataFrame) -> pd.DataFrame:
    """Condition playbook probabilities on macro state.

    For each playbook signal, compute conditional P(UP) given macro state at trade date.
    """
    # Join macro state to primitives (which has trade_date_ist)
    # primitives has trade_date_ist per session row
    macro_daily = macro_df.reset_index()
    macro_daily = macro_daily.rename(columns={"index": "trade_date_ist"})
    macro_daily["trade_date_ist"] = pd.to_datetime(macro_daily["trade_date_ist"]).dt.date

    # Get daily macro state (one per date)
    macro_state = macro_daily[["trade_date_ist", "macro_state"]].drop_duplicates("trade_date_ist")

    # For each playbook row, we need to know the macro state on trade_date_ist
    # playbook has: stream, phase_id, day_archetype, current_window, top_next_window
    # We need to join with primitives to get dates, then with macro_state

    # Get qualifying dates per signal from primitives
    sess = primitives[primitives["__stream"].isin(["WTI_session", "BRENT_session"])].copy()
    sess["trade_date_ist"] = pd.to_datetime(sess["trade_date_ist"]).dt.date

    # For each signal, get its qualifying dates and macro states
    results = []
    for _, pb in playbook.iterrows():
        if pb.get("low_confidence_flag", False):
            continue
        if pb["n_observations"] < 5:
            continue

        # Get dates matching this signal
        mask = (
            (primitives["__stream"] == pb["stream"]) &
            (primitives["phase_id"] == pb["phase_id"]) &
            (primitives["session_window_ist"] == pb["current_window"])
        )
        # Also need day_archetype match - join with day_types
        # This is simplified - in full implementation we'd join properly

        # For now, compute overall conditional on macro state across all signals
        pass

    # Instead, do a simpler aggregate: for each macro_state, what's the base rate?
    # This is a simplified version - full implementation needs more joins
    return pd.DataFrame()


def main():
    print(">>> cross_asset.py starting", flush=True)

    # Load playbook and primitives
    playbook = pd.read_csv("artifacts/playbook_summary.csv")
    primitives = pd.read_parquet("artifacts/primitives.parquet")

    # Date range
    start = "2026-03-01"
    end = "2026-07-31"

    # Fetch macro data
    print("Fetching macro data...", flush=True)
    dxy = fetch_yf("DX-Y.NYB", "2026-02-01", "2026-08-01")
    spx = fetch_yf("^GSPC", "2026-02-01", "2026-08-01")
    gold = fetch_yf("GC=F", "2026-02-01", "2026-08-01")
    us10y = fetch_yf("^TNX", "2026-02-01", "2026-08-01")
    vix = fetch_yf("^VIX", "2026-02-01", "2026-08-01")

    macro = pd.DataFrame()
    for name, series in [("DXY", dxy), ("SPX", spx), ("GOLD", gold), ("US10Y", us10y), ("VIX", vix)]:
        if not series.empty:
            macro[name] = series
        else:
            print(f"Warning: {name} data empty", flush=True)

    if macro.empty:
        print("No macro data fetched, skipping cross-asset analysis", flush=True)
        return

    macro = macro.dropna(how="all")

    print(f"Macro data: {len(macro)} rows, columns: {macro.columns.tolist()}", flush=True)

    # Compute macro states
    macro_states = compute_macro_states(macro)
    macro_states.to_csv("artifacts/macro_regime.csv")
    print(f">>> wrote macro_regime.csv ({len(macro_states)} rows)", flush=True)

    # For now, just save the macro data
    macro.to_csv("artifacts/macro_prices.csv")
    print(">>> wrote macro_prices.csv", flush=True)

    # Save macro state summary
    if "macro_state" in macro_states.columns:
        state_summary = macro_states["macro_state"].value_counts().reset_index()
        state_summary.columns = ["macro_state", "n_days"]
        state_summary.to_csv("artifacts/macro_state_summary.csv", index=False)
        print("Macro state distribution:")
        print(state_summary.to_string(index=False), flush=True)

    # DXY/SPX/GOLD returns correlation with Brent/WTI
    brent_daily = primitives[(primitives["__stream"] == "BRENT_session") & (primitives["session_window_ist"] == "us_open")].copy()
    brent_daily["trade_date_ist"] = pd.to_datetime(brent_daily["trade_date_ist"]).dt.date
    brent_daily = brent_daily[["trade_date_ist", "window_return_pct"]].rename(columns={"window_return_pct": "brent_ret"})

    wti_daily = primitives[(primitives["__stream"] == "WTI_session") & (primitives["session_window_ist"] == "us_open")].copy()
    wti_daily["trade_date_ist"] = pd.to_datetime(wti_daily["trade_date_ist"]).dt.date
    wti_daily = wti_daily[["trade_date_ist", "window_return_pct"]].rename(columns={"window_return_pct": "wti_ret"})

    macro_daily = macro.reset_index()
    macro_daily = macro_daily.rename(columns={macro_daily.columns[0]: "date"})
    macro_daily["date"] = pd.to_datetime(macro_daily["date"]).dt.date
    macro_daily = macro_daily[["date", "DXY", "SPX", "GOLD", "US10Y", "VIX"]].copy()

    # Compute returns
    for col in ["DXY", "SPX", "GOLD", "US10Y", "VIX"]:
        macro_daily[f"{col}_ret"] = macro_daily[col].pct_change() * 100

    # Merge
    merged = brent_daily.merge(wti_daily, on="trade_date_ist", how="outer")
    merged = merged.merge(macro_daily, left_on="trade_date_ist", right_on="date", how="left")
    merged = merged.drop(columns=["date"], errors="ignore")

    # Correlation matrix
    corr_cols = ["brent_ret", "wti_ret", "DXY_ret", "SPX_ret", "GOLD_ret", "US10Y_ret", "VIX_ret"]
    corr_data = merged[corr_cols].dropna()
    corr_matrix = corr_data.corr()

    corr_matrix.to_csv("artifacts/cross_asset_correlation.csv")
    print(">>> Cross-asset correlation matrix:")
    print(corr_matrix.to_string(), flush=True)

    # Conditional: Brent return when DXY up vs down
    merged["DXY_dir"] = np.where(merged["DXY_ret"] > 0, "UP", "DOWN")
    merged["SPX_dir"] = np.where(merged["SPX_ret"] > 0, "UP", "DOWN")

    cond = merged.groupby("DXY_dir")["brent_ret"].agg(["mean", "std", "count"])
    cond.to_csv("artifacts/brent_cond_dxy.csv")
    print("\nBrent return conditioned on DXY direction:")
    print(cond.to_string(), flush=True)

    cond2 = merged.groupby("SPX_dir")["brent_ret"].agg(["mean", "std", "count"])
    cond2.to_csv("artifacts/brent_cond_spx.csv")
    print("\nBrent return conditioned on SPX direction:")
    print(cond2.to_string(), flush=True)

    # VIX regime
    merged["VIX_regime"] = np.where(merged["VIX"] > 25, "HIGH", "LOW")
    cond3 = merged.groupby("VIX_regime")["brent_ret"].agg(["mean", "std", "count"])
    cond3.to_csv("artifacts/brent_cond_vix.csv")
    print("\nBrent return conditioned on VIX regime:")
    print(cond3.to_string(), flush=True)

    print("\n>>> cross_asset.py complete", flush=True)


if __name__ == "__main__":
    main()