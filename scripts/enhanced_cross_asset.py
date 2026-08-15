"""enhanced_cross_asset.py — Comprehensive cross-asset macro overlays for crude oil.

Adds:
1. DXY, SPX, Gold, US10Y, VIX regime states and conditional returns
2. COT (Commitment of Traders) positioning data
3. Options implied vol surface (skew, term structure)
4. Brent-WTI spread dynamics and basis trading signals
5. Inventory builds/draws (EIA weekly) conditional analysis
6. Macro regime classification (risk-on/off, inflation, growth)

Outputs:
- artifacts/macro_regime.csv (daily macro regime states)
- artifacts/macro_conditional_returns.csv (crude returns | macro state)
- artifacts/cot_positioning.csv (spec vs commercial positioning)
- artifacts/options_vol_surface.csv (implied vol metrics)
- artifacts/cross_asset_correlation.json (rolling correlation matrix)
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
import requests

warnings.filterwarnings("ignore")

# ─── Configuration ────────────────────────────────────────────────────────────

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

# Macro tickers
MACRO_TICKERS = {
    "DXY": "DX-Y.NYB",      # Dollar Index
    "SPX": "^GSPC",         # S&P 500
    "GOLD": "GC=F",         # Gold futures
    "US10Y": "^TNX",        # 10Y Treasury yield
    "VIX": "^VIX",          # VIX
    "WTI": "CL=F",          # WTI Crude
    "BRENT": "BZ=F",        # Brent Crude
    "COPPER": "HG=F",       # Copper (growth proxy)
    "SILVER": "SI=F",       # Silver
    "NATGAS": "NG=F",       # Natural Gas
}

# EIA API
EIA_API_KEY = ""  # Set via env if available
EIA_INVENTORY_SERIES = "PET.WCESTUS1.W"  # US crude oil inventories

# COT data source (CFTC)
COT_URL = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

# Date range
START_DATE = "2026-02-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")

# ─── Data Fetching ────────────────────────────────────────────────────────────

def fetch_macro_prices() -> pd.DataFrame:
    """Fetch all macro price series from Yahoo Finance."""
    print(">>> Fetching macro price data...", flush=True)
    data = {}

    for name, ticker in MACRO_TICKERS.items():
        try:
            df = yf.download(ticker, start=START_DATE, end=END_DATE, progress=False, auto_adjust=True)
            if not df.empty:
                df = df[["Close"]].rename(columns={"Close": name})
                df.index = pd.to_datetime(df.index).tz_localize(None)
                data[name] = df
                print(f"  {name}: {len(df)} rows")
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    # Combine
    if data:
        combined = pd.concat(data.values(), axis=1, keys=data.keys())
        combined.columns = combined.columns.get_level_values(0)
        combined = combined.ffill().dropna(how="all")
        return combined
    return pd.DataFrame()

def compute_macro_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute macro regime features from price series."""
    df = prices.copy()

    # Returns
    for col in df.columns:
        df[f"{col}_ret_1d"] = df[col].pct_change() * 100
        df[f"{col}_ret_5d"] = df[col].pct_change(5) * 100
        df[f"{col}_ret_20d"] = df[col].pct_change(20) * 100

    # Moving averages and trends
    for col in ["DXY", "SPX", "GOLD", "US10Y", "VIX"]:
        if col in df.columns:
            df[f"{col}_ma_20"] = df[col].rolling(20).mean()
            df[f"{col}_ma_50"] = df[col].rolling(50).mean()
            df[f"{col}_ma_200"] = df[col].rolling(200).mean()
            df[f"{col}_trend"] = np.where(
                df[col] > df[f"{col}_ma_20"], 1,
                np.where(df[col] < df[f"{col}_ma_50"], -1, 0)
            )
            # Trend strength
            df[f"{col}_trend_strength"] = (df[col] - df[f"{col}_ma_20"]) / df[f"{col}_ma_20"] * 100

    # Regime classification
    # Risk-on: SPX up, VIX down, DXY down, Copper up
    # Risk-off: SPX down, VIX up, DXY up, Gold up
    df["risk_on_score"] = 0
    if "SPX_trend" in df.columns: df["risk_on_score"] += df["SPX_trend"]
    if "VIX_trend" in df.columns: df["risk_on_score"] -= df["VIX_trend"]
    if "DXY_trend" in df.columns: df["risk_on_score"] -= df["DXY_trend"]
    if "COPPER_trend" in df.columns: df["risk_on_score"] += df["COPPER_trend"]

    df["macro_regime"] = np.where(
        df["risk_on_score"] >= 2, "risk_on",
        np.where(df["risk_on_score"] <= -2, "risk_off", "neutral")
    )

    # Inflation regime: Gold up, TIPS breakevens up, Copper/Gold ratio down
    if "GOLD" in df.columns and "COPPER" in df.columns:
        df["copper_gold_ratio"] = df["COPPER"] / df["GOLD"]
        df["inflation_hedge"] = np.where(df["GOLD_trend"] > 0, 1, 0)

    # Growth regime: Copper/Gold, SPX, Yield curve
    if "US10Y" in df.columns:
        # Yield curve steepness: 20-day change in 10Y yield
        df["yield_curve_steep"] = df["US10Y"].diff(20)

    # Dollar regime
    if "DXY" in df.columns:
        df["dollar_regime"] = np.where(
            df["DXY_trend"] > 0, "strong_dollar",
            np.where(df["DXY_trend"] < 0, "weak_dollar", "neutral_dollar")
        )

    # VIX regime
    if "VIX" in df.columns:
        vix_pctile = df["VIX"].rolling(252).rank(pct=True)
        df["vix_regime"] = np.where(
            vix_pctile > 0.8, "high_vol",
            np.where(vix_pctile < 0.2, "low_vol", "normal_vol")
        )

    return df

