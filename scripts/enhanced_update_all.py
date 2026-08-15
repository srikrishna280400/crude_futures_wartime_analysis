"""enhanced_update_all.py — Enhanced auto-update pipeline integrating all new components.

This extends the original update_all.py to include:
1. Enhanced data ingestion with MCX support
2. Live regime classifier retraining
3. Probabilistic signal engine
4. Walk-forward backtester
5. Enhanced cross-asset macro overlays
6. News/event engine
7. Enhanced dashboard with live signals

Usage:
    python scripts/enhanced_update_all.py              # Full refresh
    python scripts/enhanced_update_all.py --incremental  # Only process changed files
    python scripts/enhanced_update_all.py --signals-only  # Generate today's signals only
    python scripts/enhanced_update_all.py --dashboard-only  # Rebuild dashboard only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd

# ─── Configuration ────────────────────────────────────────────────────────────

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
SCRIPTS = BASE / "scripts"
ARTIFACTS = BASE / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

# Pipeline steps (order matters - dependencies)
PIPELINE_STEPS = [
    {
        "id": "data_ingestion",
        "name": "Enhanced Data Ingestion",
        "script": "enhanced_data_ingestion.py",
        "description": "Ingest source CSVs, detect changes, generate MCX data",
        "outputs": [
            "clean_master.parquet",
            "phase_lookup.csv",
            "pruning_log.md",
            "data_validator_summary.csv",
            "data_validator_phase_summary.csv",
            # MCX files
            "mcx_crudeoilm_daily_ist.csv",
            "mcx_crudeoilm_5m_ist.csv",
            "mcx_crudeoilm_15m_ist.csv",
            "mcx_crudeoilm_60m_ist.csv",
            "mcx_session_windows_summary.csv",
            "mcx_spot_daily_reference_ist.csv",
        ],
        "required": True,
    },
    {
        "id": "data_validator",
        "name": "Data Validator (rebuild clean_master)",
        "script": "data_validator.py",
        "description": "Load source CSVs + session summaries, phase-tag via merge_asof vs phase_lookup, prune invariant cols, rebuild clean_master.parquet. MUST run after ingestion so downstream engines see freshly appended dates.",
        "outputs": [
            "clean_master.parquet",
            "pruning_log.md",
            "data_validator_summary.csv",
            "data_validator_phase_summary.csv",
        ],
        "required": True,
    },
    {
        "id": "primitives",
        "name": "Primitives Engine",
        "script": "primitives_engine.py",
        "description": "Compute window returns, regime-relative thresholds, magnitude tiers, legs",
        "outputs": [
            "primitives.parquet",
            "primitives_summary.csv",
            "definitions.md",
        ],
        "required": True,
    },
    {
        "id": "window_patterns",
        "name": "Window Pattern Engine",
        "script": "window_pattern_engine.py",
        "description": "Direction splits, transition matrices, magnitude distributions, high/low attribution",
        "outputs": [
            "window_stats.csv",
            "daily_high_low_window.csv",
            "daily_high_low_counts_by_phase.csv",
            "magnitude_crosstabs.csv",
            "magnitude_x_eia.csv",
            "transition_matrices/",
        ],
        "required": True,
    },
    {
        "id": "triplets",
        "name": "Triplet Miner",
        "script": "triplet_miner.py",
        "description": "Sequential 3-leg pattern mining with composite scoring",
        "outputs": [
            "triplets_catalog.json",
            "triplets_catalog.csv",
        ],
        "required": True,
    },
    {
        "id": "conformity",
        "name": "Conformity Engine",
        "script": "conformity_engine.py",
        "description": "Quantitative conformity to trading frameworks (mean reversion, momentum, vol clustering)",
        "outputs": [
            "conformity_stats.csv",
            "volatility_clustering.csv",
            "daily_momentum.csv",
            "session_liquidity_proxy.csv",
            "concept_citations.md",
        ],
        "required": True,
    },
    {
        "id": "anomalies",
        "name": "Anomaly Engine",
        "script": "anomaly_engine.py",
        "description": "Rolling z-score anomaly detection (|z| > 2.5)",
        "outputs": [
            "anomalies.csv",
            "anomaly_summary.csv",
        ],
        "required": True,
    },
    {
        "id": "day_types",
        "name": "Day Type Engine",
        "script": "day_type_engine.py",
        "description": "Day archetype classification (trend, whipsaw, gap-and-hold, range-bound)",
        "outputs": [
            "day_types.csv",
            "day_type_phase_crosstab.csv",
            "day_type_phase_share.csv",
            "kmeans_archetype_crosstab.csv",
        ],
        "required": True,
    },
    {
        "id": "cross_factor",
        "name": "Cross-Factor Engine",
        "script": "cross_factor_engine.py",
        "description": "Brent-WTI lead-lag, EIA Wednesday, weekly structure, OPEC+, expiry proximity",
        "outputs": [
            "cross_factor_stats.csv",
            "opec_calendar.csv",
        ],
        "required": True,
    },
    {
        "id": "statistical_rigor",
        "name": "Statistical Rigor",
        "script": "statistical_rigor.py",
        "description": "FDR correction, Bayesian posteriors, hierarchical shrinkage",
        "outputs": [
            "window_stats_fdr.csv",
            "triplet_fdr.csv",
            "bayesian_posteriors.csv",
            "playbook_shrunk.csv",
            "significant_window_bias.csv",
        ],
        "required": True,
    },
    {
        "id": "synthesis",
        "name": "Synthesis Engine",
        "script": "synthesis_engine.py",
        "description": "Compile all artifacts into conditional probability playbook",
        "outputs": [
            "playbook.json",
            "playbook_summary.csv",
            "playbook_strong_patterns.csv",
            "final_playbook.md",
            "coverage_limitations.md",
        ],
        "required": True,
    },
    # NEW ENHANCED STEPS
    {
        "id": "regime_classifier",
        "name": "Live Regime Classifier",
        "script": "live_regime_classifier.py",
        "description": "Train/update regime classifier, predict current phase",
        "outputs": [
            "models/regime_classifier.pkl",
            "regime_diagnostics.json",
            "regime_feature_importance.csv",
            "regime_features.csv",
            "regime_predictions_live.csv",
        ],
        "required": False,
        "mode": "train",  # or "predict"
    },
    {
        "id": "signal_engine",
        "name": "Probabilistic Signal Engine",
        "script": "probabilistic_signal_engine.py",
        "description": "Generate today's trading signals with Bayesian posteriors, Kelly sizing, ATR stops",
        "outputs": [
            "signals_live.csv",
            "signals_history.csv",
            "signal_performance.csv",
        ],
        "required": False,
    },
    {
        "id": "prediction_scorecard",
        "name": "Prediction Scorecard (P1)",
        "script": "prediction_scorecard.py",
        "description": "Resolve each emitted signal against actual next-window outcome; rolling hit-rate & edge-decay; flags stale patterns",
        "outputs": [
            "prediction_scorecard.csv",
            "prediction_rolling_metrics.csv",
            "prediction_scorecard_summary.json",
        ],
        "required": False,
    },
    {
        "id": "daily_report",
        "name": "Daily News-Conditional Plan",
        "script": "daily_report_generator.py",
        "description": "Build the NEXT-trading-day window-by-window plan from artifacts + live news (Al Jazeera/CNN/X) + escalation/de-escalation scenarios",
        "outputs": [
            "daily_trading_report_*.md",
            "daily_trading_report_*.json",
            "TODAYS_PLAN.md",
        ],
        "required": False,
    },
    {
        "id": "walkforward_backtest",
        "name": "Walk-Forward Backtester",
        "script": "walkforward_backtester.py",
        "description": "Full walk-forward backtest with risk management, Monte Carlo CIs",
        "outputs": [
            "backtest_trades.parquet",
            "backtest_summary.json",
            "backtest_by_signal.csv",
            "backtest_by_phase.csv",
            "backtest_by_archetype.csv",
            "equity_curve.parquet",
        ],
        "required": False,
    },
    {
        "id": "enhanced_cross_asset",
        "name": "Enhanced Cross-Asset Macro",
        "script": "enhanced_cross_asset.py",
        "description": "DXY/SPX/Gold/US10Y/VIX regimes, COT positioning, options vol surface",
        "outputs": [
            "macro_regime.csv",
            "macro_conditional_returns.csv",
            "cot_positioning.csv",
            "options_vol_surface.csv",
            "cross_asset_correlation.json",
        ],
        "required": False,
    },
    {
        "id": "news_events",
        "name": "News/Event Engine",
        "script": "news_event_engine.py",
        "description": "Fetch GDELT/NewsAPI events, correlate with anomalies, map to phases",
        "outputs": [
            "news_events_master.csv",
            "news_daily_summary.csv",
            "news_anomaly_correlation.csv",
            "event_phase_mapping.csv",
            "news_pipeline_summary.json",
        ],
        "required": False,
    },
    {
        "id": "dashboard",
        "name": "Enhanced Dashboard",
        "script": "dashboard_engine_v3_fixed.py",
        "description": "Build interactive HTML dashboard with live signals, macro regime, anomaly alerts",
        "outputs": [
            "dashboard_v3.html",
        ],
        "required": True,
    },
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_checksums() -> Dict[str, str]:
    """Load file checksums for change detection."""
    checksum_file = ARTIFACTS / "source_checksums.json"
    if checksum_file.exists():
        with open(checksum_file) as f:
            return json.load(f)
    return {}

def save_checksums(checksums: Dict[str, str]) -> None:
    """Save file checksums."""
    checksum_file = ARTIFACTS / "source_checksums.json"
    with open(checksum_file, "w") as f:
        json.dump(checksums, f, indent=2)

def compute_checksum(path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    import hashlib
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def check_source_changes() -> Dict[str, bool]:
    """Check which source files have changed since last run."""
    source_files = [
        "wti_daily_ist.csv", "brent_daily_ist.csv",
        "wti_5m_ist.csv", "brent_5m_ist.csv",
        "wti_15m_ist.csv", "brent_15m_ist.csv",
        "wti_60m_ist.csv", "brent_60m_ist.csv",
        "wti_session_windows_summary.csv", "brent_session_windows_summary.csv",
        "daily_master_summary.csv",
        "wti_spot_daily_reference_ist.csv", "brent_spot_daily_reference_ist.csv",
    ]

    checksums = load_checksums()
    changes = {}

    for fname in source_files:
        fpath = BASE / fname
        if not fpath.exists():
            changes[fname] = False
            continue

        current = compute_checksum(fpath)
        cached = checksums.get(fname, "")
        changes[fname] = current != cached

    return changes

def run_step(step: Dict, mode: str = "train", quiet: bool = False) -> bool:
    """Run a single pipeline step."""
    script_path = SCRIPTS / step["script"]
    if not script_path.exists():
        print(f"  !! Script not found: {script_path}")
        return False

    cmd = [sys.executable, str(script_path)]
    if mode and "mode" in step:
        cmd.append(mode)

    if not quiet:
        print(f"\n{'='*60}")
        print(f">>> {step['name']} ({step['script']})")
        print(f"    {step['description']}")
        print(f"{'='*60}")

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(BASE),
            capture_output=quiet,
            text=True,
            timeout=3600,
        )
        elapsed = time.time() - start

        if result.returncode != 0:
            print(f"  !! FAILED after {elapsed:.1f}s (exit code {result.returncode})")
            if quiet and result.stderr:
                print(result.stderr[-2000:])
            return False

        if not quiet:
            print(f"  OK ({elapsed:.1f}s)")

        # Verify outputs
        for out in step.get("outputs", []):
            out_path = ARTIFACTS / out
            if not out_path.exists() and not quiet:
                print(f"  !! Expected output missing: {out}")

        return True

    except subprocess.TimeoutExpired:
        print(f"  !! TIMEOUT after 1 hour")
        return False
    except Exception as e:
        print(f"  !! ERROR: {e}")
        return False

def update_checksums() -> None:
    """Update checksums for all source files after successful run."""
    source_files = [
        "wti_daily_ist.csv", "brent_daily_ist.csv",
        "wti_5m_ist.csv", "brent_5m_ist.csv",
        "wti_15m_ist.csv", "brent_15m_ist.csv",
        "wti_60m_ist.csv", "brent_60m_ist.csv",
        "wti_session_windows_summary.csv", "brent_session_windows_summary.csv",
        "daily_master_summary.csv",
        "wti_spot_daily_reference_ist.csv", "brent_spot_daily_reference_ist.csv",
    ]

    checksums = {}
    for fname in source_files:
        fpath = BASE / fname
        if fpath.exists():
            checksums[fname] = compute_checksum(fpath)

    save_checksums(checksums)

def generate_daily_report(results: Dict[str, Any]) -> str:
    """Generate a daily execution report."""
    report = f"""
