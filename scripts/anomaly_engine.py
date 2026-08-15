"""anomaly_engine.py — Step 7 of the directive.

Detect anomalies via rolling z-scores of volatility and volume.
Flag rows with |z| > 2.5; write ONLY flagged rows to anomalies.csv.

The directive says: 'Only for those flagged dates, run targeted web searches
to correlate with geopolitical news.' We do the statistical filter here; the
news correlation is a separate pass.
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats as scistats

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"


Z_THRESHOLD = 2.5
ROLLING_WINDOW = 20  # sessions
# Use rolling z-scores only (not global); global z overweights the mean by extreme values
USE_GLOBAL_Z = False


def main():
    print(">>> anomaly_engine.py starting", flush=True)
    master = pd.read_parquet(ARTIFACTS / "clean_master.parquet")

    # Work at the DAILY level (more tractable, plus phase-level is sufficient for z-score detection)
    daily = master[master["__stream"].isin(["WTI_daily", "BRENT_daily"])].copy()
    daily = daily.sort_values(["__stream", "trade_date_ist"]).reset_index(drop=True)

    # Need realized_vol_proxy. The data has it but only in INR. Build native version.
    # realized_vol_proxy in source = std(intraday 1m returns) * sqrt(n) * 100 — already computed
    # If not available, recompute from intraday
    print(f">>> daily rows: {len(daily):,}", flush=True)

    # Convert to per-stream daily series
    anomalies = []
    for stream in daily["__stream"].unique():
        sub = daily[daily["__stream"] == stream].sort_values("trade_date_ist").copy()
        # Use realized_vol_proxy from the data; if missing/NaN, fall back to (high-low)/open
        if "realized_vol_proxy" in sub.columns:
            sub["vol_native"] = sub["realized_vol_proxy"].fillna(
                (sub["high_native"] - sub["low_native"]) / sub["open_native"] * 100.0
            )
        else:
            sub["vol_native"] = (sub["high_native"] - sub["low_native"]) / sub["open_native"] * 100.0

        # Use body_pct_native for "move magnitude"
        if "body_pct_native" in sub.columns:
            sub["move_native"] = sub["body_pct_native"].abs().fillna(sub["vol_native"] * 0.5)
        else:
            sub["move_native"] = sub["vol_native"] * 0.5

        # Use mfe_pct or mae_pct for adverse/favorable excursion
        sub["abs_excursion"] = np.maximum(
            sub.get("mfe_pct", pd.Series(0, index=sub.index)).abs(),
            sub.get("mae_pct", pd.Series(0, index=sub.index)).abs()
        ).fillna(0)

        # Volume series (may be NaN for some)
        if "volume" in sub.columns:
            sub["volume_series"] = sub["volume"].fillna(0)
        else:
            sub["volume_series"] = np.nan

        # Compute rolling z-scores for each metric
        metric_cols = ["vol_native", "move_native", "abs_excursion", "volume_series"]
        for col in metric_cols:
            v = sub[col]
            if v.isna().all():
                continue
            # Rolling z: (x - rolling_mean) / rolling_std
            rmean = v.rolling(ROLLING_WINDOW, min_periods=5).mean()
            rstd = v.rolling(ROLLING_WINDOW, min_periods=5).std()
            z = (v - rmean) / rstd.replace(0, np.nan)
            sub[f"{col}_rolling_z"] = z

        # Compute global z-scores as fallback (scipy zscore)
        if USE_GLOBAL_Z:
            for col in ["vol_native", "move_native", "abs_excursion", "volume_series"]:
                v = sub[col].dropna()
                if len(v) > 2:
                    global_z = scistats.zscore(v, nan_policy="omit")
                    sub.loc[v.index, f"{col}_global_z"] = global_z

        # Flag anomalies: any |rolling_z| > threshold
        z_cols = [c for c in sub.columns if c.endswith("_rolling_z")]
        if USE_GLOBAL_Z:
            z_cols = z_cols + [c for c in sub.columns if c.endswith("_global_z")]
        for col in z_cols:
            flagged = sub[sub[col].abs() > Z_THRESHOLD].copy()
            if flagged.empty:
                continue
            flagged["anomaly_metric"] = col
            flagged["z_value"] = flagged[col]
            flagged = flagged[["__stream", "trade_date_ist", "phase_id", "phase_label",
                                "vol_native", "move_native", "abs_excursion", "volume_series",
                                "anomaly_metric", "z_value"]]
            anomalies.append(flagged)

    if not anomalies:
        print(">>> No anomalies flagged.", flush=True)
        anomalies_df = pd.DataFrame()
    else:
        anomalies_df = pd.concat(anomalies, ignore_index=True)

    # Deduplicate per (date, stream) — keep highest |z|
    if not anomalies_df.empty:
        anomalies_df["abs_z"] = anomalies_df["z_value"].abs()
        anomalies_df = anomalies_df.sort_values("abs_z", ascending=False).drop_duplicates(
            subset=["__stream", "trade_date_ist"], keep="first"
        ).reset_index(drop=True)
        anomalies_df = anomalies_df.drop(columns=["abs_z"])
        # Sort by date for output
        anomalies_df = anomalies_df.sort_values(["trade_date_ist", "__stream"]).reset_index(drop=True)

    anomalies_df.to_csv(ARTIFACTS / "anomalies.csv", index=False)
    print(f">>> wrote anomalies.csv ({len(anomalies_df)} flagged rows)", flush=True)

    # Compact summary by phase
    if not anomalies_df.empty:
        summary = anomalies_df.groupby("phase_id").size().reset_index(name="n_anomalies")
        summary["pct_of_phase_dates"] = summary["n_anomalies"] / summary["phase_id"].map(
            {1: 26, 2: 46, 3: 4, 4: 5, 5: 12, 6: 8}
        ) * 100
        summary.to_csv(ARTIFACTS / "anomaly_summary.csv", index=False)
        print(summary.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()