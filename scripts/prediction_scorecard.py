"""prediction_scorecard.py — P1: Prediction Scorecard.

Purpose
-------
Makes the system genuinely "learn from its deviations": every time the signal
engine emits a signal, we record the *actual* next-window outcome. Over time we
compute rolling hit-rate, conditional edge, and edge-decay per
(phase, day-type, current_window, direction, stream). Stale patterns (those
whose recent hit-rate collapsed vs their announced historical edge) are flagged
and can be automatically down-weighted by the signal engine and dashboard.

This is P1 in the roadmap (turns "this looks smart" into "this provably works
or doesn't"). Depends ONLY on compact artifacts:
  - artifacts/signals_live.csv      (emitted signals with entry/SL/TP/direction)
  - artifacts/primitives.parquet    (actual OHLC to resolve next-window outcome)

Outputs
-------
  artifacts/prediction_scorecard.csv        — per-signal row: signal, date, direction,
                                               announced edge, resolved outcome, hit/miss,
                                               pnl estimate
  artifacts/prediction_rolling_metrics.csv  — rolling hit-rate & edge per pattern key
  artifacts/prediction_scorecard_summary.json — latest verdict + decay warning list
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ART = BASE / "artifacts"

# Recovery window sizes (in number of past signals) for rolling metrics
ROLLING_WINDOW = 30  # how many past signals define "recent" hit-rate
EDGE_DECAY_HALFLIFE = 20  # exponential decay half-life (signals), older entries weighted less
MIN_SIGNALS_FOR_VERDICT = 5
STALE_HITRATE_DROP = 0.15  # if recent hit-rate < announced edge - 0.15 → flag stale/decayed


# ----------------------------------------------------------------------
# Resolve actual outcome from primitives
# ----------------------------------------------------------------------
def resolve_outcome(sig_row: pd.Series, primitives: pd.DataFrame) -> Optional[float]:
    """Resolve the realized PnL% for a signal.

    Entry assumed at the current-window close (the 'next window' expected to
    open = the current window's close-ish), realized over the next window:
      For a signal at current_window C expecting next_window N:
        - find date D's row for window C (entry ref) and window N (outcome).
        - if N == C (same-window next-day style ambiguity) or missing → None.
    Since session frames are used, N is the immediately following window on the
    same trade date.
    """
    stream = sig_row.get("stream")
    date = sig_row.get("signal_date")  # normalized yyyy-mm-dd
    cwin = sig_row.get("current_window")
    nwin = sig_row.get("next_window")
    direction = str(sig_row.get("direction", "")).upper().strip()

    if not stream or not cwin or not nwin or direction not in ("UP", "DOWN"):
        return None

    sub = primitives[
        (primitives["__stream"] == stream)
        & (primitives["trade_date_ist"].dt.strftime("%Y-%m-%d") == date)
    ]
    if sub.empty:
        return None

    cur = sub[sub["session_window_ist"] == cwin]
    nxt = sub[sub["session_window_ist"] == nwin]
    if cur.empty or nxt.empty:
        return None

    entry = cur["close_native"].iloc[0]   # current-window close as entry ref
    outcome = nxt["close_native"].iloc[0]
    if not np.isfinite(entry) or not np.isfinite(outcome) or entry == 0:
        return None

    ret = (outcome - entry) / entry * 100.0
    if direction == "UP":
        return ret
    return -ret


# ----------------------------------------------------------------------
# Build scorecard from historical signals_live.csv (reproducible re-run)
# ----------------------------------------------------------------------
def build_scorecard(signals: pd.DataFrame, primitives: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()

    rows = []
    for _, s in signals.iterrows():
        date = str(s.get("timestamp", ""))[:10]
        hit_pnl = resolve_outcome(s, primitives)
        rows.append(
            {
                "signal_id": s.get("signal_id", ""),
                "signal_date": date,
                "stream": s.get("stream", ""),
                "phase_id": s.get("phase_id", np.nan),
                "day_archetype": s.get("day_archetype", ""),
                "current_window": s.get("current_window", ""),
                "next_window": s.get("next_window", ""),
                "direction": str(s.get("direction", "")).upper(),
                # announced edge (higher of p_up / p_down → direction bias)
                "announced_prob": float(
                    s.get("p_up") if str(s["direction"]).upper() == "UP" else s.get("p_down")
                ),
                "entry": s.get("entry_price", np.nan),
                "stop": s.get("stop_price", np.nan),
                "target": s.get("target_price", np.nan),
                "resolved_pnl_pct": hit_pnl,
                "resolved": hit_pnl is not None,
            }
        )
    sc = pd.DataFrame(rows)
    if sc.empty:
        return sc

    sc["hit"] = np.where(sc["resolved"], (sc["resolved_pnl_pct"] > 0).astype(int), np.nan)
    return sc.sort_values(["signal_date", "signal_id"]).reset_index(drop=True)


# ----------------------------------------------------------------------
# Rolling metrics & edge-decay
# ----------------------------------------------------------------------
def rolling_metrics(sc: pd.DataFrame) -> pd.DataFrame:
    """Per (stream, phase, day-type, current_window) rolling hit-rate & edge with decay weight."""
    if sc.empty or not sc["resolved"].any():
        return pd.DataFrame()

    resolved = sc[sc["resolved"]].copy()

    out_rows = []
    for key, g in resolved.groupby(
        ["stream", "phase_id", "day_archetype", "current_window"], dropna=False
    ):
        g = g.sort_values("signal_date").reset_index(drop=True)
        n = len(g)

        # overall hit-rate
        overall_hit = g["hit"].mean()
        # announced average edge (mean of announced_prob)
        announced_edge = g["announced_prob"].mean()
        # realized hit-rate bias
        realized_edge = overall_hit
        # decay-weighted recent hit-rate (exponential weights, newest = highest)
        if n > 0:
            weights = np.power(0.5, np.arange(n - 1, -1, -1) / EDGE_DECAY_HALFLIFE)
            recent_hit = float(np.average(g["hit"], weights=weights))
        else:
            recent_hit = np.nan

        decayed = False
        if n >= MIN_SIGNALS_FOR_VERDICT and np.isfinite(recent_hit) and np.isfinite(announced_edge):
            decayed = (recent_hit < announced_edge - STALE_HITRATE_DROP)

        out_rows.append(
            {
                "stream": key[0],
                "phase_id": key[1],
                "day_archetype": key[2],
                "current_window": key[3],
                "n_signals": n,
                "overall_hit_rate": overall_hit,
                "announced_edge_prob": announced_edge,
                "recent_hit_rate": recent_hit,
                "edge_decay": announced_edge - recent_hit if np.isfinite(recent_hit) else np.nan,
                "stale_flag": bool(decayed),
            }
        )
    if not out_rows:
        return pd.DataFrame()
    return pd.DataFrame(out_rows).sort_values(["stale_flag", "n_signals"], ascending=[False, False])


def summary_json(sc: pd.DataFrame, rolling: pd.DataFrame) -> Dict:
    resolved_n = int(sc["resolved"].sum()) if not sc.empty else 0
    hit_n = int(sc["hit"].sum()) if not sc.empty and sc["hit"].notna().any() else 0
    verdict = {
        "total_signals_emitted": int(len(sc)) if not sc.empty else 0,
        "resolved_signals": resolved_n,
        "resolved_hits": hit_n,
        "overall_hit_rate": float(hit_n / resolved_n) if resolved_n else None,
        "last_resolved_date": str(sc[sc["resolved"]]["signal_date"].max()) if not sc.empty and sc["resolved"].any() else None,
        "stale_patterns": (
            rolling[rolling["stale_flag"]].to_dict(orient="records") if not rolling.empty else []
        ),
        "generated_at": datetime.now().isoformat(),
    }
    return verdict


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main() -> Dict:
    print(">>> prediction_scorecard.py starting", flush=True)
    primitives = pd.read_parquet(ART / "primitives.parquet")

    # Collect all historical signals from signals_live.csv (may only hold latest;
    # if a long-term signals_history.csv exists, prefer that)
    history_path = ART / "signals_history.csv"
    if history_path.exists():
        signals = pd.read_csv(history_path)
    else:
        try:
            signals = pd.read_csv(ART / "signals_live.csv")
        except Exception:
            signals = pd.DataFrame()

    sc = build_scorecard(signals, primitives)
    sc.to_csv(ART / "prediction_scorecard.csv", index=False)
    print(f">>> wrote prediction_scorecard.csv ({len(sc)} rows)", flush=True)

    rolling = rolling_metrics(sc)
    rolling.to_csv(ART / "prediction_rolling_metrics.csv", index=False)
    print(f">>> wrote prediction_rolling_metrics.csv ({len(rolling)} rows)", flush=True)

    verdict = summary_json(sc, rolling)
    with open(ART / "prediction_scorecard_summary.json", "w") as f:
        json.dump(verdict, f, indent=2, default=str)

    print(f">>> verdict: {verdict}", flush=True)
    return verdict


if __name__ == "__main__":
    main()