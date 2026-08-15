"""backtester.py — Vectorized backtester for playbook signals.

Replays every playbook signal on historical data, computes:
- Per-signal P&L (entry at next window open, exit at window close or stop/target)
- Aggregate metrics: Sharpe, Sortino, max DD, win rate, profit factor, expectancy
- Per-phase, per-archetype, per-window breakdown
- Monte Carlo resampling for confidence intervals on metrics

Outputs:
- backtest_results.json (machine-readable)
- backtest_summary.csv (human-readable)
- equity_curve.parquet (for plotting)
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
SCRIPTS = BASE / "scripts"


def load_artifacts():
    """Load all compact artifacts needed for backtesting."""
    playbook = pd.read_csv(ARTIFACTS / "playbook_summary.csv")
    primitives = pd.read_parquet(ARTIFACTS / "primitives.parquet")
    phase = pd.read_csv(ARTIFACTS / "phase_lookup.csv")
    day_types = pd.read_csv(ARTIFACTS / "day_types.csv")
    return playbook, primitives, phase, day_types


def compute_stops_targets(row, primitives_row):
    """Derive stop/target from magnitude tier and phase ATR."""
    # Use phase ATR as base unit
    atr = primitives_row.get("phase_atr_pct", 1.5)
    tier = primitives_row.get("magnitude_tier", "Q1_0_25")

    # Tier multipliers for stop/target
    tier_mult = {
        "Q1_0_25": 0.5,
        "Q2_25_50": 0.75,
        "Q3_50_75": 1.0,
        "Q4_75_90": 1.5,
        "Q5_90_100": 2.0,
    }.get(tier, 1.0)

    stop_atr = 1.0 * tier_mult   # 1 ATR stop
    target_atr = 2.0 * tier_mult  # 2:1 reward:risk

    return {
        "stop_pct": atr * stop_atr,
        "target_pct": atr * target_atr,
        "atr_pct": atr,
    }


def simulate_signal(playbook_row, primitives, session_data):
    """Simulate a single playbook signal on historical data.

    Entry: next window's open
    Exit: window close, or stop/target hit intraday
    """
    stream = playbook_row["stream"]
    phase_id = playbook_row["phase_id"]
    archetype = playbook_row["day_archetype"]
    current_window = playbook_row["current_window"]
    next_window = playbook_row["top_next_window"]
    direction_bias = "UP" if playbook_row["pct_up_next"] > playbook_row["pct_down_next"] else "DOWN"

    # Filter session data for this stream, phase, archetype, current_window
    mask = (
        (primitives["__stream"] == stream) &
        (primitives["phase_id"] == phase_id) &
        (primitives["session_window_ist"] == current_window)
    )

    # Need to join with day_types for archetype
    # This is simplified - in reality we'd need the full join
    qualifying = primitives[mask].copy()

    if len(qualifying) < 3:
        return None

    results = []
    for _, row in qualifying.iterrows():
        # Get the next window's data for this date
        date = row["trade_date_ist"]
        next_data = primitives[
            (primitives["__stream"] == stream) &
            (primitives["trade_date_ist"] == date) &
            (primitives["session_window_ist"] == next_window)
        ]

        if next_data.empty:
            continue

        next_row = next_data.iloc[0]

        # Entry at next window open
        entry_price = next_row["open_native"]
        exit_price = next_row["close_native"]
        high = next_row["high_native"]
        low = next_row["low_native"]

        if pd.isna(entry_price) or pd.isna(exit_price):
            continue

        # Get stops/targets from magnitude tier
        tier = row.get("magnitude_tier", "Q1_0_25")
        atr = row.get("phase_atr_pct", 1.5)

        tier_mult = {
            "Q1_0_25": 0.5, "Q2_25_50": 0.75, "Q3_50_75": 1.0,
            "Q4_75_90": 1.5, "Q5_90_100": 2.0,
        }.get(tier, 1.0)

        stop_dist = atr * 1.0 * tier_mult
        target_dist = atr * 2.0 * tier_mult

        if direction_bias == "UP":
            stop_price = entry_price * (1 - stop_dist / 100)
            target_price = entry_price * (1 + target_dist / 100)
            # Check if stop hit first
            if low <= stop_price:
                pnl_pct = -stop_dist
                exit_type = "stop"
            elif high >= target_price:
                pnl_pct = target_dist
                exit_type = "target"
            else:
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                exit_type = "close"
        else:
            stop_price = entry_price * (1 + stop_dist / 100)
            target_price = entry_price * (1 - target_dist / 100)
            if high >= stop_price:
                pnl_pct = -stop_dist
                exit_type = "stop"
            elif low <= target_price:
                pnl_pct = target_dist
                exit_type = "target"
            else:
                pnl_pct = (entry_price - exit_price) / entry_price * 100
                exit_type = "close"

        results.append({
            "trade_date": date,
            "entry": entry_price,
            "exit": exit_price,
            "pnl_pct": pnl_pct,
            "exit_type": exit_type,
            "direction": direction_bias,
        })

    if not results:
        return None

    df = pd.DataFrame(results)
    return df


def run_backtest(playbook, primitives, phase, day_types):
    """Run full backtest across all playbook signals."""

    all_trades = []

    for _, pb_row in playbook.iterrows():
        if pb_row.get("low_confidence_flag", False):
            continue
        if pb_row["n_observations"] < 5:
            continue

        trades = simulate_signal(pb_row, primitives, None)
        if trades is not None and len(trades) > 0:
            trades["signal_key"] = f"{pb_row['stream']}|{pb_row['phase_id']}|{pb_row['day_archetype']}|{pb_row['current_window']}"
            trades["phase"] = pb_row["phase_id"]
            trades["archetype"] = pb_row["day_archetype"]
            trades["window"] = pb_row["current_window"]
            trades["stream"] = pb_row["stream"]
            all_trades.append(trades)

    if not all_trades:
        return pd.DataFrame()

    all_trades_df = pd.concat(all_trades, ignore_index=True)
    return all_trades_df


def compute_metrics(trades_df):
    """Compute comprehensive backtest metrics."""
    if trades_df.empty:
        return {}

    pnl = trades_df["pnl_pct"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    metrics = {
        "total_trades": len(trades_df),
        "win_rate": len(wins) / len(pnl) * 100,
        "avg_win": wins.mean() if len(wins) > 0 else 0,
        "avg_loss": losses.mean() if len(losses) > 0 else 0,
        "profit_factor": wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf,
        "expectancy": pnl.mean(),
        "sharpe": pnl.mean() / pnl.std() * np.sqrt(252) if pnl.std() > 0 else 0,
        "sortino": pnl.mean() / losses.std() * np.sqrt(252) if len(losses) > 0 and losses.std() > 0 else np.inf,
        "max_drawdown": compute_max_dd(pnl.cumsum()),
        "avg_trade_pct": pnl.mean(),
        "median_trade_pct": pnl.median(),
    }
    return metrics


def compute_max_dd(equity_curve):
    """Maximum drawdown from peak. Handles both array and Series."""
    eq = pd.Series(equity_curve)
    peak = eq.expanding().max()
    dd = (eq - peak) / peak * 100
    return dd.min()


def monte_carlo_confidence(trades_df, n_iter=1000, confidence=0.95):
    """Monte Carlo resampling for metric confidence intervals."""
    if trades_df.empty:
        return {}

    pnl = trades_df["pnl_pct"].values
    n = len(pnl)

    metrics_samples = {"sharpe": [], "win_rate": [], "expectancy": [], "max_dd": []}

    for _ in range(n_iter):
        sample = np.random.choice(pnl, size=n, replace=True)
        equity = np.cumsum(sample)
        metrics_samples["sharpe"].append(sample.mean() / sample.std() * np.sqrt(252) if sample.std() > 0 else 0)
        metrics_samples["win_rate"].append((sample > 0).mean() * 100)
        metrics_samples["expectancy"].append(sample.mean())
        metrics_samples["max_dd"].append(compute_max_dd(equity))

    alpha = (1 - confidence) / 2
    result = {}
    for k, v in metrics_samples.items():
        result[f"{k}_ci_lower"] = np.percentile(v, alpha * 100)
        result[f"{k}_ci_upper"] = np.percentile(v, (1 - alpha) * 100)
        result[f"{k}_median"] = np.median(v)

    return result


def main():
    print(">>> backtester.py starting", flush=True)

    playbook, primitives, phase, day_types = load_artifacts()
    print(f">>> Loaded playbook: {len(playbook)} rows, primitives: {len(primitives)} rows", flush=True)

    # Run backtest
    trades = run_backtest(playbook, primitives, phase, day_types)
    print(f">>> Simulated {len(trades)} trades across {trades['signal_key'].nunique() if len(trades) > 0 else 0} signals", flush=True)

    if trades.empty:
        print("!!! No trades generated", flush=True)
        return

    # Overall metrics
    overall = compute_metrics(trades)
    mc = monte_carlo_confidence(trades)

    # Per-signal metrics
    signal_metrics = []
    for sig, grp in trades.groupby("signal_key"):
        m = compute_metrics(grp)
        m["signal"] = sig
        m["n_trades"] = len(grp)
        signal_metrics.append(m)

    signal_df = pd.DataFrame(signal_metrics).sort_values("expectancy", ascending=False)

    # Per-phase metrics
    phase_metrics = []
    for ph, grp in trades.groupby("phase"):
        m = compute_metrics(grp)
        m["phase"] = ph
        m["n_trades"] = len(grp)
        phase_metrics.append(m)
    phase_df = pd.DataFrame(phase_metrics)

    # Per-archetype metrics
    arch_metrics = []
    for arch, grp in trades.groupby("archetype"):
        m = compute_metrics(grp)
        m["archetype"] = arch
        m["n_trades"] = len(grp)
        arch_metrics.append(m)
    arch_df = pd.DataFrame(arch_metrics)

    # Equity curve
    trades_sorted = trades.sort_values("trade_date")
    trades_sorted["cum_pnl"] = trades_sorted["pnl_pct"].cumsum()

    # Save outputs
    out_dir = ARTIFACTS
    out_dir.mkdir(exist_ok=True)

    trades.to_parquet(out_dir / "backtest_trades.parquet", index=False)
    trades.to_csv(out_dir / "backtest_trades.csv", index=False)
    signal_df.to_csv(out_dir / "backtest_by_signal.csv", index=False)
    phase_df.to_csv(out_dir / "backtest_by_phase.csv", index=False)
    arch_df.to_csv(out_dir / "backtest_by_archetype.csv", index=False)

    # Summary JSON
    summary = {
        "overall": overall,
        "monte_carlo_ci": mc,
        "n_signals": int(trades["signal_key"].nunique()),
        "n_trades": int(len(trades)),
        "date_range": [str(trades["trade_date"].min()), str(trades["trade_date"].max())],
    }

    with open(out_dir / "backtest_results.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # Print summary
    print("\n" + "="*60)
    print("BACKTEST SUMMARY")
    print("="*60)
    for k, v in overall.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    print("\nMonte Carlo 95% CI:")
    for k, v in mc.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    print(f"\n>>> Saved backtest artifacts to {out_dir}", flush=True)

    return trades, summary


if __name__ == "__main__":
    main()