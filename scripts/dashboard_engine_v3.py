"""dashboard_engine_v3.py — Trader-focused Dashboard v3.

Complete redesign for actionable trading decisions:
- Signal cards with entry/stop/target
- Regime classifier output
- Backtest validation per signal
- Risk metrics per trade
- Interactive phase/archetype/window filters
- Equity curve with drawdown
- Monte Carlo confidence bands

Output: dashboard_v3.html (single self-contained HTML)
"""

from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"


def load_all():
    """Load all compact artifacts."""
    data = {}
    files = {
        "playbook": "playbook_summary.csv",
        "strong_patterns": "playbook_strong_patterns.csv",
        "backtest_trades": "backtest_trades.parquet",
        "backtest_by_signal": "backtest_by_signal.csv",
        "backtest_by_phase": "backtest_by_phase.csv",
        "backtest_by_archetype": "backtest_by_archetype.csv",
        "backtest_results": "backtest_results.json",
        "window_stats": "window_stats.csv",
        "window_stats_fdr": "window_stats_fdr.csv",
        "triplets": "triplets_catalog.csv",
        "triplets_fdr": "triplet_fdr.csv",
        "bayesian_posteriors": "bayesian_posteriors.csv",
        "playbook_shrunk": "playbook_shrunk.csv",
        "anomalies": "anomalies.csv",
        "day_types": "day_types.csv",
        "day_type_share": "day_type_phase_share.csv",
        "cross_factor": "cross_factor_stats.csv",
        "brent_cond_dxy": "brent_cond_dxy.csv",
        "brent_cond_spx": "brent_cond_spx.csv",
        "brent_cond_vix": "brent_cond_vix.csv",
        "macro_state_summary": "macro_state_summary.csv",
        "anomalies": "anomalies.csv",
        "conformity": "conformity_stats.csv",
        "vol_clustering": "volatility_clustering.csv",
        "phase_lookup": "phase_lookup.csv",
        "regime_features": "regime_features.csv",
        "regime_importance": "regime_feature_importance.csv",
        "regime_diagnostics": "regime_diagnostics.json",
    }

    for key, fname in files.items():
        path = ARTIFACTS / fname
        if path.exists():
            if path.suffix == ".parquet":
                data[key] = pd.read_parquet(path)
            elif path.suffix == ".json":
                with open(path) as f:
                    data[key] = json.load(f)
            else:
                data[key] = pd.read_csv(path)
        else:
            data[key] = pd.DataFrame()

    # Load dashboard v2 chart data
    chart_data_path = ARTIFACTS / "chart_data.json"
    if chart_data_path.exists():
        with open(chart_data_path) as f:
            data["chart_data"] = json.load(f)
    else:
        data["chart_data"] = {}

    return data


def df_to_js(df: pd.DataFrame, max_rows: int = 200) -> str:
    """Convert dataframe to JavaScript array of objects."""
    if df is None or df.empty:
        return "[]"
    df = df.head(max_rows)
    records = []
    for _, row in df.iterrows():
        rec = {}
        for col, val in row.items():
            if pd.isna(val):
                rec[col] = None
            elif isinstance(val, (np.integer,)):
                rec[col] = int(val)
            elif isinstance(val, (np.floating,)):
                rec[col] = float(val)
            elif isinstance(val, (np.bool_,)):
                rec[col] = bool(val)
            else:
                rec[col] = str(val)
        records.append(rec)
    return json.dumps(records, default=str)


def load_template() -> str:
    """Load the fixed HTML template."""
    template_path = BASE / "scripts" / "dashboard_template_fixed.html"
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def prepare_template_data(data: dict) -> dict:
    """Extract and prepare all data needed for the template."""
    import json

    def safe_json(obj):
        """Convert obj to JSON-serializable format."""
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj) if isinstance(obj, float) else int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient='records')
        if isinstance(obj, pd.Series):
            return obj.to_dict()
        if isinstance(obj, dict):
            return {k: safe_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [safe_json(v) for v in obj]
        return str(obj)

    # Load all required artifacts
    playbook = safe_json(data.get('playbook', pd.DataFrame()).to_dict(orient='records'))
    strong_patterns = safe_json(data.get('strong_patterns', pd.DataFrame()).to_dict(orient='records'))
    bt_signals = safe_json(data.get('backtest_by_signal', pd.DataFrame()).to_dict(orient='records'))
    bt_phase = safe_json(data.get('backtest_by_phase', pd.DataFrame()).to_dict(orient='records'))
    bt_arch = safe_json(data.get('backtest_by_archetype', pd.DataFrame()).to_dict(orient='records'))
    bt_results = safe_json(data.get('backtest_results', {}))
    ws = safe_json(data.get('window_stats_fdr', pd.DataFrame()).to_dict(orient='records'))
    triplets = safe_json(data.get('triplets', pd.DataFrame()).to_dict(orient='records'))
    bayes = safe_json(data.get('bayesian_posteriors', pd.DataFrame()).to_dict(orient='records'))
    shrunk = safe_json(data.get('playbook_shrunk', pd.DataFrame()).to_dict(orient='records'))
    anomalies = safe_json(data.get('anomalies', pd.DataFrame()).to_dict(orient='records'))
    day_types = safe_json(data.get('day_type_share', pd.DataFrame()).to_dict(orient='records'))
    cross_factor = safe_json(data.get('cross_factor', pd.DataFrame()).to_dict(orient='records'))
    bt_results = data.get('backtest_results', {})
    regime_diag = data.get('regime_diagnostics', {})
    phase = safe_json(data.get('phase_lookup', pd.DataFrame()).to_dict(orient='records'))
    bt_trades = safe_json(data.get('backtest_trades', pd.DataFrame()).to_dict(orient='records'))
    chart_data = safe_json(data.get('chart_data', {}))

    return {
        'js_strong_patterns': json.dumps(strong_patterns),
        'js_bt_signals': json.dumps(bt_signals),
        'js_bt_phase': json.dumps(bt_phase),
        'js_bt_arch': json.dumps(bt_arch),
        'js_anomalies': json.dumps(anomalies),
        'js_day_share': json.dumps(day_types),
        'js_cross_factor': json.dumps(cross_factor),
        'js_phase': json.dumps(phase),
        'js_anomalies': json.dumps(anomalies),
        'js_ws': json.dumps(ws),
        'js_bayes': json.dumps(bayes),
        'regime_json': json.dumps(regime_diag),
        'bt_summary': json.dumps(bt_results.get('overall', {})),
        'mc_ci': json.dumps(data.get('backtest_results', {}).get('monte_carlo_ci', {})),
        'bt_trades': json.dumps(bt_trades),
        'chart_data': json.dumps(chart_data),
        'nSignals': len(strong_patterns),
        'nTrades': len(bt_trades),
        # Additional variables used in template
        'h': '',
        'v': '',
    }


def main():
    print(">>> dashboard_engine_v3.py starting", flush=True)
    data = load_all()
    print(f">>> Loaded {len(data)} artifacts", flush=True)

    # Load the fixed HTML template
    with open(BASE / "scripts" / "dashboard_template_fixed.html") as f:
        template = f.read()

    # Prepare template data
    template_data = prepare_template_data(data)

    # Render
    html = template.format(**template_data)

    # Replace placeholder with actual JS code
    html = html.replace("CTX_PARSED_V", "ctx.parsed.v")

    out = BASE / "dashboard_v3.html"
    out.write_text(html, encoding="utf-8")
    print(f">>> wrote {BASE / 'dashboard_v3.html'} ({len(html):,} chars)", flush=True)


if __name__ == "__main__":
    main()