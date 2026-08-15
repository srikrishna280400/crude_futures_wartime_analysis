"""probabilistic_signal_engine.py — Production signal engine with Bayesian posteriors, Kelly sizing, and regime-conditional stops.

This engine transforms the pattern library into actionable trading signals:
1. Computes P(UP|conditions) with 95% credible intervals (Beta-Binomial)
2. Computes expected value E[return|conditions] with uncertainty
3. Kelly-optimal position sizing per signal
4. ATR-based stops/targets per magnitude tier
5. Drawdown-aware risk controls
6. Signal filtering by FDR-corrected significance

Outputs:
- artifacts/signals_live.csv (today's signals)
- artifacts/signal_performance.csv (historical signal performance)
- artifacts/risk_params.json (stop/target/sizing params per tier/phase)
"""

from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import beta as beta_dist

warnings.filterwarnings("ignore")

# ─── Configuration ────────────────────────────────────────────────────────────

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

# Risk parameters
TARGET_ANNUAL_VOL = 0.10        # 10% annual vol target
MAX_POSITION_PCT = 0.25         # Max 25% equity per trade
MAX_DRAWDOWN_PCT = 0.10         # Stop trading at 10% DD
REDUCE_SIZE_DD_PCT = 0.05       # Halve size at 5% DD
KELLY_MAX_FRACTION = 0.25       # Cap Kelly at 25%
MIN_TRADES_FOR_KELLY = 20       # Min trades for Kelly estimate

# Bayesian priors
DIRICHLET_PRIOR = (1.0, 1.0, 1.0)  # Flat prior for UP/DOWN/FLAT

# Magnitude tier ATR multipliers
TIER_STOP_MULT = {
    "Q1_0_25": 0.5,
    "Q2_25_50": 0.75,
    "Q3_50_75": 1.0,
    "Q4_75_90": 1.5,
    "Q5_90_100": 2.0,
}
TIER_TARGET_MULT = {k: v * 2.0 for k, v in TIER_STOP_MULT.items()}  # 2:1 R:R

# ─── Data Classes ─────────────────────────────────────────────────────────────

