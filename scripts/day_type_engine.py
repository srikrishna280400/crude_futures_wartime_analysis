"""day_type_engine.py — Step 8 of the directive.

Classify whole days into repeatable archetypes (gap-and-hold, gap-and-fade,
late-session-decisive, range-bound-all-day, whipsaw-two-sided, all-day-trend,
mixed-regime). Cross-tab by phase. Optional KMeans cross-check.

Outputs:
  - day_types.csv (per date × stream classification)
  - day_type_phase_crosstab.csv
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"


def classify_day(row) -> str:
    """Rule-based archetype classification using existing daily metrics.

    Each directional label is suffixed with _up or _down so the trader
    can tell at a glance which way the day was trending. e.g.:
      - all_day_trend_up vs all_day_trend_down
      - late_session_decisive_up vs late_session_decisive_down
    Direction is sourced from body_direction (UP / DOWN / FLAT).

    Returns one of:
      gap_and_hold_up, gap_and_hold_down, gap_and_fade,
      all_day_trend_up, all_day_trend_down,
      whipsaw_two_sided,
      late_session_decisive_up, late_session_decisive_down,
      range_bound, mixed_regime, unknown
    """
    gap = row.get("gap_pct_native", np.nan)
    body = row.get("body_pct_native", np.nan)
    rng = row.get("day_range_pct_native", np.nan)
    cloc = row.get("close_location_in_range_pct", np.nan)
    efficiency = row.get("day_efficiency_ratio", np.nan)
    reversal = row.get("intraday_reversal_flag", False)
    trend = row.get("trendiness_score_1_to_5", np.nan)
    whipsaw = row.get("whipsaw_score_1_to_5", np.nan)
    direction = str(row.get("body_direction", "")).upper()  # UP / DOWN / FLAT / NaN

    if pd.isna(rng) or rng <= 0:
        return "unknown"

    # Gap relative to range
    gap_ratio = abs(gap) / rng if pd.notna(gap) and rng > 0 else 0

    if gap_ratio > 0.4:
        # Significant gap
        if pd.notna(body) and pd.notna(gap) and ((body > 0 and gap > 0) or (body < 0 and gap < 0)):
            # Body confirms gap direction → gap and hold
            return "gap_and_hold_up" if body > 0 else "gap_and_hold_down"
        else:
            return "gap_and_fade"

    if pd.notna(trend) and trend >= 4 and pd.notna(efficiency) and efficiency >= 0.5:
        # Trending day — split by direction so trader knows up vs down
        if direction == "UP":
            return "all_day_trend_up"
        if direction == "DOWN":
            return "all_day_trend_down"
        # FLAT body but high trend score is rare; treat as up by default
        return "all_day_trend_up"

    if pd.notna(whipsaw) and whipsaw >= 4:
        # Whipsaw = both sides hurt; direction is ambiguous by construction.
        # Keep as direction-agnostic label (intentional).
        return "whipsaw_two_sided"

    if pd.notna(cloc) and (cloc >= 80 or cloc <= 20):
        # Decisive late-session move — split by direction
        if cloc >= 80:
            return "late_session_decisive_up"
        if cloc <= 20:
            return "late_session_decisive_down"
        return "late_session_decisive_up"

    if pd.notna(efficiency) and efficiency < 0.3:
        # Range-bound = no clear direction by definition
        return "range_bound"

    return "mixed_regime"


def main():
    print(">>> day_type_engine.py starting", flush=True)
    master = pd.read_parquet(ARTIFACTS / "clean_master.parquet")
    daily = master[master["__stream"].isin(["WTI_daily", "BRENT_daily"])].copy()
    print(f">>> daily rows: {len(daily)}", flush=True)

    # Apply classification
    daily["day_archetype"] = daily.apply(classify_day, axis=1)

    # Compact day_types.csv
    keep_cols = ["__stream", "trade_date_ist", "phase_id", "phase_label",
                 "gap_pct_native", "body_pct_native", "body_direction",
                 "day_range_pct_native", "close_location_in_range_pct",
                 "day_efficiency_ratio", "trendiness_score_1_to_5",
                 "whipsaw_score_1_to_5", "intraday_reversal_flag",
                 "did_gap_up", "did_gap_down", "extreme_gap_flag",
                 "day_archetype"]
    for c in keep_cols:
        if c not in daily.columns:
            daily[c] = np.nan
    daily[keep_cols].to_csv(ARTIFACTS / "day_types.csv", index=False)
    print(f">>> wrote day_types.csv", flush=True)

    # Cross-tab: archetype × phase
    ct = pd.crosstab(
        [daily["__stream"], daily["day_archetype"]],
        daily["phase_id"].fillna(-1).astype(int),
        margins=False,
        dropna=True,
    )
    ct_long = ct.reset_index().melt(id_vars=["__stream", "day_archetype"],
                                     var_name="phase_id", value_name="count")
    ct_long.to_csv(ARTIFACTS / "day_type_phase_crosstab.csv", index=False)
    print(f">>> wrote day_type_phase_crosstab.csv", flush=True)

    # Per-phase archetype share
    pct_share = []
    for (stream, pid), g in daily.groupby(["__stream", "phase_id"], observed=True):
        if g["day_archetype"].isna().all() or (g["day_archetype"] == "unknown").all():
            continue
        n = len(g)
        for arch, c in g["day_archetype"].value_counts().items():
            pct_share.append({
                "stream": stream,
                "phase_id": pid,
                "phase_label": g["phase_label"].iloc[0] if "phase_label" in g.columns else "",
                "day_archetype": arch,
                "count": int(c),
                "pct": c / n * 100,
                "low_confidence_flag": n < 5,
            })
    pct_df = pd.DataFrame(pct_share).sort_values(
        ["stream", "phase_id", "pct"], ascending=[True, True, False]
    )
    pct_df.to_csv(ARTIFACTS / "day_type_phase_share.csv", index=False)
    print(pct_df.head(30).to_string(index=False), flush=True)

    # =========================================================
    # Optional KMeans cross-check on standardized daily features
    # =========================================================
    feat_cols = ["gap_pct_native", "body_pct_native", "day_range_pct_native",
                 "close_location_in_range_pct", "day_efficiency_ratio",
                 "trendiness_score_1_to_5", "whipsaw_score_1_to_5"]
    feat_cols = [c for c in feat_cols if c in daily.columns]
    if len(feat_cols) >= 3:
        scaler = StandardScaler()
        # Only fit on rows with all features
        mask = daily[feat_cols].notna().all(axis=1)
        if mask.sum() >= 10:
            X = scaler.fit_transform(daily.loc[mask, feat_cols])
            km = KMeans(n_clusters=4, random_state=42, n_init=10).fit(X)
            daily.loc[mask, "kmeans_cluster"] = km.labels_
            # Compare cluster to archetype
            cmp = pd.crosstab(
                daily.loc[mask, "day_archetype"],
                daily.loc[mask, "kmeans_cluster"]
            )
            cmp.to_csv(ARTIFACTS / "kmeans_archetype_crosstab.csv")
            print(f"\nKMeans × archetype crosstab:", flush=True)
            print(cmp.to_string(), flush=True)

    print(">>> done", flush=True)


if __name__ == "__main__":
    main()
