"""triplet_miner.py — Step 5 of the directive.

Sequential pattern mining over window-level legs:
  - Encode leg = (direction, magnitude_tier)
  - Enumerate 3-leg sequences (sliding window within day, ordered by WINDOW_ORDER)
  - Compute support = #occurrences / #qualifying days
  - Compute confidence = P(leg3 | leg1, leg2)
  - Composite score = support × consistency × sample confidence
  - Output top-N triplet catalog

Output:
  - triplets_catalog.json
"""

from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"


WINDOW_ORDER = [
    "asia_early", "us_late", "global_reopen_pre_mcx", "mcx_open_drive",
    "india_morning", "india_midday", "europe_midday", "us_pre_open",
    "us_open", "mcx_tail",
]


def main():
    print(">>> triplet_miner.py starting", flush=True)
    p = pd.read_parquet(ARTIFACTS / "primitives.parquet")
    phase = pd.read_csv(ARTIFACTS / "phase_lookup.csv")
    sess = p[p["__stream"].isin(["WTI_session", "BRENT_session"])].copy()

    # Sort by (stream, date, window order) so triplets are within a day in chronological order
    sess["_win_rank"] = sess["session_window_ist"].map({w: i for i, w in enumerate(WINDOW_ORDER)})
    sess = sess.sort_values(["__stream", "trade_date_ist", "_win_rank"]).reset_index(drop=True)

    # Drop UNCLASSIFIED legs
    sess = sess[sess["leg"] != "UNCLASSIFIED"]
    sess = sess[sess["magnitude_tier"] != "UNCLASSIFIED"]

    # Build triplet string per (stream, date) using rolling window of size 3
    def build_triplets(g):
        g = g.sort_values("_win_rank")
        legs = g["leg"].tolist()
        wins = g["session_window_ist"].tolist()
        rows = []
        for i in range(len(legs) - 2):
            rows.append({
                "leg1": legs[i], "win1": wins[i],
                "leg2": legs[i+1], "win2": wins[i+1],
                "leg3": legs[i+2], "win3": wins[i+2],
                "leg_triplet": "|".join([legs[i], legs[i+1], legs[i+2]]),
                "win_triplet": "|".join([wins[i], wins[i+1], wins[i+2]]),
            })
        return pd.DataFrame(rows)

    # Build triplets manually per (stream, date) — avoids groupby.apply index issue
    all_triplets = []
    for (stream, dt), g in sess.groupby(["__stream", "trade_date_ist"], observed=True):
        df = build_triplets(g)
        if df.empty:
            continue
        df["__stream"] = stream
        df["trade_date_ist"] = dt
        all_triplets.append(df)
    triplets = pd.concat(all_triplets, ignore_index=True) if all_triplets else pd.DataFrame()
    print(f">>> raw triplets: {len(triplets):,}", flush=True)

    # Bring in phase_id from sess by joining
    phase_map = sess[["__stream", "trade_date_ist", "phase_id", "phase_label"]].drop_duplicates(
        subset=["__stream", "trade_date_ist"]
    )
    triplets = triplets.merge(phase_map, on=["__stream", "trade_date_ist"], how="left")

    # =========================================================
    # Per-phase + stream counts
    # =========================================================
    catalog = []
    for (sym, pid, sig), g in triplets.groupby(["__stream", "phase_id", "leg_triplet"], observed=True):
        # Counts and basic stats
        n_occurrences = len(g)
        # Number of unique dates that could yield this triplet (denominator for support)
        # All dates in this phase × stream
        phase_dates = phase_map[(phase_map["__stream"] == sym) & (phase_map["phase_id"] == pid)]
        n_phase_dates = len(phase_dates)
        support = n_occurrences / n_phase_dates if n_phase_dates else 0

        # Confidence: of all (leg1, leg2) → leg3 occurrences, how often does leg3 = the chosen one?
        # Build denominator: count of (leg1, leg2) for this stream × phase
        denom = len(triplets[(triplets["__stream"] == sym) & (triplets["phase_id"] == pid)
                              & (triplets["leg1"] + "|" + triplets["leg2"] ==
                                 sig.split("|")[0] + "|" + sig.split("|")[1])])
        confidence = n_occurrences / denom if denom else 0

        # Consistency = std of leg1 returns for this triplet
        consistency = 1 / (1 + abs(support - confidence))

        composite = support * consistency * min(1.0, n_occurrences / 5.0)  # confidence-penalty for low n

        # Sample-confidence flag
        low_conf = n_occurrences < 5 or n_phase_dates < 5

        # Get example dates
        sample_dates = sorted(g["trade_date_ist"].dt.strftime("%Y-%m-%d").unique().tolist())[:5]
        # Get example window triple
        sample_wins = g["win_triplet"].mode().iloc[0] if not g["win_triplet"].mode().empty else ""

        catalog.append({
            "stream": sym,
            "phase_id": int(pid),
            "phase_label": phase.loc[phase["phase_id"] == pid, "phase_label"].iloc[0] if (phase["phase_id"] == pid).any() else "",
            "leg_triplet": sig,
            "example_window_triplet": sample_wins,
            "n_occurrences": int(n_occurrences),
            "n_phase_dates": int(n_phase_dates),
            "support": float(support),
            "confidence": float(confidence),
            "consistency": float(consistency),
            "composite_score": float(composite),
            "low_confidence_flag": bool(low_conf),
            "sample_dates": sample_dates,
        })

    catalog_df = pd.DataFrame(catalog).sort_values(["stream", "phase_id", "composite_score"], ascending=[True, True, False])

    # Output JSON (top-N ranked)
    # Show all entries, but prioritize non-low-confidence
    ranked = catalog_df.sort_values(
        ["low_confidence_flag", "composite_score"], ascending=[True, False]
    )
    out = ARTIFACTS / "triplets_catalog.json"
    with open(out, "w") as f:
        json.dump(ranked.to_dict(orient="records"), f, indent=2, default=str)
    print(f">>> wrote {out} ({len(ranked)} entries)", flush=True)

    # Also write a CSV view
    ranked.drop(columns=["sample_dates"]).to_csv(ARTIFACTS / "triplets_catalog.csv", index=False)
    print(f">>> wrote triplets_catalog.csv", flush=True)

    # Show top 30
    print("\n>>> Top 30 triplets (low-conf filtered):", flush=True)
    display = ranked[~ranked["low_confidence_flag"]].head(30)
    if len(display) == 0:
        print("  No non-low-confidence triplets; showing top 30 overall", flush=True)
        display = ranked.head(30)
    print(display[["stream", "phase_label", "leg_triplet", "n_occurrences", "support", "confidence", "composite_score"]].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()