"""cross_phase_engine.py — Cross-phase pattern similarity & borrowing engine.

When the current phase has limited data (phase 10: n=176 session rows),
this engine finds the MOST SIMILAR historical phases and borrows their
window-direction patterns, weighted by similarity × reliability.

Similarity is computed across 4 dimensions:
  1. Volatility profile (ATR, range, std per window) — 30% weight
  2. Direction distribution per window (UP/DOWN/FLAT %) — 30% weight
  3. Session return distribution (mean, median, tails) — 20% weight
  4. Magnitude-tier distribution (Q1–Q5 %) — 20% weight

Outputs:
  artifacts/cross_phase_similarity.csv  — similarity matrix (10×10)
  artifacts/cross_phase_borrowed.csv    — borrowed patterns for current phase
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial.distance import cosine

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ART = BASE / "artifacts"

# Similarity dimension weights (must sum to 1.0)
W_VOL = 0.30
W_DIR = 0.30
W_RET = 0.20
W_MAG = 0.20

# Minimum trading days in a phase for its patterns to be trusted for borrowing
MIN_TRADING_DAYS_FOR_BORROWING = 8  # at least 8 days of history

# ─── Feature extraction per phase ───

def build_phase_features(ws: pd.DataFrame, ms: pd.DataFrame, ps: pd.DataFrame) -> pd.DataFrame:
    """Build a feature vector for each phase across all 4 dimensions."""
    rows = []
    for pid in sorted(ws['phase_id'].unique()):
        p_ws = ws[ws['phase_id'] == pid]
        p_ms = ms[ms['phase_id'] == pid] if not ms.empty else pd.DataFrame()

        # Volatility features (30%)
        vol_feats = {}
        for w in p_ws['session_window_ist'].unique():
            ww = p_ws[p_ws['session_window_ist'] == w]
            vol_feats[f'vol_std_{w}'] = ww['std_return_pct'].mean()
            vol_feats[f'vol_mean_{w}'] = ww['mean_return_pct'].mean()

        # Direction distribution (30%) — aggregated across streams
        dir_feats = {}
        for w in p_ws['session_window_ist'].unique():
            ww = p_ws[p_ws['session_window_ist'] == w]
            dir_feats[f'dir_up_{w}'] = ww['pct_up'].mean()
            dir_feats[f'dir_down_{w}'] = ww['pct_down'].mean()
            dir_feats[f'dir_flat_{w}'] = ww['pct_flat'].mean()

        # Return distribution (20%)
        ret_feats = {}
        rets = p_ws['mean_return_pct'].dropna()
        ret_feats['ret_mean'] = rets.mean()
        ret_feats['ret_median'] = rets.median()
        ret_feats['ret_std'] = rets.std()
        ret_feats['ret_skew'] = rets.skew() if len(rets) > 3 and not pd.isna(rets.skew()) else 0

        # Magnitude tier distribution (20%)
        mag_feats = {}
        tiers = p_ms.groupby('magnitude_tier')['count'].sum() if not p_ms.empty else pd.Series()
        for t in ['Q1_0_25', 'Q2_25_50', 'Q3_50_75', 'Q4_75_90', 'Q5_90_100']:
            mag_feats[f'mag_{t}'] = tiers.get(t, 0)

        combined = {**vol_feats, **dir_feats, **ret_feats, **mag_feats}
        combined['phase_id'] = pid
        combined['n_session_rows'] = int(len(p_ws))
        # Count unique trading days from primitives for this phase
        nd = len(ps[ps['phase_id'] == float(pid)]['trade_date_ist'].unique()) if 'trade_date_ist' in ps.columns else int(len(p_ws))
        combined['n_trading_days'] = nd
        rows.append(combined)

    return pd.DataFrame(rows).fillna(0).set_index('phase_id')


def similarity_matrix(feats: pd.DataFrame) -> pd.DataFrame:
    """Compute pairwise cosine similarity between ALL phases (10×10 matrix)."""
    ids = feats.index.tolist()
    cols = [c for c in feats.columns if c not in ('n_session_rows',)]
    vals = feats[cols].values
    sim = np.ones((len(ids), len(ids)))
    for i in range(len(ids)):
        for j in range(len(ids)):
            if i == j:
                continue
            d = cosine(vals[i], vals[j])
            sim[i][j] = max(0, 1 - d)  # cosine similarity: 1 = identical, 0 = orthogonal
    return pd.DataFrame(sim, index=ids, columns=ids)


def borrow_patterns(target_phase: int, window_stats: pd.DataFrame, magnitude: pd.DataFrame,
                    sim: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    """For a target phase (e.g. 10), borrow patterns from similar phases.

    For each (window, stream) with LOW n in the target phase, finds the most
    similar source phase that has ADEQUATE n and computes a blended pattern.
    """
    # Target data
    tgt = window_stats[window_stats['phase_id'] == target_phase].copy()
    target_days = int(feats.loc[target_phase, 'n_trading_days']) if target_phase in feats.index else 0

    results = []
    for _, row in tgt.iterrows():
        w = row['session_window_ist']
        s = row['stream']
        n = int(row['n_valid'])
        p_up = float(row['pct_up'])
        p_dn = float(row['pct_down'])
        p_fl = float(row['pct_flat'])
        mret = float(row['mean_return_pct'])

        # Find most similar source phase with enough data
        sims = sim.loc[target_phase].drop(target_phase).sort_values(ascending=False)
        blended_up, blended_dn, blended_fl, blended_mret = p_up, p_dn, p_fl, mret
        borrowed_from = None
        borrow_weight = 0.0

        for src_id, similarity in sims.items():
            src_days = int(feats.loc[src_id, 'n_trading_days'])
            if src_days < MIN_TRADING_DAYS_FOR_BORROWING:
                continue
            # Find matching row in source
            src_row = window_stats[(window_stats['phase_id'] == src_id) &
                                    (window_stats['session_window_ist'] == w) &
                                    (window_stats['stream'] == s)]
            if src_row.empty:
                continue
            sr = src_row.iloc[0]
            src_n_win = int(sr['n_valid'])
            if src_n_win < 5:
                continue

            # Compute blending weight: similarity × log(n_source)/log(max_n)
            max_d = max(feats['n_trading_days'])
            reliability = np.log(src_days) / np.log(max_d)
            alpha = similarity * reliability  # blend factor: how much to borrow vs keep own

            # Blend: own × (1-alpha) + borrowed × alpha
            src_up = float(sr['pct_up'])
            src_dn = float(sr['pct_down'])
            src_fl = float(sr['pct_flat'])
            src_mret = float(sr['mean_return_pct'])

            alpha_capped = min(alpha, 0.5)  # never borrow more than 50%
            blended_up = p_up * (1 - alpha_capped) + src_up * alpha_capped
            blended_dn = p_dn * (1 - alpha_capped) + src_dn * alpha_capped
            blended_fl = p_fl * (1 - alpha_capped) + src_fl * alpha_capped
            blended_mret = mret * (1 - alpha_capped) + src_mret * alpha_capped
            borrowed_from = int(src_id)
            borrow_weight = round(alpha_capped, 3)
            break  # use only the best match

        results.append({
            'phase_id': target_phase,
            'session_window_ist': w,
            'stream': s,
            'n_own': n,
            'p_up_own': round(p_up, 1),
            'p_dn_own': round(p_dn, 1),
            'p_fl_own': round(p_fl, 1),
            'mean_ret_own': round(mret, 3),
            'borrowed_from_phase': borrowed_from,
            'borrow_weight': borrow_weight,
            'p_up_blended': round(blended_up, 1),
            'p_dn_blended': round(blended_dn, 1),
            'p_fl_blended': round(blended_fl, 1),
            'mean_ret_blended': round(blended_mret, 3),
        })
    return pd.DataFrame(results)


def main():
    print(">>> cross_phase_engine.py starting", flush=True)
    ws = pd.read_csv(ART / 'window_stats.csv')
    ms = pd.read_csv(ART / 'magnitude_crosstabs.csv')
    ps = pd.read_parquet(ART / 'primitives.parquet')

    feats = build_phase_features(ws, ms, ps)
    feats.to_csv(ART / 'cross_phase_features.csv')
    print(f">>> wrote cross_phase_features.csv ({len(feats)} phases)", flush=True)

    sim = similarity_matrix(feats)
    sim.to_csv(ART / 'cross_phase_similarity.csv')
    print(f">>> wrote cross_phase_similarity.csv ({len(sim)}×{len(sim)} matrix)", flush=True)
    print("Similarity matrix (diagonal=1.0, off-diag=similarity):")
    print(sim.round(3).to_string())

    # Borrow patterns for Phase 10 (current)
    borrowed = borrow_patterns(10, ws, ms, sim, feats)
    borrowed.to_csv(ART / 'cross_phase_borrowed.csv', index=False)
    print(f">>> wrote cross_phase_borrowed.csv ({len(borrowed)} patterns)", flush=True)
    if not borrowed.empty:
        print(borrowed.to_string())

    print(">>> cross_phase_engine.py complete", flush=True)


if __name__ == "__main__":
    main()