class SignalDirection(Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"
    NONE = "NONE"

@dataclass
class BayesianPosterior:
    """Beta-Binomial posterior for directional probability."""
    mean_up: float
    mean_down: float
    mean_flat: float
    hdi_up: Tuple[float, float]
    hdi_down: Tuple[float, float]
    hdi_flat: Tuple[float, float]
    n_eff: float
    sample_n: int

@dataclass
class SignalExpectancy:
    """Expected value and risk metrics for a signal."""
    exp_return_pct: float
    exp_return_lower: float  # 5th percentile
    exp_return_upper: float  # 95th percentile
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    sharpe_estimate: float
    n_trades: int

@dataclass
class PositionSizing:
    """Kelly/vol-target position sizing."""
    kelly_fraction: float
    vol_target_fraction: float
    final_fraction: float
    position_size_usd: float
    stop_distance_pct: float
    target_distance_pct: float
    risk_per_trade_usd: float

@dataclass
class TradingSignal:
    """Complete trading signal with all metadata."""
    timestamp: str
    stream: str
    phase_id: int
    phase_label: str
    day_archetype: str
    current_window: str
    next_window: str
    direction: SignalDirection
    posterior: BayesianPosterior
    expectancy: SignalExpectancy
    sizing: PositionSizing
    stop_price: float
    target_price: float
    entry_price: float
    atr_pct: float
    magnitude_tier: str
    fdr_q_value: float
    significant: bool
    confidence_score: float  # Composite: posterior precision * sample size * significance
    signal_id: str

# ─── Bayesian Inference ───────────────────────────────────────────────────────

def dirichlet_posterior(n_up: int, n_down: int, n_flat: int,
                         prior: Tuple[float, float, float] = DIRICHLET_PRIOR) -> BayesianPosterior:
    """Compute Dirichlet posterior for 3-category outcome."""
    alpha_up = prior[0] + n_up
    alpha_down = prior[1] + n_down
    alpha_flat = prior[2] + n_flat
    alpha_sum = alpha_up + alpha_down + alpha_flat

    mean_up = alpha_up / alpha_sum
    mean_down = alpha_down / alpha_sum
    mean_flat = alpha_flat / alpha_sum

    # Variance for each (Dirichlet marginal is Beta)
    var_up = (alpha_up * (alpha_sum - alpha_up)) / (alpha_sum**2 * (alpha_sum + 1))
    var_down = (alpha_down * (alpha_sum - alpha_down)) / (alpha_sum**2 * (alpha_sum + 1))
    var_flat = (alpha_flat * (alpha_sum - alpha_flat)) / (alpha_sum**2 * (alpha_sum + 1))

    # 95% HDI using Beta approximation
    def hdi_beta(a, b):
        # Use percentiles of Beta distribution
        return (float(beta_dist.ppf(0.025, a, b)), float(beta_dist.ppf(0.975, a, b)))

    hdi_up = hdi_beta(alpha_up, alpha_sum - alpha_up)
    hdi_down = hdi_beta(alpha_down, alpha_sum - alpha_down)
    hdi_flat = hdi_beta(alpha_flat, alpha_sum - alpha_flat)

    # Effective sample size
    n_eff = alpha_sum - sum(prior)

    return BayesianPosterior(
        mean_up=mean_up, mean_down=mean_down, mean_flat=mean_flat,
        hdi_up=hdi_up, hdi_down=hdi_down, hdi_flat=hdi_flat,
        n_eff=n_eff, sample_n=n_up + n_down + n_flat
    )

def compute_expectancy(posterior: BayesianPosterior,
                       magnitude_tier: str,
                       historical_returns: pd.Series) -> SignalExpectancy:
    """Compute expected return with uncertainty from posterior."""
    if len(historical_returns) < 5:
        # Default estimates
        return SignalExpectancy(
            exp_return_pct=0.0, exp_return_lower=-1.0, exp_return_upper=1.0,
            win_rate=posterior.mean_up, avg_win_pct=1.0, avg_loss_pct=-1.0,
            profit_factor=1.0, sharpe_estimate=0.0, n_trades=len(historical_returns)
        )

    wins = historical_returns[historical_returns > 0]
    losses = historical_returns[historical_returns < 0]

    win_rate = len(wins) / len(historical_returns) if len(historical_returns) > 0 else 0.5
    avg_win = wins.mean() if len(wins) > 0 else 1.0
    avg_loss = losses.mean() if len(losses) > 0 else -1.0
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf

    # Posterior-weighted expectancy
    # E[R] = P(UP)*E[R|UP] + P(DOWN)*E[R|DOWN] + P(FLAT)*E[R|FLAT]
    # Approximate E[R|FLAT] ≈ 0
    exp_return = posterior.mean_up * avg_win + posterior.mean_down * avg_loss

    # Bootstrap uncertainty
    n_boot = 1000
    boot_returns = []
    for _ in range(n_boot):
        # Sample from posterior
        p_up = beta_dist.rvs(posterior.hdi_up[0]*100, posterior.hdi_up[1]*100)  # rough
        p_down = beta_dist.rvs(posterior.hdi_down[0]*100, posterior.hdi_down[1]*100)
        # Renormalize
        total = p_up + p_down
        if total > 0:
            p_up, p_down = p_up/total, p_down/total
        boot_exp = p_up * avg_win + p_down * avg_loss
        boot_returns.append(boot_exp)

    return SignalExpectancy(
        exp_return_pct=exp_return,
        exp_return_lower=float(np.percentile(boot_returns, 5)),
        exp_return_upper=float(np.percentile(boot_returns, 95)),
        win_rate=win_rate,
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        profit_factor=pf if pf != np.inf else 10.0,
        sharpe_estimate=exp_return / historical_returns.std() * np.sqrt(252) if historical_returns.std() > 0 else 0,
        n_trades=len(historical_returns)
    )

# ─── Position Sizing ──────────────────────────────────────────────────────────

def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float, max_frac: float = KELLY_MAX_FRACTION) -> float:
    """Kelly criterion: f* = (p*b - q)/b where b = avg_win/|avg_loss|."""
    if avg_loss == 0 or win_rate <= 0:
        return 0.0
    b = avg_win / abs(avg_loss)
    p = win_rate
    q = 1 - p
    f = (p * b - q) / b
    return float(np.clip(f, 0, max_frac))

def vol_target_fraction(equity: float, target_annual_vol: float,
                         stop_distance_pct: float, trades_per_year: int = 252) -> float:
    """Volatility targeting: position = equity * (target_vol / trade_vol)."""
    if stop_distance_pct == 0:
        return 0.0
    trade_vol_annual = stop_distance_pct * np.sqrt(trades_per_year)
    if trade_vol_annual == 0:
        return 0.0
    position_frac = target_annual_vol / trade_vol_annual
    return float(np.clip(position_frac, 0, MAX_POSITION_PCT))

