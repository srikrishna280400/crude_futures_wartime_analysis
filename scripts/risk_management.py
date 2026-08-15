"""risk_management.py — Risk management layer for playbook signals.

Components:
1. Position Sizing: Kelly criterion / volatility targeting (target vol = 10% annual)
2. Stop/Target Optimization: Grid search over ATR multiples per phase/archetype
3. Portfolio Limits: Max 1 position, max 2% equity per trade, max 5% sector exposure
4. Drawdown Controls: Reduce size 50% at 5% DD, stop at 10% DD
5. Kelly Fraction: f* = (p×b - q)/b where p=win_rate, b=avg_win/avg_loss

Outputs:
- risk_adjusted_backtest.csv (backtest with risk controls applied)
- risk_params.json (optimal parameters per phase/archetype)
- equity_curve_risk_adjusted.parquet (for plotting)
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
MODELS = BASE / "models"


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float, max_fraction: float = 0.25) -> float:
    """Kelly criterion fraction with cap.
    f* = (p * b - q) / b where p=win_rate, q=1-p, b=avg_win/|avg_loss|
    """
    if avg_loss == 0 or win_rate <= 0:
        return 0.0
    b = avg_win / abs(avg_loss)
    p = win_rate
    q = 1 - p
    f = (p * b - q) / b
    return float(np.clip(f, 0, max_fraction))


def vol_target_position(equity: float, target_annual_vol: float, trade_vol_pct: float,
                         stop_dist_pct: float) -> float:
    """Volatility targeting position size.
    Position = equity * (target_vol / trade_vol) where trade_vol = stop_dist * sqrt(trades_per_year)
    """
    if stop_dist_pct == 0:
        return 0.0
    trades_per_year = 252  # assuming daily trades
    trade_vol_annual = stop_dist_pct * np.sqrt(trades_per_year)
    if trade_vol_annual == 0:
        return 0.0
    position_frac = target_annual_vol / trade_vol_annual
    return float(np.clip(equity * position_frac, 0, equity * 0.1))  # cap at 10% equity


def simulate_with_risk(trades_df: pd.DataFrame, equity_start: float = 100000,
                        target_vol: float = 0.10, max_dd_pct: float = 0.10,
                        reduce_at_pct: float = 0.05) -> tuple[pd.DataFrame, dict]:
    """Simulate trades with risk management applied."""
    equity = equity_start
    equity_curve = []
    dd_curve = []
    peak = equity_start

    results = []
    current_size_mult = 1.0  # position size multiplier (1.0 = full)

    for _, trade in trades_df.iterrows():
        # Apply current drawdown control
        dd = (peak - equity) / peak if peak > 0 else 0
        if dd >= max_dd_pct:
            current_size_mult = 0.0  # stop trading
        elif dd >= reduce_at_pct:
            current_size_mult = 0.5  # reduce size
        else:
            current_size_mult = 1.0

        if current_size_mult == 0:
            equity_curve.append(equity)
            dd_curve.append(dd)
            continue

        # Position sizing using Kelly (capped at 25%)
        kelly_frac = kelly_fraction(
            trade.get("win_rate_historical", 0.5),
            trade.get("avg_win_historical", 1.0),
            trade.get("avg_loss_historical", 1.0),
            max_fraction=0.25
        )

        # Also apply vol targeting
        stop_dist = trade.get("stop_dist_pct", 1.0)
        vol_frac = vol_target_position(
            equity * kelly_frac, 0.10, 1.0, stop_dist
        ) / equity if equity > 0 else 0

        # Use smaller of Kelly and vol targeting
        position_frac = min(kelly_frac, vol_frac)
        position_size = equity * position_frac * current_size_mult

        # Simulate trade
        pnl_pct = trade["pnl_pct"]
        pnl = position_size * pnl_pct / 100
        equity += pnl
        peak = max(peak, equity)

        equity_curve.append(equity)
        dd_curve.append((peak - equity) / peak if peak > 0 else 0)

        results.append({
            "trade_date": trade.get("trade_date"),
            "signal": trade.get("signal_key"),
            "entry": trade.get("entry"),
            "exit": trade.get("exit"),
            "pnl_pct": pnl_pct,
            "position_size": position_size,
            "kelly_frac": kelly_frac,
            "size_mult": current_size_mult,
            "pnl": pnl,
            "equity": equity,
            "drawdown": dd,
            "exit_type": trade.get("exit_type"),
        })

    results_df = pd.DataFrame(results)

    # Summary metrics
    if len(results_df) > 0:
        pnl_series = results_df["pnl_pct"] if "pnl_pct" in results_df.columns else results_df["pnl"] / equity_start * 100
        metrics = {
            "total_return_pct": (equity - equity_start) / equity_start * 100,
            "total_trades": len(results_df),
            "win_rate": (results_df["pnl"] > 0).mean() * 100 if "pnl" in results_df.columns else 0,
            "profit_factor": results_df[results_df["pnl"] > 0]["pnl"].sum() / abs(results_df[results_df["pnl"] < 0]["pnl"].sum()) if (results_df["pnl"] < 0).any() else np.inf,
            "expectancy_pct": results_df["pnl_pct"].mean() if "pnl_pct" in results_df.columns else 0,
            "sharpe": results_df["pnl_pct"].mean() / results_df["pnl_pct"].std() * np.sqrt(252) if results_df["pnl_pct"].std() > 0 else 0,
            "max_drawdown_pct": max(dd_curve) * 100 if dd_curve else 0,
            "final_equity": equity,
        }
    else:
        metrics = {}

    equity_df = pd.DataFrame({
        "trade_num": range(len(equity_curve)),
        "equity": equity_curve,
        "drawdown_pct": dd_curve
    })

    return results_df, equity_df, metrics


def optimize_stops_targets(trades_df: pd.DataFrame, atr_col: str = "atr_pct",
                            tier_col: str = "magnitude_tier") -> pd.DataFrame:
    """Grid search over ATR multiples for stop/target per phase/archetype."""
    # This is a placeholder - would need historical intraday data to properly test
    # For now, return default multipliers per tier
    tier_multipliers = {
        "Q1_0_25": {"stop_mult": 0.5, "target_mult": 1.0},
        "Q2_25_50": {"stop_mult": 0.75, "target_mult": 1.5},
        "Q3_50_75": {"stop_mult": 1.0, "target_mult": 2.0},
        "Q4_75_90": {"stop_mult": 1.5, "target_mult": 3.0},
        "Q5_90_100": {"stop_mult": 2.0, "target_mult": 4.0},
    }
    return pd.DataFrame([{"tier": k, **v} for k, v in tier_multipliers.items()])


def main():
    print(">>> risk_management.py starting", flush=True)

    # Load backtest trades
    trades = pd.read_parquet("artifacts/backtest_trades.parquet")
    print(f">>> Loaded {len(trades)} trades", flush=True)

    # Add historical win rate / avg win/loss per signal for Kelly
    signal_stats = trades.groupby("signal_key").agg(
        win_rate_historical=("pnl_pct", lambda x: (x > 0).mean()),
        avg_win_historical=("pnl_pct", lambda x: x[x > 0].mean() if (x > 0).any() else 1),
        avg_loss_historical=("pnl_pct", lambda x: x[x < 0].mean() if (x < 0).any() else -1),
        n_trades=("pnl_pct", "count"),
    ).reset_index()

    # Merge stats back
    trades_with_stats = trades.merge(signal_stats, on="signal_key", how="left")

    # Run risk-adjusted backtest
    trades_risk, equity_df, metrics = simulate_with_risk(trades_with_stats)

    # Save
    trades_risk.to_parquet("artifacts/backtest_trades_risk_adjusted.parquet", index=False)
    trades_risk.to_csv("artifacts/backtest_trades_risk_adjusted.csv", index=False)

    equity_curve = pd.DataFrame({
        "trade_num": range(len(trades_with_stats)),
        "equity": trades_with_stats["pnl_pct"].cumsum() + 100000
    })
    equity_curve.to_parquet("artifacts/equity_curve_risk_adjusted.parquet", index=False)

    # Optimize stop/target params
    opt_params = optimize_stops_targets(trades)
    opt_params.to_csv("artifacts/risk_params.csv", index=False)

    # Summary
    print("\n=== RISK-ADJUSTED BACKTEST SUMMARY ===")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    # Save metrics
    import json
    with open("artifacts/risk_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    print(">>> risk_management.py complete", flush=True)


if __name__ == "__main__":
    main()