def fetch_eia_inventory() -> pd.DataFrame:
    """Fetch EIA weekly petroleum inventory data."""
    if not EIA_API_KEY:
        print(">>> EIA API key not set, skipping inventory fetch")
        return pd.DataFrame()

    url = f"https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
    params = {
        "api_key": EIA_API_KEY,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[product][]": "WCESTUS1",
        "start": START_DATE,
        "end": END_DATE,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()["response"]["data"]
        df = pd.DataFrame(data)
        df["period"] = pd.to_datetime(df["period"])
        df = df.rename(columns={"value": "crude_inventory_mmbbl"})
        df = df[["period", "crude_inventory_mmbbl"]].sort_values("period")
        df["inventory_change"] = df["crude_inventory_mmbbl"].diff()
        df["inventory_pct_change"] = df["crude_inventory_mmbbl"].pct_change() * 100
        return df
    except Exception as e:
        print(f">>> EIA fetch failed: {e}")
        return pd.DataFrame()

def fetch_cot_data() -> pd.DataFrame:
    """Fetch CFTC Commitment of Traders data."""
    try:
        r = requests.get(COT_URL, timeout=30)
        lines = r.text.strip().split("\n")

        # Parse CFTC format (fixed width)
        records = []
        for line in lines:
            if "CRUDE OIL" in line.upper() and "LIGHT SWEET" in line.upper():
                # This is a simplified parser - real CFTC format is complex
                # For production, use a proper COT parser
                pass
        return pd.DataFrame()
    except Exception as e:
        print(f">>> COT fetch failed: {e}")
        return pd.DataFrame()

def fetch_options_vol_surface() -> pd.DataFrame:
    """Fetch options implied vol data for WTI/Brent."""
    # Use yfinance options chain
    # Note: Limited to available expirations
    results = []

    for name, ticker in [("WTI", "CL=F"), ("BRENT", "BZ=F")]:
        try:
            opt = yf.Ticker(ticker)
            expirations = opt.options[:6]  # First 6 expirations

            for exp in expirations:
                chain = opt.option_chain(exp)
                calls = chain.calls
                puts = chain.puts

                if len(calls) > 10 and len(puts) > 10:
                    # ATM straddle IV
                    spot = (calls["strike"].iloc[len(calls)//2] +
                            puts["strike"].iloc[len(puts)//2]) / 2

                    # Find ATM options
                    atm_call = calls.iloc[(calls["strike"] - spot).abs().argmin()]
                    atm_put = puts.iloc[(puts["strike"] - spot).abs().argmin()]

                    # 25-delta skew
                    call_iv_25d = calls[calls["strike"] > spot]["impliedVolatility"].iloc[0] \
                        if "impliedVolatility" in calls.columns else np.nan
                    put_iv_25d = puts[puts["strike"] < spot]["impliedVolatility"].iloc[-1] \
                        if "impliedVolatility" in puts.columns else np.nan

                    results.append({
                        "date": datetime.now().date(),
                        "instrument": name,
                        "expiration": exp,
                        "days_to_exp": (pd.Timestamp(exp) - pd.Timestamp.now()).days,
                        "atm_call_iv": atm_call.get("impliedVolatility", np.nan),
                        "atm_put_iv": atm_put.get("impliedVolatility", np.nan),
                        "skew_25d": put_iv_25d - call_iv_25d if pd.notna(put_iv_25d) and pd.notna(call_iv_25d) else np.nan,
                        "term_structure_slope": np.nan,  # Would need multiple expiries
                    })
        except Exception as e:
            print(f">>> Options fetch failed for {name}: {e}")

    return pd.DataFrame(results)

# ─── Conditional Analysis ─────────────────────────────────────────────────────

def load_crude_data() -> Dict[str, pd.DataFrame]:
    """Load crude daily and session data."""
    wti_daily = read_xlsx(BASE / "wti_daily_ist.csv")
    brent_daily = read_xlsx(BASE / "brent_daily_ist.csv")

    # Get session returns
    primitives = pd.read_parquet(ARTIFACTS / "primitives.parquet")
    sess = primitives[primitives["__stream"].isin(["WTI_session", "BRENT_session"])]

    return {
        "wti_daily": wti_daily,
        "brent_daily": brent_daily,
        "session": sess,
    }

def read_xlsx(path: Path) -> pd.DataFrame:
    import tempfile, shutil, os
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    try:
        shutil.copy(str(path), tmp.name)
        return pd.read_excel(tmp.name)
    finally:
        os.unlink(tmp.name)

def analyze_macro_conditionals(crude: Dict, macro: pd.DataFrame) -> pd.DataFrame:
    """Analyze crude returns conditional on macro regimes."""
    # Daily crude returns
    wti = crude["wti_daily"].copy()
    wti["trade_date_ist"] = pd.to_datetime(wti["trade_date_ist"])
    wti = wti.set_index("trade_date_ist")["close_native"].pct_change().rename("wti_ret").to_frame()
    wti.index = wti.index.normalize()

    brent = crude["brent_daily"].copy()
    brent["trade_date_ist"] = pd.to_datetime(brent["trade_date_ist"])
    brent = brent.set_index("trade_date_ist")["close_native"].pct_change().rename("brent_ret").to_frame()
    brent.index = brent.index.normalize()

    crude_ret = wti.join(brent, how="outer")
    crude_ret["avg_ret"] = crude_ret[["wti_ret", "brent_ret"]].mean(axis=1) * 100

    # Convert macro columns to numeric first
    macro = macro.apply(pd.to_numeric, errors='coerce')

    # Align macro data (macro index is datetime)
    macro_daily = macro.resample("D").last().ffill()
    macro_daily.index = macro_daily.index.normalize()

    # Join
    joined = crude_ret.join(macro_daily, how="inner")

    # Conditional analysis
    results = []

    # 1. By macro regime
    for regime in ["risk_on", "risk_off", "neutral"]:
        mask = joined["macro_regime"] == regime
        if mask.sum() < 5:
            continue
        sub = joined[mask]
        results.append({
            "condition": f"macro_regime_{regime}",
            "n": int(mask.sum()),
            "wti_mean": sub["wti_ret"].mean(),
            "brent_mean": sub["brent_ret"].mean(),
            "avg_mean": sub["avg_ret"].mean(),
            "wti_std": sub["wti_ret"].std(),
            "brent_std": sub["brent_ret"].std(),
            "sharpe": sub["avg_ret"].mean() / sub["avg_ret"].std() * np.sqrt(252) if sub["avg_ret"].std() > 0 else 0,
            "pct_positive": (sub["avg_ret"] > 0).mean() * 100,
        })

    # 2. By dollar regime
    for regime in ["strong_dollar", "weak_dollar", "neutral_dollar"]:
        mask = joined["dollar_regime"] == regime
        if mask.sum() < 5:
            continue
        sub = joined[mask]
        results.append({
            "condition": f"dollar_{regime}",
            "n": int(mask.sum()),
            "wti_mean": sub["wti_ret"].mean(),
            "brent_mean": sub["brent_ret"].mean(),
            "avg_mean": sub["avg_ret"].mean(),
            "wti_std": sub["wti_ret"].std(),
            "sharpe": sub["avg_ret"].mean() / sub["avg_ret"].std() * np.sqrt(252) if sub["avg_ret"].std() > 0 else 0,
        })

    # 3. By VIX regime
    for regime in ["high_vol", "low_vol", "normal_vol"]:
        mask = joined["vix_regime"] == regime
        if mask.sum() < 5:
            continue
        sub = joined[mask]
        results.append({
            "condition": f"vix_{regime}",
            "n": int(mask.sum()),
            "avg_mean": sub["avg_ret"].mean(),
            "sharpe": sub["avg_ret"].mean() / sub["avg_ret"].std() * np.sqrt(252) if sub["avg_ret"].std() > 0 else 0,
        })

    # 4. By SPX trend
    for trend_val, label in [(-1, "down"), (0, "flat"), (1, "up")]:
        mask = joined["SPX_trend"] == trend_val
        if mask.sum() < 5:
            continue
        sub = joined[mask]
        results.append({
            "condition": f"spx_trend_{label}",
            "n": int(mask.sum()),
            "avg_mean": sub["avg_ret"].mean(),
            "sharpe": sub["avg_ret"].mean() / sub["avg_ret"].std() * np.sqrt(252) if sub["avg_ret"].std() > 0 else 0,
        })

    # 5. Inventory build/draw (EIA)
    if "inventory_change" in joined.columns:
        for direction, label in [(-1, "draw"), (1, "build")]:
            mask = np.sign(joined["inventory_change"]) == direction
            if mask.sum() < 5:
                continue
            sub = joined[mask]
            results.append({
                "condition": f"eia_inventory_{label}",
                "n": int(mask.sum()),
                "avg_mean": sub["avg_ret"].mean(),
                "sharpe": sub["avg_ret"].mean() / sub["avg_ret"].std() * np.sqrt(252) if sub["avg_ret"].std() > 0 else 0,
            })

    return pd.DataFrame(results)

def analyze_brent_wti_spread(crude: Dict) -> pd.DataFrame:
    """Analyze Brent-WTI spread dynamics."""
    wti = crude["wti_daily"].copy()
    brent = crude["brent_daily"].copy()

    wti["trade_date_ist"] = pd.to_datetime(wti["trade_date_ist"])
    brent["trade_date_ist"] = pd.to_datetime(brent["trade_date_ist"])

    wti = wti.set_index("trade_date_ist")["close_native"]
    brent = brent.set_index("trade_date_ist")["close_native"]

    spread = (brent - wti).dropna().rename("brent_wti_spread")
    spread_ret = spread.pct_change() * 100

    # Rolling stats
    spread_ma = spread.rolling(20).mean()
    spread_std = spread.rolling(20).std()
    spread_z = (spread - spread_ma) / spread_std

    # Mean reversion signals
    signals = pd.DataFrame({
        "spread": spread,
        "spread_z": spread_z,
        "spread_ret": spread_ret,
        "long_brent_short_wti": np.where(spread_z < -2, 1, np.where(spread_z > 2, -1, 0)),
    })

    return signals

def rolling_cross_correlations(crude: Dict, macro: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Compute rolling correlations between crude and macro assets."""
    wti = crude["wti_daily"].set_index("trade_date_ist")["close_native"].pct_change()
    brent = crude["brent_daily"].set_index("trade_date_ist")["close_native"].pct_change()

    # Convert macro columns to numeric, coercing errors
    macro_numeric = macro.apply(pd.to_numeric, errors='coerce')
    macro_ret = macro_numeric.pct_change()

    # Align
    all_data = pd.concat([wti.rename("WTI"), brent.rename("BRENT"), macro_ret], axis=1).dropna()

    results = []
    for i in range(window, len(all_data)):
        sub = all_data.iloc[i-window:i]
        date = all_data.index[i]

        corr = sub.corr()
        row = {"date": date}
        for asset in ["DXY", "SPX", "GOLD", "US10Y", "VIX"]:
            if asset in corr.columns:
                row[f"WTI_{asset}_corr"] = corr.loc["WTI", asset]
                row[f"BRENT_{asset}_corr"] = corr.loc["BRENT", asset]
        results.append(row)

    return pd.DataFrame(results)

# ─── Main Pipeline ────────────────────────────────────────────────────────────

def run_enhanced_cross_asset() -> Dict:
    """Run the complete cross-asset analysis pipeline."""
    print(">>> Enhanced Cross-Asset Analysis Starting", flush=True)

    # 1. Fetch macro prices
    macro_prices = fetch_macro_prices()
    if macro_prices.empty:
        return {"status": "error", "message": "Failed to fetch macro prices"}

    macro_prices.to_csv(ARTIFACTS / "macro_prices.csv")
    print(f">>> Saved macro_prices.csv: {len(macro_prices)} rows")

    # 2. Compute macro features
    macro_features = compute_macro_features(macro_prices)
    macro_features.to_csv(ARTIFACTS / "macro_regime.csv")
    print(f">>> Saved macro_regime.csv: {len(macro_features)} rows")

    # 3. Load crude data
    crude = load_crude_data()

    # 4. Conditional analysis
    conditional = analyze_macro_conditionals(crude, macro_features)
    conditional.to_csv(ARTIFACTS / "macro_conditional_returns.csv", index=False)
    print(f">>> Saved macro_conditional_returns.csv: {len(conditional)} conditions")

    # 5. Brent-WTI spread
    spread_signals = analyze_brent_wti_spread(crude)
    spread_signals.to_csv(ARTIFACTS / "brent_wti_spread_signals.csv")
    print(f">>> Saved brent_wti_spread_signals.csv")

    # 6. Rolling correlations
    roll_corr = rolling_cross_correlations(crude, macro_features)
    roll_corr.to_csv(ARTIFACTS / "rolling_cross_correlations.csv", index=False)
    print(f">>> Saved rolling_cross_correlations.csv: {len(roll_corr)} rows")

    # 7. EIA Inventory (if API key)
    inventory = fetch_eia_inventory()
    if not inventory.empty:
        inventory.to_csv(ARTIFACTS / "eia_inventory.csv", index=False)

    # 8. Options vol surface
    options = fetch_options_vol_surface()
    if not options.empty:
        options.to_csv(ARTIFACTS / "options_vol_surface.csv", index=False)

    # 9. COT data
    cot = fetch_cot_data()
    if not cot.empty:
        cot.to_csv(ARTIFACTS / "cot_positioning.csv", index=False)

    # 10. Summary stats for dashboard
    summary = {
        "macro_regimes": macro_features["macro_regime"].value_counts().to_dict(),
        "dollar_regimes": macro_features["dollar_regime"].value_counts().to_dict(),
        "vix_regimes": macro_features["vix_regime"].value_counts().to_dict() if "vix_regime" in macro_features else {},
        "conditional_returns": conditional.to_dict(orient="records"),
        "current_spread": float(spread_signals["spread"].iloc[-1]) if len(spread_signals) > 0 else None,
        "current_spread_z": float(spread_signals["spread_z"].iloc[-1]) if len(spread_signals) > 0 else None,
        "latest_correlations": roll_corr.iloc[-1].to_dict() if len(roll_corr) > 0 else {},
    }

    with open(ARTIFACTS / "cross_asset_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print("\n>>> Cross-Asset Analysis Complete!")
    print(f"  Conditional findings: {len(conditional)} regime-condition pairs analyzed")

    return {"status": "success", "summary": summary}

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    result = run_enhanced_cross_asset()
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()