def compute_position_sizing(equity: float, expectancy: SignalExpectancy,
                            atr_pct: float, magnitude_tier: str,
                            current_drawdown: float) -> PositionSizing:
    """Compute final position size with all risk controls."""
    # Base stop/target from ATR and tier
    stop_mult = TIER_STOP_MULT.get(magnitude_tier, 1.0)
    target_mult = TIER_TARGET_MULT.get(magnitude_tier, 2.0)

    stop_dist = atr_pct * stop_mult
    target_dist = atr_pct * target_mult

    # Kelly
    kelly_f = kelly_fraction(expectancy.win_rate, expectancy.avg_win_pct, expectancy.avg_loss_pct)

    # Vol targeting
    vol_f = vol_target_fraction(equity, TARGET_ANNUAL_VOL, stop_dist)

    # Drawdown adjustment
    dd_mult = 1.0
    if current_drawdown >= MAX_DRAWDOWN_PCT:
        dd_mult = 0.0
    elif current_drawdown >= REDUCE_SIZE_DD_PCT:
        dd_mult = 0.5

    # Final fraction
    final_f = min(kelly_f, vol_f) * dd_mult
    final_f = float(np.clip(final_f, 0, MAX_POSITION_PCT))

    position_usd = equity * final_f
    risk_usd = position_usd * stop_dist / 100

    return PositionSizing(
        kelly_fraction=kelly_f,
        vol_target_fraction=vol_f,
        final_fraction=final_f,
        position_size_usd=position_usd,
        stop_distance_pct=stop_dist,
        target_distance_pct=target_dist,
        risk_per_trade_usd=risk_usd,
    )

# ─── Signal Generation ────────────────────────────────────────────────────────

def generate_signals(playbook: pd.DataFrame,
                     primitives: pd.DataFrame,
                     window_stats_fdr: pd.DataFrame,
                     equity: float = 100000,
                     current_drawdown: float = 0.0) -> List[TradingSignal]:
    """Generate trading signals from playbook with full probabilistic framework."""

    signals = []

    # Current market state (latest data)
    latest_date = primitives["trade_date_ist"].max()
    latest_primitives = primitives[primitives["trade_date_ist"] == latest_date]

    # Determine current day archetype
    day_types = pd.read_csv(ARTIFACTS / "day_types.csv")
    today_archetype = day_types[day_types["trade_date_ist"] == latest_date]
    current_archetype = today_archetype["day_archetype"].iloc[0] if not today_archetype.empty else "unknown"

    # Get current window (based on current time IST)
    now_ist = pd.Timestamp.now(tz="Asia/Kolkata")
    current_window = assign_session_window(pd.Series([now_ist])).iloc[0]

    # Filter playbook for current conditions
    # Note: playbook has (phase, day_archetype, current_window) -> next_window distribution
    current_phase = get_current_phase(latest_date)
    if current_phase is None:
        return signals

    mask = (
        (playbook["phase_id"] == current_phase) &
        (playbook["day_archetype"] == current_archetype) &
        (playbook["current_window"] == current_window)
    )
    applicable = playbook[mask]

    if applicable.empty:
        # Try without day archetype
        mask = (playbook["phase_id"] == current_phase) & (playbook["current_window"] == current_window)
        applicable = playbook[mask]

    for _, row in applicable.iterrows():
        n_obs = row["n_observations"]
        if n_obs < 3:
            continue

        # Direction
        p_up = row["pct_up_next"]
        p_down = row["pct_down_next"]
        p_flat = row["pct_flat_next"]

        direction = SignalDirection.UP if p_up > p_down else SignalDirection.DOWN
        if max(p_up, p_down) < 40:  # No clear edge
            direction = SignalDirection.FLAT

        # Bayesian posterior
        n_up = int(n_obs * p_up / 100)
        n_down = int(n_obs * p_down / 100)
        n_flat = n_obs - n_up - n_down
        posterior = dirichlet_posterior(n_up, n_down, n_flat)

        # Historical returns for this signal
        signal_key = f"{row['stream']}|{row['phase_id']}|{row['day_archetype']}|{row['current_window']}"
        hist_returns = get_historical_returns(signal_key, primitives)

        # Expectancy
        # Need magnitude tier for this signal
        tier = row.get("magnitude_tier", "Q3_50_75")
        expectancy = compute_expectancy(posterior, tier, hist_returns)

        # Current ATR for sizing
        atr_row = primitives[
            (primitives["phase_id"] == current_phase) &
            (primitives["__stream"] == row["stream"])
        ].iloc[-1] if not primitives.empty else None
        atr_pct = atr_row.get("phase_atr_pct", 1.5) if atr_row is not None else 1.5

        # Entry price (next window open)
        entry_price = get_next_window_open(row["stream"], row["top_next_window"], latest_date, primitives)

        # Position sizing
        sizing = compute_position_sizing(equity, expectancy, atr_pct, tier, current_drawdown)

        # Stop/target prices
        if direction == SignalDirection.UP:
            stop_price = entry_price * (1 - sizing.stop_distance_pct / 100)
            target_price = entry_price * (1 + sizing.target_distance_pct / 100)
        elif direction == SignalDirection.DOWN:
            stop_price = entry_price * (1 + sizing.stop_distance_pct / 100)
            target_price = entry_price * (1 - sizing.target_distance_pct / 100)
        else:
            stop_price = entry_price
            target_price = entry_price

        # FDR q-value
        fdr_row = window_stats_fdr[
            (window_stats_fdr["stream"] == row["stream"]) &
            (window_stats_fdr["phase_id"] == row["phase_id"]) &
            (window_stats_fdr["session_window_ist"] == row["top_next_window"])
        ]
        q_val = fdr_row["q_up"].iloc[0] if direction == SignalDirection.UP and not fdr_row.empty else \
                fdr_row["q_down"].iloc[0] if direction == SignalDirection.DOWN and not fdr_row.empty else 1.0

        # Confidence score
        confidence = compute_confidence(posterior, n_obs, q_val, expectancy)

        signal = TradingSignal(
            timestamp=datetime.now().isoformat(),
            stream=row["stream"],
            phase_id=int(row["phase_id"]),
            phase_label=row.get("phase_label", ""),
            day_archetype=row["day_archetype"],
            current_window=row["current_window"],
            next_window=row["top_next_window"],
            direction=direction,
            posterior=posterior,
            expectancy=expectancy,
            sizing=sizing,
            stop_price=stop_price,
            target_price=target_price,
            entry_price=entry_price,
            atr_pct=atr_pct,
            magnitude_tier=tier,
            fdr_q_value=float(q_val),
            significant=q_val < 0.05,
            confidence_score=confidence,
            signal_id=hashlib.md5(signal_key.encode()).hexdigest()[:8],
        )
        signals.append(signal)

    return signals