# Crude Oil War-Regime Pipeline — Daily Report
**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Mode:** {results.get('mode', 'full')}

## Execution Summary
- **Total Steps:** {results.get('total_steps', 0)}
- **Successful:** {results.get('successful', 0)}
- **Failed:** {results.get('failed', 0)}
- **Skipped:** {results.get('skipped', 0)}
- **Duration:** {results.get('duration', 0):.1f}s

## Step Results
"""
    for step_result in results.get("steps", []):
        status = "✅" if step_result["success"] else "❌"
        report += f"- {status} **{step_result['name']}** ({step_result['duration']:.1f}s)\n"
        if not step_result["success"]:
            report += f"  - Error: {step_result.get('error', 'Unknown')}\n"

    report += f"""

## Key Outputs
"""
    # Check for key artifacts
    key_outputs = [
        "signals_live.csv",
        "signals_history.csv",
        "playbook.json",
        "dashboard_v3.html",
        "regime_predictions_live.csv",
        "backtest_summary.json",
        "prediction_scorecard.csv",
        "prediction_rolling_metrics.csv",
        "prediction_scorecard_summary.json",
        "news_pipeline_summary.json",
        "TODAYS_PLAN.md",
    ]

    for out in key_outputs:
        path = ARTIFACTS / out
        if path.exists():
            size = path.stat().st_size
            mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime('%H:%M:%S')
            report += f"- ✅ {out} ({size:,} bytes, updated {mtime})\n"
        else:
            report += f"- ❌ {out} (missing)\n"

    # Latest signal summary
    signals_path = ARTIFACTS / "signals_live.csv"
    if signals_path.exists():
        try:
            sigs = pd.read_csv(signals_path)
            if not sigs.empty:
                report += f"\n## Today's Signals ({len(sigs)} generated)\n"
                for _, s in sigs.head(5).iterrows():
                    report += f"- {s['signal_id']}: {s['stream']} P{s['phase_id']} {s['current_window']}→{s['next_window']} {s['direction']} @ {s['confidence_score']:.2f} conf\n"
        except Exception:
            pass

    # Latest regime prediction
    regime_path = ARTIFACTS / "regime_predictions_live.csv"
    if regime_path.exists():
        try:
            regime = pd.read_csv(regime_path)
            if not regime.empty:
                latest = regime.iloc[-1]
                report += f"\n## Current Regime Prediction\n"
                report += f"- Phase: {latest.get('phase_id', 'N/A')} ({latest.get('phase_label', 'N/A')})\n"
                report += f"- Confidence: {latest.get('confidence', 0):.1%}\n"
                report += f"- Model Version: {latest.get('model_version', 'N/A')}\n"
        except Exception:
            pass

    return report

# ─── Main Pipeline ────────────────────────────────────────────────────────────

def run_pipeline(
    incremental: bool = False,
    signals_only: bool = False,
    dashboard_only: bool = False,
    quiet: bool = False,
    skip_steps: List[str] = None,
    only_steps: List[str] = None,
) -> Dict[str, Any]:
    """Run the enhanced pipeline."""

    if not quiet:
        print(f"\n{'#'*70}")
        print(f"ENHANCED CRUDE OIL WAR-REGIME PIPELINE")
        print(f"{'Incremental' if incremental else 'Full'} run | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*70}\n")

    start_time = time.time()

    # Check source changes
    changes = check_source_changes()
    changed_files = [f for f, c in changes.items() if c]

    if not quiet:
        print(f">>> Source file changes detected: {len(changed_files)}")
        for f in changed_files:
            print(f"  - {f}")

    # Determine which steps to run
    steps_to_run = []

    if dashboard_only:
        steps_to_run = [s for s in PIPELINE_STEPS if s["id"] == "dashboard"]
    elif signals_only:
        # signals-only = ensure data is fresh to the last appended date, then
        # generate signals, score them, and emit the news-conditional next-day plan.
        # If source CSVs changed since last run, FIRST run the full data pipeline
        # (ingestion → validator → primitives → … → synthesis) so the report is
        # built from the latest appended date; otherwise jump straight to predict.
        report_steps = [
            s for s in PIPELINE_STEPS
            if s["id"] in ["regime_classifier", "signal_engine",
                           "prediction_scorecard", "daily_report", "dashboard"]
        ]
        if changed_files:
            print(f">>> {len(changed_files)} source file(s) changed — re-running data pipeline to last appended date.", flush=True)
            data_steps = [
                s for s in PIPELINE_STEPS
                if s["id"] in ["data_ingestion", "data_validator", "primitives",
                               "window_patterns", "triplets", "conformity", "anomalies",
                               "day_types", "cross_factor", "statistical_rigor", "synthesis"]
            ]
            steps_to_run = data_steps + report_steps
        else:
            print(">>> No source changes — generating report from existing artifacts.", flush=True)
            steps_to_run = report_steps
        # Run classifier in predict mode
        for s in steps_to_run:
            if s["id"] == "regime_classifier":
                s["mode"] = "predict"
    else:
        steps_to_run = PIPELINE_STEPS.copy()

    # Filter by skip/only
    if skip_steps:
        steps_to_run = [s for s in steps_to_run if s["id"] not in skip_steps]
    if only_steps:
        steps_to_run = [s for s in steps_to_run if s["id"] in only_steps]

    # In incremental mode, skip required steps if no source changes
    if incremental and not changed_files:
        if not quiet:
            print(">>> No source changes detected. Skipping data-dependent steps.")
        # Only run steps that don't depend on raw data
        steps_to_run = [s for s in steps_to_run
                       if s["id"] in ["regime_classifier", "signal_engine",
                                      "prediction_scorecard", "daily_report", "dashboard"]]
        for s in steps_to_run:
            if s["id"] == "regime_classifier":
                s["mode"] = "predict"

    # Execute steps
    results = {
        "mode": "signals_only" if signals_only else ("dashboard_only" if dashboard_only else ("incremental" if incremental else "full")),
        "total_steps": len(steps_to_run),
        "successful": 0,
        "failed": 0,
        "skipped": 0,
        "steps": [],
        "duration": 0,
    }

    for step in steps_to_run:
        step_start = time.time()
        success = run_step(step, mode=step.get("mode", "train"), quiet=quiet)
        step_duration = time.time() - step_start

        step_result = {
            "id": step["id"],
            "name": step["name"],
            "success": success,
            "duration": step_duration,
        }

        if not success:
            step_result["error"] = "Step execution failed"
            results["failed"] += 1
            if step.get("required", True):
                print(f"\n!! Required step failed. Stopping pipeline.")
                break
        else:
            results["successful"] += 1

        results["steps"].append(step_result)

    results["duration"] = time.time() - start_time

    # Update checksums on success (signals-only also updates when it ran the data pipeline)
    update_checksums_ok = (results["failed"] == 0 and not dashboard_only)
    if signals_only and not changed_files:
        update_checksums_ok = False  # nothing re-ingested, keep checksums as-is
    if update_checksums_ok:
        update_checksums()

    # Generate report
    if not quiet:
        report = generate_daily_report(results)
        report_path = ARTIFACTS / f"pipeline_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_path, "w") as f:
            f.write(report)
        print(report)

    return results

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enhanced Crude Oil War-Regime Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/enhanced_update_all.py                    # Full pipeline
  python scripts/enhanced_update_all.py --incremental      # Only if sources changed
  python scripts/enhanced_update_all.py --signals-only     # Generate today's signals
  python scripts/enhanced_update_all.py --dashboard-only   # Rebuild dashboard
  python scripts/enhanced_update_all.py --only regime_classifier signal_engine
  python scripts/enhanced_update_all.py --skip walkforward_backtest news_events
        """
    )

    parser.add_argument("--incremental", action="store_true",
                        help="Only run if source files changed")
    parser.add_argument("--signals-only", action="store_true",
                        help="Generate today's signals only (predict mode)")
    parser.add_argument("--dashboard-only", action="store_true",
                        help="Rebuild dashboard only")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-step output")
    parser.add_argument("--skip", nargs="+", default=[],
                        help="Step IDs to skip")
    parser.add_argument("--only", nargs="+", default=[],
                        help="Run only these step IDs")

    args = parser.parse_args()

    # Validate
    if sum([args.incremental, args.signals_only, args.dashboard_only]) > 1:
        print("Error: --incremental, --signals-only, and --dashboard-only are mutually exclusive")
        sys.exit(1)

    # Valid step IDs
    valid_ids = [s["id"] for s in PIPELINE_STEPS]
    for sid in args.skip + args.only:
        if sid not in valid_ids:
            print(f"Error: Invalid step ID '{sid}'. Valid: {valid_ids}")
            sys.exit(1)

    results = run_pipeline(
        incremental=args.incremental,
        signals_only=args.signals_only,
        dashboard_only=args.dashboard_only,
        quiet=args.quiet,
        skip_steps=args.skip,
        only_steps=args.only,
    )

    # Exit code
    sys.exit(0 if results["failed"] == 0 else 1)

if __name__ == "__main__":
    main()