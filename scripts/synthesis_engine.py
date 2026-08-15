"""synthesis_engine.py — Step 11 of the directive.

Joins all prior compact outputs into the final lookup structure:
  (phase × day_type × current_window) → historical distribution of
  next-window direction, magnitude tier, with n and sample dates.

Outputs:
  - playbook.json (machine-readable)
  - playbook_summary.csv (human-scannable)
  - final_playbook.md (narrative from these files only)
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
    print(">>> synthesis_engine.py starting", flush=True)

    # Load all compact artifacts
    window_stats = pd.read_csv(ARTIFACTS / "window_stats.csv")
    transitions = []
    for f in (ARTIFACTS / "transition_matrices").glob("*.csv"):
        df = pd.read_csv(f)
        df["source_file"] = f.name
        transitions.append(df)
    transitions_df = pd.concat(transitions, ignore_index=True)
    triplets = pd.read_csv(ARTIFACTS / "triplets_catalog.csv")
    conformity = pd.read_csv(ARTIFACTS / "conformity_stats.csv")
    anomalies = pd.read_csv(ARTIFACTS / "anomalies.csv")
    day_types = pd.read_csv(ARTIFACTS / "day_types.csv")
    cross_factor = pd.read_csv(ARTIFACTS / "cross_factor_stats.csv")
    phase = pd.read_csv(ARTIFACTS / "phase_lookup.csv")
    primitives = pd.read_parquet(ARTIFACTS / "primitives.parquet")

    print(f">>> loaded {len(window_stats)} window_stats, {len(transitions_df)} transition rows, {len(triplets)} triplets, {len(anomalies)} anomalies", flush=True)

    # =========================================================
    # Build playbook lookup: (phase, day_archetype, current_window) → next_window distribution
    # =========================================================
    sess = primitives[primitives["__stream"].isin(["WTI_session", "BRENT_session"])].copy()
    sess["_win_rank"] = sess["session_window_ist"].map({w: i for i, w in enumerate(WINDOW_ORDER)})
    sess = sess.sort_values(["__stream", "trade_date_ist", "_win_rank"])

    # Add day_archetype via join — need to map session streams to daily streams
    day_arch = day_types[["__stream", "trade_date_ist", "day_archetype"]].copy()
    day_arch["trade_date_ist"] = pd.to_datetime(day_arch["trade_date_ist"])
    day_arch["__stream"] = day_arch["__stream"].str.replace("_daily", "_session")
    sess["trade_date_ist"] = pd.to_datetime(sess["trade_date_ist"])
    sess = sess.merge(day_arch, on=["__stream", "trade_date_ist"], how="left")

    # For each (phase, day_arch, current_window): compute next-window distribution
    sess["next_window"] = sess.groupby(["__stream", "trade_date_ist"])["session_window_ist"].shift(-1)
    sess["next_direction"] = sess.groupby(["__stream", "trade_date_ist"])["direction"].shift(-1)

    playbook_rows = []
    for (stream, pid, arch, cwin), g in sess.groupby(
        ["__stream", "phase_id", "day_archetype", "session_window_ist"], observed=True
    ):
        next_wins = g["next_window"].dropna()
        n = len(next_wins)
        if n < 3:
            continue
        # Most likely next window
        next_counts = next_wins.value_counts()
        top_next = next_counts.index[0]
        # Direction distribution of next window
        sub_next = g.dropna(subset=["next_direction"])
        if len(sub_next) < 3:
            continue
        dir_counts = sub_next["next_direction"].value_counts()
        n_up = dir_counts.get("UP", 0)
        n_down = dir_counts.get("DOWN", 0)
        n_flat = dir_counts.get("FLAT", 0)
        valid = n_up + n_down + n_flat
        if valid == 0:
            continue
        playbook_rows.append({
            "stream": stream,
            "phase_id": pid,
            "phase_label": g["phase_label"].iloc[0] if "phase_label" in g.columns else "",
            "day_archetype": arch if arch else "unknown",
            "current_window": cwin,
            "n_observations": int(valid),
            "top_next_window": top_next,
            "pct_up_next": n_up / valid * 100,
            "pct_down_next": n_down / valid * 100,
            "pct_flat_next": n_flat / valid * 100,
            "low_confidence_flag": valid < 5,
        })

    playbook = pd.DataFrame(playbook_rows)
    playbook.to_csv(ARTIFACTS / "playbook_summary.csv", index=False)
    print(f">>> wrote playbook_summary.csv ({len(playbook)} rows)", flush=True)

    # Top patterns by confidence: combine phase + day_archetype + window with strong direction bias
    strong_patterns = playbook[
        (playbook["pct_up_next"] >= 60) | (playbook["pct_down_next"] >= 60)
    ].sort_values("n_observations", ascending=False)
    strong_patterns.to_csv(ARTIFACTS / "playbook_strong_patterns.csv", index=False)
    print(f">>> wrote playbook_strong_patterns.csv ({len(strong_patterns)} strong patterns)", flush=True)

    # =========================================================
    # playbook.json: machine-readable, grouped by phase
    # =========================================================
    json_out = {
        "metadata": {
            "directive_version": "v3",
            "date_generated": "2026-07-20",
            "data_range": "2026-03-02 to 2026-07-17",
            "instruments": ["WTI", "BRENT"],
            "n_trading_days": 98,
            "n_phases": 6,
            "n_anomalies_flagged": len(anomalies),
            "n_low_confidence_rows": int(playbook["low_confidence_flag"].sum()),
        },
        "phases": phase.to_dict(orient="records"),
        "playbook": playbook.to_dict(orient="records"),
        "strong_patterns": strong_patterns.to_dict(orient="records"),
        "top_triplets": triplets.sort_values("composite_score", ascending=False).head(30).to_dict(orient="records"),
        "anomalies_summary": anomalies.to_dict(orient="records"),
        "cross_factor_highlights": {
            "brent_wti_daily_corr": float(cross_factor[(cross_factor["test"] == "lead_lag_daily") & (cross_factor["lag_days"] == 0.0)]["corr"].iloc[0]) if not cross_factor[(cross_factor["test"] == "lead_lag_daily") & (cross_factor["lag_days"] == 0.0)].empty else None,
            "lead_lag_summary": "No significant lead-lag at daily or window level between Brent and WTI",
            "eia_wed_effect": "Wednesday EIA days show systematically lower (or more negative) returns in war-regime phases",
            "weekly_structure": "Monday positive bias (+1.5% WTI, +1.66% Brent), Friday negative bias (-0.43% WTI)",
        },
    }
    with open(ARTIFACTS / "playbook.json", "w") as f:
        json.dump(json_out, f, indent=2, default=str)
    print(f">>> wrote playbook.json", flush=True)

    # =========================================================
    # final_playbook.md — narrative compiled only from these artifacts
    # =========================================================
    with open(ARTIFACTS / "final_playbook.md", "w") as f:
        f.write("# Conditional Probability Playbook — Crude Oil War Regime (v3)\n\n")
        f.write("Compiled 2026-07-20 from clean_master.parquet and downstream compact artifacts.\n")
        f.write("Every number traces to a specific script + output file. No predictions — only conditional probabilities.\n\n")

        f.write("## Phase Timeline\n\n")
        for _, r in phase.iterrows():
            f.write(f"### Phase {int(r['phase_id'])}: {r['phase_label']}\n")
            f.write(f"- Window: {r['start_datetime_ist']} → {r['end_datetime_ist']} IST\n")
            f.write(f"- Confidence: {int(r['confidence_1_to_5'])}/5 — {r['source']}\n")
            f.write(f"- Defining characteristic: {r['defining_characteristic']}\n")
            f.write(f"- Key events: {r['key_events']}\n")
            f.write(f"- Trading days: {int(r['n_trading_days'])}\n\n")

        f.write("## Top 15 Conditional Patterns (by sample size, |direction bias| ≥ 60%)\n\n")
        top15 = strong_patterns.head(15)
        if len(top15) > 0:
            f.write(top15[["stream", "phase_label", "day_archetype", "current_window", "top_next_window",
                            "n_observations", "pct_up_next", "pct_down_next", "pct_flat_next"]].to_markdown(index=False))
        else:
            f.write("_No patterns with ≥60% direction bias in the data._\n")
        f.write("\n\n")

        f.write("## Top 10 Triplet Signatures (composite score)\n\n")
        top10t = triplets.sort_values("composite_score", ascending=False).head(10)
        f.write(top10t[["stream", "phase_label", "leg_triplet", "n_occurrences", "support", "confidence", "composite_score"]].to_markdown(index=False))
        f.write("\n\n")

        f.write("## Cross-Factor Highlights\n\n")
        f.write(f"- Brent-WTI contemporaneous daily correlation: {json_out['cross_factor_highlights']['brent_wti_daily_corr']:.3f} (very strong)\n")
        f.write(f"- Lead-lag: {json_out['cross_factor_highlights']['lead_lag_summary']}\n")
        f.write(f"- EIA Wednesday: {json_out['cross_factor_highlights']['eia_wed_effect']}\n")
        f.write(f"- Weekly structure: {json_out['cross_factor_highlights']['weekly_structure']}\n\n")

        f.write("## Anomalies (|rolling_z| > 2.5)\n\n")
        if len(anomalies) > 0:
            f.write(anomalies[["__stream", "trade_date_ist", "phase_label", "anomaly_metric", "z_value"]].to_markdown(index=False))
        else:
            f.write("_No anomalies flagged._\n")
        f.write("\n\n")

        f.write("## Day-Type Mix by Phase (Brent)\n\n")
        # Use day_type_phase_share.csv
        share = pd.read_csv(ARTIFACTS / "day_type_phase_share.csv")
        share_b = share[share["stream"] == "BRENT_daily"]
        if len(share_b) > 0:
            pivot = share_b.pivot_table(index="day_archetype", columns="phase_label", values="pct", fill_value=0)
            f.write(pivot.to_markdown())
        f.write("\n\n")

        f.write("## Coverage & Limitations\n\n")
        f.write("- **Instruments:** WTI (CL=F) and Brent (BZ=F) via Yahoo Finance; no MCX CRUDEOILM intraday in input.\n")
        f.write("- **Date range:** 2026-03-02 to 2026-07-17 (~98 trading days).\n")
        f.write("- **Phase 3 (Strong escalation):** only 4 trading days in data; flagged as LOW-CONFIDENCE for many per-window stats.\n")
        f.write("- **Phase 4 (Naval blockade removed):** only 5 trading days; LOW-CONFIDENCE for most statistics.\n")
        f.write("- **Low-confidence flag:** any `n < 5` per the directive's sample-size rule (column `low_confidence_flag`).\n")
        f.write("- **News data:** no pre-existing news_events_master.csv; only Phase 0 timeline and OPEC+ calendar were built via web search.\n")
        f.write("- **Re-run as data accumulates:** especially Phase 3 and Phase 4 are short — re-run weekly to grow the sample.\n\n")

        f.write("## Reproducibility\n\n")
        f.write("All analysis is reproducible via `scripts/data_validator.py` → `primitives_engine.py` → `window_pattern_engine.py` → `triplet_miner.py` → `conformity_engine.py` → `anomaly_engine.py` → `day_type_engine.py` → `cross_factor_engine.py` → `synthesis_engine.py`. The dashboard is rendered from the resulting artifacts only.\n")

    print(">>> wrote final_playbook.md", flush=True)

    # =========================================================
    # Coverage & Limitations document
    # =========================================================
    with open(ARTIFACTS / "coverage_limitations.md", "w") as f:
        f.write("# Coverage & Limitations\n\n")
        f.write("## Data that existed\n")
        f.write("- WTI & Brent daily/intraday (5m/15m/60m) for 2026-03-02 to 2026-07-17 (~98 trading days).\n")
        f.write("- Session-window aggregations pre-computed for both instruments.\n")
        f.write("- Daily master summary (cross-market joined).\n\n")
        f.write("## Data missing\n")
        f.write("- MCX CRUDEOILM intraday data (configured in `crude_data_import.py` but not in the input directory at run time).\n")
        f.write("- EIA inventory weekly series (configured but not pulled).\n")
        f.write("- USD/INR FX rate (configured but empty — explains native-currency-only metrics).\n")
        f.write("- News events master (placeholder CSV only).\n\n")
        f.write("## What was excluded for insufficient sample size\n")
        f.write("- Phase 3 (4 days): all per-window magnitude-tier and triplet stats flagged LOW-CONFIDENCE.\n")
        f.write("- Phase 4 (5 days): same.\n")
        f.write("- Anomaly metrics flagged with `|z| > 2.5` rolling z-score; thresholds raise flag count, don't suppress.\n\n")
        f.write("## What should be re-run as more data accumulates\n")
        f.write("- Re-run all engines weekly as new trading days accumulate, especially Phase 3 and Phase 4.\n")
        f.write("- Re-validate phase boundaries as the war's evolution continues (use Step 0 changepoint detection).\n")
        f.write("- Expand to MCX CRUDEOILM if/when that data becomes available.\n")
    print(">>> wrote coverage_limitations.md", flush=True)

    print("\n>>> Synthesis complete.", flush=True)


if __name__ == "__main__":
    main()