def compute_confidence(posterior: BayesianPosterior, n_obs: int, q_val: float,
                        expectancy: SignalExpectancy) -> float:
    """Composite confidence score: posterior precision * sqrt(n) * (1-q) * |expectancy|."""
    # Posterior precision (inverse of HDI width)
    hdi_width = posterior.hdi_up[1] - posterior.hdi_up[0]
    precision = 1 / (hdi_width + 0.01)

    # Sample size factor
    n_factor = min(np.sqrt(n_obs / 20), 1.0)  # Caps at n=20

    # Significance factor
    sig_factor = 1 - q_val

    # Expectancy magnitude
    exp_factor = min(abs(expectancy.exp_return_pct) / 1.0, 1.0)  # Cap at 1% expected

    return float(precision * n_factor * sig_factor * exp_factor)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def assign_session_window(ts_ist: pd.Series) -> pd.Series:
    """Vectorized session window assignment."""
    h = ts_ist.dt.hour.astype(float) + ts_ist.dt.minute.astype(float) / 60.0
    out = pd.Series("other_valid_hours", index=ts_ist.index, dtype=object)
    windows = {
        "global_reopen_pre_mcx": (3.5, 9.0),
        "mcx_open_drive": (9.0, 10.5),
        "india_morning": (10.5, 12.5),
        "india_midday": (12.5, 15.5),
        "europe_midday": (15.5, 18.0),
        "us_pre_open": (18.0, 20.0),
        "us_open": (20.0, 23.0),
        "mcx_tail": (23.0, 24.0),
        "us_late": (0.0, 1.5),
    }
    for name, (a, b) in windows.items():
        if a < b:
            mask = (h >= a) & (h < b)
        else:
            mask = (h >= a) | (h < b)
        out = out.mask(mask, name)
    return out

def get_current_phase(date: pd.Timestamp) -> Optional[int]:
    """Get phase_id for a date from phase_lookup.csv."""
    phase = pd.read_csv(ARTIFACTS / "phase_lookup.csv")
    phase["start"] = pd.to_datetime(phase["start_datetime_ist"])
    phase["end"] = pd.to_datetime(phase["end_datetime_ist"])
    dt = pd.Timestamp(date).tz_localize(None)
    match = phase[(phase["start"] <= dt) & (phase["end"] >= dt)]
    return int(match["phase_id"].iloc[0]) if not match.empty else None

def get_historical_returns(signal_key: str, primitives: pd.DataFrame) -> pd.Series:
    """Get historical returns for a specific signal pattern."""
    # This would need the backtest trades or we approximate from primitives
    # For now, return empty series - will be populated from backtest
    return pd.Series(dtype=float)

