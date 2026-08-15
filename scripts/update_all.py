"""update_all.py — Single-command orchestrator for the entire pipeline.

PURPOSE
-------
When you add new trading days to the 13 source CSV/XLSX files, run this script
to refresh every downstream artifact and the dashboard:

    python scripts/update_all.py

It runs all 10 engines in dependency order:

    1. data_validator.py       →  clean_master.parquet
    2. primitives_engine.py    →  primitives.parquet
    3. window_pattern_engine.py → window_stats.csv, transition_matrices/*.csv
    4. triplet_miner.py        →  triplets_catalog.json
    5. conformity_engine.py    →  conformity_stats.csv, concept_citations.md
    6. anomaly_engine.py       →  anomalies.csv
    7. day_type_engine.py      →  day_types.csv
    8. cross_factor_engine.py  →  cross_factor_stats.csv
    9. synthesis_engine.py     →  playbook.json, dashboard.html inputs
   10. dashboard_engine.py     →  dashboard.html

USAGE
-----
  python scripts/update_all.py                # full refresh
  python scripts/update_all.py --only 3       # run only step 3 (Window Pattern Engine)
  python scripts/update_all.py --skip 2       # skip the first 2 steps
  python scripts/update_all.py --from 5       # start from step 5 onwards
  python scripts/update_all.py --list         # show step list and exit
  python scripts/update_all.py --quiet        # suppress per-step detail
  python scripts/update_all.py --no-dashboard # skip dashboard rebuild at end

WHAT THIS DOES NOT DO (so you know the gaps)
-------------------------------------------
- Does NOT pull live/intraday data — only re-processes the 13 files already in
  the project root.
- Does NOT fetch web news — phase boundaries and OPEC calendar remain static.
  To update those, edit artifacts/phase_lookup.csv and artifacts/opec_calendar.csv
  directly.
- Does NOT validate that the source files are well-formed — that is the job of
  each engine (which will fail loudly if a file is broken).

WHEN TO RUN
-----------
- After appending new days to the 13 source CSVs.
- After fixing a typo in the source data.
- After changing the phase boundaries (in artifacts/phase_lookup.csv).
- After updating the OPEC+ calendar.
- Weekly during the war, so Phase 3 and Phase 4 sample sizes grow.

ARTIFACTS WRITTEN
-----------------
See the inline checklist below — the script prints a summary table at the end.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE / "scripts"
ARTIFACTS = BASE / "artifacts"
DASHBOARD = BASE / "dashboard.html"

# Each step: (display name, filename, [list of artifact paths produced])
STEPS = [
    (
        "Step 1: Data Validator",
        "data_validator.py",
        [
            "clean_master.parquet",
            "phase_lookup.csv",
            "pruning_log.md",
            "data_validator_summary.csv",
            "data_validator_phase_summary.csv",
        ],
    ),
    (
        "Step 2: Primitives Engine",
        "primitives_engine.py",
        [
            "primitives.parquet",
            "primitives_summary.csv",
            "definitions.md",
        ],
    ),
    (
        "Step 3-4: Window Pattern Engine",
        "window_pattern_engine.py",
        [
            "window_stats.csv",
            "daily_high_low_window.csv",
            "daily_high_low_counts_by_phase.csv",
            "magnitude_crosstabs.csv",
            "magnitude_x_eia.csv",
            # transition_matrices/*.csv is generated dynamically
        ],
    ),
    (
        "Step 5: Triplet Miner",
        "triplet_miner.py",
        [
            "triplets_catalog.json",
            "triplets_catalog.csv",
        ],
    ),
    (
        "Step 6: Conformity Engine",
        "conformity_engine.py",
        [
            "conformity_stats.csv",
            "volatility_clustering.csv",
            "daily_momentum.csv",
            "session_liquidity_proxy.csv",
            "concept_citations.md",
        ],
    ),
    (
        "Step 7: Anomaly Engine",
        "anomaly_engine.py",
        [
            "anomalies.csv",
            "anomaly_summary.csv",
        ],
    ),
    (
        "Step 8: Day Type Engine",
        "day_type_engine.py",
        [
            "day_types.csv",
            "day_type_phase_crosstab.csv",
            "day_type_phase_share.csv",
            "kmeans_archetype_crosstab.csv",
        ],
    ),
    (
        "Step 9: Cross Factor Engine",
        "cross_factor_engine.py",
        [
            "cross_factor_stats.csv",
            "opec_calendar.csv",
        ],
    ),
    (
        "Step 11: Synthesis Engine",
        "synthesis_engine.py",
        [
            "playbook.json",
            "playbook_summary.csv",
            "playbook_strong_patterns.csv",
            "chart_data.json",
            "final_playbook.md",
            "coverage_limitations.md",
        ],
    ),
    (
        "Dashboard Engine",
        "dashboard_engine.py",
        [
            "../dashboard.html",  # outside artifacts/
        ],
    ),
]


# =============================================================
# CLI
# =============================================================
def parse_args():
    p = argparse.ArgumentParser(
        description="Re-run the entire Crude Analysis pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--only", type=int, help="Run only step N (1-based).")
    p.add_argument("--skip", type=int, default=0, help="Skip the first N steps.")
    p.add_argument("--from", type=int, dest="from_step", help="Start from step N (1-based).")
    p.add_argument("--list", action="store_true", help="Show step list and exit.")
    p.add_argument("--quiet", action="store_true", help="Suppress per-step detail.")
    p.add_argument("--no-dashboard", action="store_true", help="Skip dashboard rebuild.")
    p.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter to use (default: same as this script's).",
    )
    return p.parse_args()


def list_steps():
    print("\nPipeline steps:\n")
    for i, (name, fname, _) in enumerate(STEPS, 1):
        print(f"  [{i}] {name:<35} -> {fname}")
    print()


# =============================================================
# Source-data verification (run once at the top)
# =============================================================
def verify_sources():
    required_files = [
        "wti_daily_ist.csv", "brent_daily_ist.csv",
        "wti_5m_ist.csv", "brent_5m_ist.csv",
        "wti_15m_ist.csv", "brent_15m_ist.csv",
        "wti_60m_ist.csv", "brent_60m_ist.csv",
        "wti_session_windows_summary.csv", "brent_session_windows_summary.csv",
        "daily_master_summary.csv",
        "wti_spot_daily_reference_ist.csv", "brent_spot_daily_reference_ist.csv",
    ]
    print("\n>>> Verifying source files in project root...")
    missing = []
    for f in required_files:
        p = BASE / f
        if not p.exists():
            missing.append(f)
        else:
            size = p.stat().st_size
            print(f"    {f:<48} {size:>10,} bytes")
    if missing:
        print(f"\n!! {len(missing)} source file(s) missing: {missing}")
        print("    These engines will fail. Restore the files first.")
        return False
    return True


# =============================================================
# Run step
# =============================================================
def run_step(idx_one_based, step, python, quiet=False) -> bool:
    name, fname, _ = step
    script_path = SCRIPTS_DIR / fname
    if not script_path.exists():
        print(f"!! Step {idx_one_based} script missing: {script_path}")
        return False
    print(f"\n{'=' * 70}")
    print(f">>> [{idx_one_based}/{len(STEPS)}] {name}")
    print(f"    -> {script_path.name}")
    print("=" * 70)
    t0 = time.time()
    try:
        result = subprocess.run(
            [python, str(script_path)],
            cwd=str(BASE),
            capture_output=quiet,
            text=True,
        )
    except Exception as e:
        print(f"!! Step {idx_one_based} crashed: {e}")
        return False
    dt = time.time() - t0
    if result.returncode != 0:
        print(f"!! Step {idx_one_based} ({fname}) FAILED with exit code {result.returncode}")
        if quiet and result.stderr:
            print(result.stderr[-2000:])
        return False
    print(f"    ok ({dt:.1f}s)")
    return True


# =============================================================
# Artifact summary at the end
# =============================================================
def report_artifacts():
    print("\n" + "=" * 70)
    print("ARTIFACTS INVENTORY")
    print("=" * 70)
    artifacts = sorted(ARTIFACTS.iterdir())
    for f in artifacts:
        if f.is_file():
            print(f"  {f.name:<50} {f.stat().st_size:>12,} bytes")
        elif f.is_dir():
            sub_count = sum(1 for _ in f.iterdir())
            print(f"  {f.name + '/':<50} {sub_count:>12} files")
    if DASHBOARD.exists():
        print(f"  {'../dashboard.html':<50} {DASHBOARD.stat().st_size:>12,} bytes")
    print()


# =============================================================
# Main
# =============================================================
def main():
    args = parse_args()

    if args.list:
        list_steps()
        return 0

    if not verify_sources():
        return 1

    # Determine which steps to run
    start = (args.from_step or 1) - 1
    if args.skip:
        start = max(start, args.skip)
    end = len(STEPS)

    if args.only:
        # 1-based -> 0-based
        chosen = args.only - 1
        if chosen < 0 or chosen >= len(STEPS):
            print(f"!! --only {args.only} out of range (1..{len(STEPS)})")
            return 2
        steps_to_run = [(chosen + 1, STEPS[chosen])]
    else:
        steps_to_run = [(i + 1, step) for i, step in enumerate(STEPS) if i >= start and (args.no_dashboard or i < len(STEPS) - 1 or start != (args.from_step or 1) - 1)][:end]

        # If user wants full run, run all
        if not args.only and start == 0 and not args.no_dashboard:
            steps_to_run = [(i + 1, step) for i, step in enumerate(STEPS)]
        elif not args.only and start == 0 and args.no_dashboard:
            steps_to_run = [(i + 1, step) for i, step in enumerate(STEPS[:-1])]
        else:
            # Partial run
            chosen_set = list(range(start, end - 1 if args.no_dashboard else end))
            steps_to_run = [(i + 1, STEPS[i]) for i in chosen_set if 0 <= i < len(STEPS)]

    print(f"\n{'#' * 70}")
    print(f"CRUDE OIL WAR-REGIME PIPELINE — auto-update")
    print(f"Python: {args.python}")
    print(f"Steps to run: {[s[0] for s in steps_to_run]}")
    print(f"{'#' * 70}")

    t_start = time.time()
    failed = []
    for idx, step in steps_to_run:
        ok = run_step(idx, step, args.python, quiet=args.quiet)
        if not ok:
            failed.append(idx)
            print(f"\n!! Pipeline aborted at step {idx}. Earlier steps succeeded; downstream NOT updated.")
            break
    dt_total = time.time() - t_start

    print(f"\n{'=' * 70}")
    if not failed:
        print(f"✓ PIPELINE COMPLETE in {dt_total:.1f}s")
        print(f"  - {len(steps_to_run)} step(s) succeeded")
        print(f"  - All artifacts below are now up to date.")
    else:
        print(f"!! PIPELINE FAILED at step {failed[0]} after {dt_total:.1f}s")
    print("=" * 70)

    report_artifacts()

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