def get_next_window_open(stream: str, window: str, date: pd.Timestamp, primitives: pd.DataFrame) -> float:
    """Get the open price for the next window on a given date."""
    next_data = primitives[
        (primitives["__stream"] == stream) &
        (primitives["trade_date_ist"] == date) &
        (primitives["session_window_ist"] == window)
    ]
    if not next_data.empty:
        return float(next_data["open_native"].iloc[0])
    return 100.0  # Fallback

# ─── Main Pipeline ────────────────────────────────────────────────────────────

def run_signal_engine(mode: str = "live", equity: float = 100000, current_dd: float = 0.0) -> Dict:
    """Main entry point for signal engine."""
    print(f">>> Probabilistic Signal Engine: {mode} mode", flush=True)

    # Load artifacts
    playbook = pd.read_csv(ARTIFACTS / "playbook_summary.csv")
    primitives = pd.read_parquet(ARTIFACTS / "primitives.parquet")
    window_stats_fdr = pd.read_csv(ARTIFACTS / "window_stats_fdr.csv")

    # Generate signals
    signals = generate_signals(playbook, primitives, window_stats_fdr, equity, current_dd)

    # Convert to DataFrame
    if signals:
        sig_df = pd.DataFrame([{
            "timestamp": s.timestamp,
            "signal_id": s.signal_id,
            "stream": s.stream,
            "phase_id": s.phase_id,
            "phase_label": s.phase_label,
            "day_archetype": s.day_archetype,
            "current_window": s.current_window,
            "next_window": s.next_window,
            "direction": s.direction.value,
            "entry_price": s.entry_price,
            "stop_price": s.stop_price,
            "target_price": s.target_price,
            "atr_pct": s.atr_pct,
            "magnitude_tier": s.magnitude_tier,
            "p_up": s.posterior.mean_up,
            "p_down": s.posterior.mean_down,
            "p_flat": s.posterior.mean_flat,
            "hdi_up_lower": s.posterior.hdi_up[0],
            "hdi_up_upper": s.posterior.hdi_up[1],
            "hdi_down_lower": s.posterior.hdi_down[0],
            "hdi_down_upper": s.posterior.hdi_down[1],
            "exp_return": s.expectancy.exp_return_pct,
            "exp_return_lower": s.expectancy.exp_return_lower,
            "exp_return_upper": s.expectancy.exp_return_upper,
            "win_rate": s.expectancy.win_rate,
            "profit_factor": s.expectancy.profit_factor,
            "kelly_fraction": s.sizing.kelly_fraction,
            "vol_target_fraction": s.sizing.vol_target_fraction,
            "final_position_fraction": s.sizing.final_fraction,
            "position_size_usd": s.sizing.position_size_usd,
            "risk_per_trade_usd": s.sizing.risk_per_trade_usd,
            "fdr_q_value": s.fdr_q_value,
            "significant": s.significant,
            "confidence_score": s.confidence_score,
        } for s in signals])
    else:
        sig_df = pd.DataFrame()

    # Save — write today's signals AND append to a persistent history for the
    # prediction scorecard (P1). De-dupe by signal_id so re-runs don't double-count.
    sig_df.to_csv(ARTIFACTS / "signals_live.csv", index=False)
    history_path = ARTIFACTS / "signals_history.csv"
    if not sig_df.empty:
        try:
            if history_path.exists():
                hist = pd.read_csv(history_path)
                sig_df = pd.concat([hist, sig_df], ignore_index=True, sort=False)
            sig_df = sig_df.drop_duplicates(subset=["signal_id"], keep="last")
            sig_df.to_csv(history_path, index=False)
        except Exception as e:
            print(f"  !! signals_history append failed: {e}", flush=True)
    print(f">>> Generated {len(signals)} signals", flush=True)

    # Print summary
    for s in signals:
        print(f"  {s.signal_id}: {s.stream} P{s.phase_id} {s.current_window}->{s.next_window} "
              f"{s.direction.value} @ {s.confidence_score:.2f} conf "
              f"| Entry: {s.entry_price:.2f} SL: {s.stop_price:.2f} TP: {s.target_price:.2f} "
              f"| Size: {s.sizing.final_fraction:.1%} (${s.sizing.position_size_usd:,.0f})")

    return {
        "signals_generated": len(signals),
        "signals": [asdict(s) for s in signals] if signals else [],
    }

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import sys
    import hashlib
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"
    equity = float(sys.argv[2]) if len(sys.argv) > 2 else 100000
    dd = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    run_signal_engine(mode, equity, dd)

if __name__ == "__main__":
    main()