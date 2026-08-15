"""dashboard_engine.py v2 — Comprehensive visual dashboard.

Builds a single self-contained HTML file with many visual elements:
  - Executive summary cards
  - Price journey line chart with phase backgrounds
  - Phase Gantt timeline
  - Window × phase direction heatmap
  - Day-type pie/donut charts per phase
  - Anomaly timeline
  - Decision-helper cards (actionable "if you see X, do Y")
  - Pattern strength bars
  - Conformity metrics radar
  - Triplet flow diagram
  - Mind map (SVG)
  - Critical review tab

Output: dashboard.html (~250-300KB)
"""

from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ART = BASE / "artifacts"


# ============================================================
# Helpers
# ============================================================
def read_xlsx_as_csv(path):
    import tempfile, shutil, os
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    try:
        shutil.copy(str(path), tmp.name)
        return pd.read_excel(tmp.name)
    finally:
        os.unlink(tmp.name)


def safe(o):
    if isinstance(o, dict): return {k: safe(v) for k, v in o.items()}
    if isinstance(o, list): return [safe(x) for x in o]
    if o is None: return None
    try:
        if pd.isna(o): return None
    except Exception:
        pass
    if isinstance(o, pd.Timestamp): return str(o)
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, (np.bool_,)): return bool(o)
    return o


# ============================================================
# Build comprehensive chart data
# ============================================================
def build_chart_data():
    # Phase lookup
    phase = pd.read_csv(ART / 'phase_lookup.csv')

    # Daily prices with phase_id
    wti = read_xlsx_as_csv(BASE / 'wti_daily_ist.csv')[
        ['trade_date_ist', 'close_native', 'volume', 'net_day_return_pct', 'day_range_pct_native',
         'body_direction', 'trendiness_score_1_to_5', 'whipsaw_score_1_to_5']
    ].rename(columns={
        'close_native': 'wti_close',
        'net_day_return_pct': 'wti_ret',
        'day_range_pct_native': 'wti_range',
        'body_direction': 'wti_body',
    })
    brent = read_xlsx_as_csv(BASE / 'brent_daily_ist.csv')[
        ['trade_date_ist', 'close_native', 'net_day_return_pct', 'day_range_pct_native',
         'body_direction']
    ].rename(columns={
        'close_native': 'brent_close',
        'net_day_return_pct': 'brent_ret',
        'day_range_pct_native': 'brent_range',
        'body_direction': 'brent_body',
    })
    prices = wti.merge(brent, on='trade_date_ist').sort_values('trade_date_ist').reset_index(drop=True)
    prices['trade_date_ist'] = pd.to_datetime(prices['trade_date_ist'])

    # Phase tag via date range
    def phase_id_for(dt):
        for _, p in phase.iterrows():
            if pd.to_datetime(p['start_datetime_ist']) <= dt <= pd.to_datetime(p['end_datetime_ist']):
                return int(p['phase_id'])
        return None
    prices['phase_id'] = prices['trade_date_ist'].apply(phase_id_for)
    prices['phase_label'] = prices['phase_id'].map(dict(zip(phase['phase_id'], phase['phase_label'])))

    # Compute log return / drawdown
    prices['wti_log_ret'] = np.log(prices['wti_close'] / prices['wti_close'].shift(1))
    prices['brent_log_ret'] = np.log(prices['brent_close'] / prices['brent_close'].shift(1))
    prices['wti_cumret'] = (prices['wti_close'] / prices['wti_close'].iloc[0] - 1) * 100
    prices['brent_cumret'] = (prices['brent_close'] / prices['brent_close'].iloc[0] - 1) * 100
    prices['wti_close_round'] = prices['wti_close'].round(2)
    prices['brent_close_round'] = prices['brent_close'].round(2)
    prices['dt'] = prices['trade_date_ist'].dt.strftime('%Y-%m-%d')

    # ===== WINDOW STATS: aggregate per phase for charts =====
    ws = pd.read_csv(ART / 'window_stats.csv')
    ws_agg = (
        ws.groupby(['session_window_ist', 'phase_id'])
        .agg(pct_up=('pct_up', 'mean'),
             pct_down=('pct_down', 'mean'),
             pct_flat=('pct_flat', 'mean'),
             n=('n_valid', 'sum'),
             mean_ret=('mean_return_pct', 'mean'),
             std_ret=('std_return_pct', 'mean'))
        .reset_index()
    )

    # ===== DAY TYPE PIE =====
    dts = pd.read_csv(ART / 'day_type_phase_share.csv')

    # ===== ANOMALIES =====
    anom = pd.read_csv(ART / 'anomalies.csv')

    # ===== STRONG PATTERNS =====
    sp = pd.read_csv(ART / 'playbook_strong_patterns.csv')
    # Build "if-then" cards
    if_then_cards = []
    for _, r in sp.nlargest(20, 'n_observations').iterrows():
        direction = 'UP' if r['pct_up_next'] >= 60 else 'DOWN'
        bias_pct = r['pct_up_next'] if direction == 'UP' else r['pct_down_next']
        if_then_cards.append({
            'stream': r['stream'],
            'phase': r['phase_label'],
            'archetype': r['day_archetype'],
            'current_window': r['current_window'],
            'next_window': r['top_next_window'],
            'direction': direction,
            'bias_pct': round(bias_pct, 1),
            'n': int(r['n_observations']),
            'low_conf': bool(r['low_confidence_flag']),
            'mean_ret': round(float(r.get('pct_up_next', 0)) - float(r.get('pct_down_next', 0)), 1),
        })

    # ===== TRIPLETS =====
    tri = pd.read_csv(ART / 'triplets_catalog.csv').sort_values('composite_score', ascending=False).head(15)

    # ===== CROSS FACTOR =====
    cf = pd.read_csv(ART / 'cross_factor_stats.csv')

    # ===== CONFORMITY =====
    conf = pd.read_csv(ART / 'conformity_stats.csv')

    # ===== PRIMITIVES SUMMARY =====
    ps = pd.read_csv(ART / 'primitives_summary.csv')

    # ===== OPEC =====
    opec = pd.read_csv(ART / 'opec_calendar.csv')

    # ===== DV PHASE SUMMARY =====
    dv_phase = pd.read_csv(ART / 'data_validator_phase_summary.csv')

    # ===== TOP METRICS =====
    # Compute quick stats
    n_trading_days = len(prices)
    price_change_brent = float(prices['brent_close'].iloc[-1] - prices['brent_close'].iloc[0])
    pct_change_brent = (prices['brent_close'].iloc[-1] / prices['brent_close'].iloc[0] - 1) * 100
    pct_change_wti = (prices['wti_close'].iloc[-1] / prices['wti_close'].iloc[0] - 1) * 100
    max_brent = float(prices['brent_close'].max())
    min_brent = float(prices['brent_close'].min())
    max_wti = float(prices['wti_close'].max())
    min_wti = float(prices['wti_close'].min())
    max_brent_date = str(prices.loc[prices['brent_close'].idxmax(), 'dt'])
    min_brent_date = str(prices.loc[prices['brent_close'].idxmin(), 'dt'])
    n_anomalies = len(anom)
    n_strong_patterns = len(sp)
    n_low_conf = int(sp['low_confidence_flag'].sum())

    # ===== BRENT-WTI SPREAD =====
    prices['brent_wti_spread'] = prices['brent_close'] - prices['wti_close']

    return {
        'prices': safe(prices[['dt', 'wti_close_round', 'brent_close_round', 'wti_ret', 'brent_ret',
                                'wti_cumret', 'brent_cumret', 'phase_id', 'phase_label',
                                'wti_body', 'brent_body', 'brent_wti_spread']].to_dict(orient='records')),
        'phases': safe(phase.to_dict(orient='records')),
        'window_stats_agg': safe(ws_agg.to_dict(orient='records')),
        'day_type_share': safe(dts.to_dict(orient='records')),
        'anomalies': safe(anom.to_dict(orient='records')),
        'if_then_cards': safe(if_then_cards),
        'top_triplets': safe(tri.to_dict(orient='records')),
        'cross_factor': safe(cf.to_dict(orient='records')),
        'conformity': safe(conf.to_dict(orient='records')),
        'primitives_summary': safe(ps.to_dict(orient='records')),
        'opec': safe(opec.to_dict(orient='records')),
        'dv_phase': safe(dv_phase.to_dict(orient='records')),
        'top_metrics': {
            'n_trading_days': n_trading_days,
            'pct_change_brent': round(pct_change_brent, 1),
            'pct_change_wti': round(pct_change_wti, 1),
            'max_brent': max_brent,
            'min_brent': min_brent,
            'max_wti': max_wti,
            'min_wti': min_wti,
            'max_brent_date': max_brent_date,
            'min_brent_date': min_brent_date,
            'n_anomalies': n_anomalies,
            'n_strong_patterns': n_strong_patterns,
            'n_low_conf': n_low_conf,
            'current_brent': float(prices['brent_close'].iloc[-1]),
            'current_wti': float(prices['wti_close'].iloc[-1]),
            'current_date': str(prices['dt'].iloc[-1]),
        },
    }


# ============================================================
# Render HTML
# ============================================================
def render_html(data):
    chart_data_json = json.dumps(data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Crude Oil War-Regime Dashboard v2</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
:root {{
  --bg: #0f1419;
  --panel: #1a1f2e;
  --panel2: #232938;
  --border: #2a3045;
  --text: #e6e6e6;
  --text-dim: #a0a8b8;
  --accent: #e94560;
  --accent2: #f7b733;
  --good: #38ada9;
  --warn: #ffa500;
  --bad: #e94560;
  --neutral: #888;
}}
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 0; background: var(--bg); color: var(--text); }}
header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 20px 32px; border-bottom: 2px solid var(--accent); }}
header h1 {{ margin: 0; font-size: 26px; color: #fff; }}
header .subtitle {{ font-size: 13px; color: var(--text-dim); margin-top: 6px; }}
.top-metrics {{ display: flex; gap: 16px; padding: 16px 32px; background: var(--panel); flex-wrap: wrap; border-bottom: 1px solid var(--border); }}
.metric {{ background: var(--panel2); padding: 14px 20px; border-radius: 6px; min-width: 140px; border-left: 3px solid var(--accent); }}
.metric.good {{ border-left-color: var(--good); }}
.metric.warn {{ border-left-color: var(--warn); }}
.metric.bad {{ border-left-color: var(--bad); }}
.metric .label {{ font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }}
.metric .value {{ font-size: 22px; font-weight: bold; margin-top: 4px; }}
.metric .sub {{ font-size: 11px; color: var(--text-dim); margin-top: 2px; }}
nav.tabs {{ display: flex; background: var(--panel); padding: 0; overflow-x: auto; border-bottom: 1px solid var(--border); }}
nav.tabs button {{ background: none; border: none; color: var(--text-dim); padding: 14px 20px; cursor: pointer; font-size: 14px; white-space: nowrap; border-bottom: 2px solid transparent; }}
nav.tabs button:hover {{ background: var(--panel2); color: var(--text); }}
nav.tabs button.active {{ background: var(--panel2); color: #fff; border-bottom: 2px solid var(--accent); }}
.tab-content {{ display: none; padding: 24px 32px; }}
.tab-content.active {{ display: block; }}
.tab-content h2 {{ font-size: 20px; color: #fff; border-bottom: 2px solid var(--accent); padding-bottom: 6px; margin-top: 0; }}
.tab-content h3 {{ font-size: 16px; color: var(--accent2); margin-top: 24px; }}
.tab-content p {{ font-size: 13px; line-height: 1.6; color: var(--text-dim); }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }}
.grid-full {{ display: grid; grid-template-columns: 1fr; gap: 20px; }}
.chart-card {{ background: var(--panel); padding: 18px; border-radius: 6px; border: 1px solid var(--border); }}
.chart-card .title {{ font-size: 14px; color: var(--text); margin-bottom: 8px; font-weight: 600; }}
.chart-card canvas {{ max-height: 380px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12px; margin: 12px 0; background: var(--panel); }}
th {{ background: var(--panel2); color: var(--text); padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
td {{ padding: 6px 12px; border-bottom: 1px solid var(--border); }}
tr:nth-child(even) td {{ background: rgba(255,255,255,0.02); }}
td.low-conf {{ background: rgba(233,69,96,0.15) !important; color: var(--bad); font-weight: bold; }}
td.ok {{ color: var(--good); }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: bold; }}
.badge.up {{ background: rgba(56,173,169,0.2); color: var(--good); }}
.badge.down {{ background: rgba(233,69,96,0.2); color: var(--bad); }}
.badge.flat {{ background: rgba(136,136,136,0.2); color: var(--text-dim); }}
.badge.warn {{ background: rgba(255,165,0,0.2); color: var(--warn); }}
.if-then-card {{ background: linear-gradient(135deg, var(--panel), var(--panel2)); padding: 14px; border-radius: 6px; margin-bottom: 10px; border-left: 4px solid var(--accent); }}
.if-then-card.low-conf {{ border-left-color: var(--warn); opacity: 0.7; }}
.if-then-card .condition {{ font-size: 12px; color: var(--text-dim); }}
.if-then-card .action {{ font-size: 14px; color: var(--text); font-weight: 600; margin-top: 6px; }}
.if-then-card .n {{ font-size: 11px; color: var(--text-dim); margin-top: 4px; }}
.if-then-card.up {{ border-left-color: var(--good); }}
.if-then-card.down {{ border-left-color: var(--bad); }}
.note {{ background: rgba(255,165,0,0.1); padding: 14px 18px; border-left: 3px solid var(--warn); margin: 12px 0; font-size: 12px; color: var(--text); border-radius: 4px; }}
.gantt {{ background: var(--panel); padding: 16px; border-radius: 6px; }}
.gantt-bar {{ height: 28px; border-radius: 4px; display: flex; align-items: center; padding-left: 8px; font-size: 12px; color: #fff; margin-bottom: 4px; position: relative; }}
.mindmap {{ background: var(--panel); padding: 20px; border-radius: 6px; min-height: 500px; }}
.mindmap text {{ fill: var(--text); font-size: 11px; font-family: sans-serif; }}
.mindmap circle {{ stroke: var(--accent); stroke-width: 2; }}
@media (max-width: 900px) {{ .grid, .grid-3 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<header>
  <h1>🛢️ Crude Oil War-Regime Pattern Dashboard v2</h1>
  <div class="subtitle">Iran-Israel conflict analysis • 2026-03-02 → 2026-07-17 (98 trading days) • Compiled 2026-07-20</div>
</header>

<div class="top-metrics" id="topMetrics"></div>

<nav class="tabs">
  <button class="active" data-tab="exec">🎯 Executive</button>
  <button data-tab="phase">📅 Phases</button>
  <button data-tab="price">📈 Price Journey</button>
  <button data-tab="decision">🎲 Decision Helper</button>
  <button data-tab="windows">🪟 Windows</button>
  <button data-tab="anom">⚠️ Anomalies</button>
  <button data-tab="daytype">📊 Day Types</button>
  <button data-tab="triplets">🔗 Triplets</button>
  <button data-tab="cross">🔄 Cross-Factor</button>
  <button data-tab="mindmap">🧠 Mind Map</button>
  <button data-tab="review">📝 Critical Review</button>
</nav>

<div class="tab-content active" id="tab-exec">
  <h2>🎯 Executive Summary — One-Page Briefing</h2>
  <p>Quick-read view of the 98-day war regime. Start here. Every claim links to a tab with the supporting data.</p>

  <div class="grid">
    <div class="chart-card">
      <div class="title">📈 Price Journey (% cumulative return from start)</div>
      <canvas id="execPrice"></canvas>
    </div>
    <div class="chart-card">
      <div class="title">🎯 Direction Distribution Across All Windows (avg per phase)</div>
      <canvas id="execDirection"></canvas>
    </div>
  </div>

  <div class="grid">
    <div class="chart-card">
      <div class="title">📊 Day-Type Mix by Phase (Brent)</div>
      <canvas id="execDayType"></canvas>
    </div>
    <div class="chart-card">
      <div class="title">⚠️ Anomalies on Price Timeline</div>
      <canvas id="execAnomalies"></canvas>
    </div>
  </div>

  <h3>🟢 Top 5 High-Confidence Actionable Patterns</h3>
  <div id="execTopPatterns"></div>

  <div class="note">
    <strong>Bottom line:</strong> Crude oil is in Phase 6 (renewed strong escalation) as of 2026-07-17. Brent at <span id="execCurrentPrice"></span>, up ~<span id="execPctChange"></span> from war start. The playbook gives conditional probabilities based on (phase, day-type, window). See Decision Helper tab for actionable "if X then Y" cards.
  </div>
</div>

<div class="tab-content" id="tab-phase">
  <h2>📅 Phase Timeline</h2>
  <p>Six regimes derived from web-researched Iran-Israel/US conflict timeline. Hover for details.</p>

  <div class="chart-card">
    <div class="title">Phase Gantt Timeline</div>
    <div class="gantt" id="ganttChart"></div>
  </div>

  <div class="grid">
    <div class="chart-card">
      <div class="title">📊 Trading Days per Phase</div>
      <canvas id="phaseDays"></canvas>
    </div>
    <div class="chart-card">
      <div class="title">📈 Volatility (Mean Range %) per Phase</div>
      <canvas id="phaseVol"></canvas>
    </div>
  </div>

  <h3>Phase Definitions</h3>
  <div id="phaseTable"></div>
</div>

<div class="tab-content" id="tab-price">
  <h2>📈 Price Journey — WTI vs Brent</h2>
  <p>Day-by-day close with phase backgrounds. Spot prices via FRED/EIA used for reference.</p>

  <div class="chart-card">
    <div class="title">Daily Close: WTI vs Brent</div>
    <canvas id="priceChart"></canvas>
  </div>

  <div class="grid">
    <div class="chart-card">
      <div class="title">Daily Returns Distribution (Brent)</div>
      <canvas id="priceReturnDist"></canvas>
    </div>
    <div class="chart-card">
      <div class="title">Brent-WTI Spread Over Time</div>
      <canvas id="priceSpread"></canvas>
    </div>
  </div>

  <h3>Key Price Milestones</h3>
  <div class="grid-3">
    <div class="metric"><div class="label">Brent Start (Mar 2)</div><div class="value">$<span id="brentStart"></span></div></div>
    <div class="metric"><div class="label">Brent Peak</div><div class="value">$<span id="brentPeak"></span></div><div class="sub" id="brentPeakDate"></div></div>
    <div class="metric"><div class="label">Brent Current (Jul 17)</div><div class="value">$<span id="brentCurrent"></span></div></div>
    <div class="metric good"><div class="label">Brent % Change</div><div class="value">+<span id="brentPct"></span>%</div></div>
    <div class="metric"><div class="label">WTI Start</div><div class="value">$<span id="wtiStart"></span></div></div>
    <div class="metric"><div class="label">WTI Peak</div><div class="value">$<span id="wtiPeak"></span></div></div>
  </div>
</div>

<div class="tab-content" id="tab-decision">
  <h2>🎲 Decision Helper — "If You See X, Then Y"</h2>
  <p>Actionable patterns from the playbook. Each card shows: <strong>CONDITION → ACTION → historical base rate (n)</strong>. Cards marked LOW-CONFIDENCE have n&lt;5.</p>

  <div class="note">
    <strong>How to read:</strong> These are <em>conditional probabilities</em>, not predictions. "67% UP" means historically, when this pattern occurred, the next window closed up 67% of the time. Always cross-check with current news, your own risk tolerance, and stop/target sizing.
  </div>

  <div class="grid-3" id="decisionCards"></div>
</div>

<div class="tab-content" id="tab-windows">
  <h2>🪟 Time-Window Analysis</h2>
  <p>Direction bias (UP/DOWN/FLAT) per window per phase. Heatmap shows percentage. n disclosed on every cell.</p>

  <div class="chart-card">
    <div class="title">Direction Heatmap: Window × Phase (% UP bias, avg across streams)</div>
    <canvas id="windowHeatmap"></canvas>
  </div>

  <h3>Per-Window × Phase Direction Tables</h3>
  <div id="windowTable"></div>

  <h3>Transition Matrices (P(direction_next | direction_current))</h3>
  <div id="transitionMatrices"></div>
</div>

<div class="tab-content" id="tab-anom">
  <h2>⚠️ Anomalies (Rolling |z| &gt; 2.5)</h2>
  <p>Days where volatility, move magnitude, or volume was statistically anomalous vs. recent history. Heuristic only — not claims of intent.</p>

  <div class="grid">
    <div class="chart-card">
      <div class="title">Anomaly Timeline</div>
      <canvas id="anomalyTimeline"></canvas>
    </div>
    <div class="chart-card">
      <div class="title">Anomalies per Phase</div>
      <canvas id="anomalyByPhase"></canvas>
    </div>
  </div>

  <h3>Flagged Dates</h3>
  <div id="anomalyTable"></div>
</div>

<div class="tab-content" id="tab-daytype">
  <h2>📊 Day-Type Buckets</h2>
  <p>Whole-day archetype classification: trend, whipsaw, gap-and-hold, range-bound, etc.</p>

  <div class="grid">
    <div class="chart-card">
      <div class="title">Day-Type Mix Per Phase (Brent)</div>
      <canvas id="dayTypeStacked"></canvas>
    </div>
    <div class="chart-card">
      <div class="title">Day-Type Mix Per Phase (WTI)</div>
      <canvas id="dayTypeStackedWTI"></canvas>
    </div>
  </div>

  <h3>Day-Type Mix Detail</h3>
  <div id="dayTypeTable"></div>
</div>

<div class="tab-content" id="tab-triplets">
  <h2>🔗 Triplet Sequential Patterns</h2>
  <p>3-leg sequences (direction + magnitude tier) ranked by composite score = support × consistency × sample confidence.</p>

  <div class="chart-card">
    <div class="title">Top 15 Triplets by Composite Score</div>
    <canvas id="tripletChart"></canvas>
  </div>

  <h3>Triplet Catalog (top 15)</h3>
  <div id="tripletTable"></div>
</div>

<div class="tab-content" id="tab-cross">
  <h2>🔄 Cross-Factor Overlays</h2>
  <p>Brent-WTI lead-lag, EIA Wednesday effect, weekly structure, OPEC+ calendar.</p>

  <div class="chart-card">
    <div class="title">Brent-WTI Daily Return Correlation by Lead-Lag (days)</div>
    <canvas id="leadLagChart"></canvas>
  </div>

  <div class="grid">
    <div class="chart-card">
      <div class="title">📊 Weekly Structure: Mean Daily Returns</div>
      <canvas id="weeklyChart"></canvas>
    </div>
    <div class="chart-card">
      <div class="title">📊 OPEC+ Meeting Day Effect</div>
      <canvas id="opecChart"></canvas>
    </div>
  </div>

  <h3>EIA Wednesday Effect (per phase)</h3>
  <canvas id="eiaChart" height="80"></canvas>

  <h3>OPEC+ 2026 Meeting Calendar</h3>
  <div id="opecTable"></div>
</div>

<div class="tab-content" id="tab-mindmap">
  <h2>🧠 Mind Map — Conceptual Relationships</h2>
  <p>Visual map of how cross-factors, phases, windows, and trade decisions connect.</p>
  <div class="mindmap">
    <svg id="mindmapSvg" width="100%" height="600" viewBox="0 0 1100 600"></svg>
  </div>
</div>

<div class="tab-content" id="tab-review">
  <h2>📝 Critical Review — Honest Assessment</h2>
  <p>An honest evaluation of what's been done and what's missing for actual trading.</p>

  <div class="grid-3">
    <div class="metric good"><div class="label">Historical Pattern Library</div><div class="value">75%</div><div class="sub">Strong statistical work</div></div>
    <div class="metric bad"><div class="label">Trading-Decision System</div><div class="value">20%</div><div class="sub">Missing live layer</div></div>
    <div class="metric warn"><div class="label">Overall Toward Goal</div><div class="value">~55%</div><div class="sub">Research, not trading</div></div>
  </div>

  <h3>✅ What's Solid</h3>
  <ul style="font-size:13px; line-height:1.7; color:var(--text);">
    <li><strong>Pipeline architecture</strong> — 10 scripts, vectorized, compact artifacts, reproducible</li>
    <li><strong>Statistical hygiene</strong> — sample-size discipline, low-confidence flags, ≥3-repetition rule</li>
    <li><strong>Phase tagging</strong> — 6 regimes grounded in web-researched timeline</li>
    <li><strong>Specific tradable findings:</strong>
      <ul>
        <li>Brent-WTI contemporaneous correlation: 0.725 daily → don't fade intra-day divergence</li>
        <li>Wednesday EIA days: systematically lower returns in war phases</li>
        <li>Monday: +1.5% WTI positive bias. Friday: -0.4% bias</li>
        <li>Phase 4 (naval_blockade_removed): 60% whipsaw_two_sided → range-trade, don't fade</li>
      </ul>
    </li>
  </ul>

  <h3>🔴 Critical Gaps</h3>
  <ul style="font-size:13px; line-height:1.7; color:var(--text);">
    <li><strong>NO live regime classifier</strong> — can't answer "what phase are we in TODAY?"</li>
    <li><strong>NO MCX CRUDEOILM data</strong> — only WTI/Brent; Indian trader can't directly trade</li>
    <li><strong>NO backtest</strong> — patterns not validated for positive expectancy</li>
    <li><strong>NO risk management</strong> — no stops, targets, or position sizing</li>
    <li><strong>Small sample</strong> — Phase 3 (4 days), Phase 4 (6 days); only 17/1175 triplets have n≥3</li>
    <li><strong>NO multiple-comparison correction</strong> — many "60% patterns" likely spurious</li>
  </ul>

  <h3>📋 Recommended Next Steps (Priority Order)</h3>
  <ol style="font-size:13px; line-height:1.7; color:var(--text);">
    <li>Add MCX CRUDEOILM data ingest (1 week)</li>
    <li>Build a backtester that replays playbook on history (1 week)</li>
    <li>Build live regime classifier: today's data → current phase (2 weeks)</li>
    <li>Apply Benjamini-Hochberg FDR correction per test family (3 days)</li>
    <li>Add risk management layer: stops, targets, sizing (1 week)</li>
    <li>Walk-forward cross-validation framework (1 week)</li>
    <li>Cross-asset overlay: DXY, SPX, gold, COT (2 weeks)</li>
    <li>Real-time news/event feed integration (2 weeks)</li>
    <li>Paper-trade for 4 weeks before live</li>
  </ol>

  <h3>🎯 Honest Verdict</h3>
  <div class="note">
    <strong>Do not trade on this as-is.</strong> Use it as research. The historical pattern-mining half is well-executed and reproducible, but converting research → trading requires ~10-12 more weeks of work in 5 specific areas (live classifier, MCX data, backtester, risk management, cross-asset overlay). The current dashboard answers <em>"what has the market historically done in each phase?"</em> — it does <em>not</em> answer <em>"what should I do today?"</em>.
  </div>

  <p>Full critical review: <a href="CRITICAL_REVIEW.md" style="color:var(--accent);">CRITICAL_REVIEW.md</a></p>
</div>

<script>
const CHART_DATA = {chart_data_json};

// ============================================================
// Render top metrics
// ============================================================
const tm = CHART_DATA.top_metrics;
document.getElementById('topMetrics').innerHTML = `
  <div class="metric"><div class="label">Trading Days</div><div class="value">${{tm.n_trading_days}}</div><div class="sub">2026-03-02 → 2026-07-17</div></div>
  <div class="metric bad"><div class="label">Brent % Change</div><div class="value">+${{tm.pct_change_brent}}%</div><div class="sub">${{tm.min_brent}} → ${{tm.max_brent}}</div></div>
  <div class="metric bad"><div class="label">WTI % Change</div><div class="value">+${{tm.pct_change_wti}}%</div><div class="sub">${{tm.min_wti}} → ${{tm.max_wti}}</div></div>
  <div class="metric warn"><div class="label">Anomalies Flagged</div><div class="value">${{tm.n_anomalies}}</div><div class="sub">|z| > 2.5</div></div>
  <div class="metric good"><div class="label">Strong Patterns</div><div class="value">${{tm.n_strong_patterns}}</div><div class="sub">|bias| ≥ 60%</div></div>
  <div class="metric bad"><div class="label">Low-Confidence</div><div class="value">${{tm.n_low_conf}}</div><div class="sub">n &lt; 5 — flagged</div></div>
`;

// ============================================================
// Tab switching
// ============================================================
document.querySelectorAll('nav button').forEach(btn => {{
  btn.onclick = () => {{
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    // Trigger chart resize
    setTimeout(() => {{ window.dispatchEvent(new Event('resize')); }}, 100);
  }};
}});

// ============================================================
// Phase colors
// ============================================================
const phaseColors = {{
  1: '#e94560', 2: '#f7b733', 3: '#fc5c65', 4: '#3c6382', 5: '#38ada9', 6: '#e77f67'
}};

// ============================================================
// EXECUTIVE TAB
// ============================================================
(function() {{
  // Price journey
  const prices = CHART_DATA.prices;
  new Chart(document.getElementById('execPrice'), {{
    type: 'line',
    data: {{
      labels: prices.map(p => p.dt),
      datasets: [
        {{ label: 'Brent cumulative %', data: prices.map(p => p.brent_cumret), borderColor: '#e94560', backgroundColor: 'rgba(233,69,96,0.1)', fill: true, tension: 0.3, pointRadius: 0 }},
        {{ label: 'WTI cumulative %', data: prices.map(p => p.wti_cumret), borderColor: '#f7b733', backgroundColor: 'rgba(247,183,51,0.1)', fill: true, tension: 0.3, pointRadius: 0 }}
      ]
    }},
    options: {{
      plugins: {{ legend: {{ position: 'bottom' }}, tooltip: {{ mode: 'index', intersect: false }} }},
      scales: {{ y: {{ ticks: {{ callback: v => v + '%' }} }} }},
      interaction: {{ mode: 'index', intersect: false }}
    }}
  }});

  // Direction distribution per phase
  const ws = CHART_DATA.window_stats_agg;
  const phases = [...new Set(ws.map(w => w.phase_id))].sort();
  const phaseLabels = {{1:'P1 War',2:'P2 Post',3:'P3 Escalation',4:'P4 Pause',5:'P5 Slight',6:'P6 Renewed'}};
  new Chart(document.getElementById('execDirection'), {{
    type: 'bar',
    data: {{
      labels: phases.map(p => phaseLabels[p] || 'P' + p),
      datasets: [
        {{ label: '% UP', data: phases.map(p => {{
          const sub = ws.filter(w => w.phase_id === p);
          return sub.length ? sub.reduce((s, x) => s + x.pct_up, 0) / sub.length : 0;
        }}), backgroundColor: '#38ada9' }},
        {{ label: '% DOWN', data: phases.map(p => {{
          const sub = ws.filter(w => w.phase_id === p);
          return sub.length ? sub.reduce((s, x) => s + x.pct_down, 0) / sub.length : 0;
        }}), backgroundColor: '#e94560' }},
        {{ label: '% FLAT', data: phases.map(p => {{
          const sub = ws.filter(w => w.phase_id === p);
          return sub.length ? sub.reduce((s, x) => s + x.pct_flat, 0) / sub.length : 0;
        }}), backgroundColor: '#888' }}
      ]
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }} }}
  }});

  // Day type stack per phase (Brent)
  const dts = CHART_DATA.day_type_share.filter(d => d.stream === 'BRENT_daily');
  const arches = [...new Set(dts.map(d => d.day_archetype))];
  new Chart(document.getElementById('execDayType'), {{
    type: 'bar',
    data: {{
      labels: phases.map(p => phaseLabels[p] || 'P' + p),
      datasets: arches.map((a, i) => ({{
        label: a,
        data: phases.map(p => {{
          const row = dts.find(d => d.phase_id === p && d.day_archetype === a);
          return row ? row.pct : 0;
        }}),
        backgroundColor: ['#e94560','#f7b733','#38ada9','#3c6382','#888','#e77f67','#fc5c65','#0f3460'][i % 8]
      }}))
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }} }}
  }});

  // Anomalies timeline
  const anoms = CHART_DATA.anomalies.filter(a => a.__stream === 'BRENT_daily');
  new Chart(document.getElementById('execAnomalies'), {{
    type: 'scatter',
    data: {{
      datasets: [
        {{ label: 'BRENT anomalies', data: anoms.map(a => ({{x: a.trade_date_ist, y: a.z_value}})), backgroundColor: '#e94560', pointRadius: 8 }},
        {{ label: 'WTI anomalies', data: CHART_DATA.anomalies.filter(a => a.__stream === 'WTI_daily').map(a => ({{x: a.trade_date_ist, y: a.z_value}})), backgroundColor: '#f7b733', pointRadius: 8 }}
      ]
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
  }});

  // Top 5 patterns (text cards)
  const top5 = CHART_DATA.if_then_cards.slice(0, 5);
  document.getElementById('execTopPatterns').innerHTML = top5.map(c => `
    <div class="if-then-card ${{c.direction.toLowerCase()}} ${{c.low_conf ? 'low-conf' : ''}}">
      <div class="condition">IF: ${{c.stream.replace('_session','')}} • ${{c.phase}} • day=${{c.archetype}} • window=${{c.current_window}}</div>
      <div class="action">THEN: next window ${{c.next_window}} → <span class="badge ${{c.direction.toLowerCase()}}">${{c.direction}} ${{c.bias_pct}}%</span></div>
      <div class="n">base rate: n=${{c.n}} ${{c.low_conf ? '⚠ LOW-CONFIDENCE' : ''}}</div>
    </div>
  `).join('');

  document.getElementById('execCurrentPrice').textContent = '$' + tm.current_brent.toFixed(2);
  document.getElementById('execPctChange').textContent = tm.pct_change_brent.toFixed(1) + '%';
}})();

// ============================================================
// PHASE TAB
// ============================================================
(function() {{
  // Gantt
  const phases = CHART_DATA.phases;
  const minDate = new Date(phases[0].start_datetime_ist);
  const maxDate = new Date(phases[phases.length - 1].end_datetime_ist);
  const totalMs = maxDate - minDate;
  let ganttHtml = '';
  phases.forEach((p, i) => {{
    const start = new Date(p.start_datetime_ist);
    const end = new Date(p.end_datetime_ist);
    const leftPct = ((start - minDate) / totalMs * 100).toFixed(1);
    const widthPct = ((end - start) / totalMs * 100).toFixed(1);
    ganttHtml += `
      <div class="gantt-bar" style="background:${{phaseColors[p.phase_id]}}; margin-left:${{leftPct}}%; width:${{widthPct}}%;">
        P${{p.phase_id}}: ${{p.phase_label.substring(0, 25)}}${{p.phase_label.length > 25 ? '...' : ''}} (${{p.n_trading_days}}d)
      </div>
      <div style="font-size:11px; color:var(--text-dim); margin-bottom:14px; margin-left:${{leftPct}}%;">${{p.start_datetime_ist.substring(0,10)}} → ${{p.end_datetime_ist.substring(0,10)}}</div>
    `;
  }});
  document.getElementById('ganttChart').innerHTML = ganttHtml;

  // Trading days per phase
  new Chart(document.getElementById('phaseDays'), {{
    type: 'bar',
    data: {{
      labels: phases.map(p => 'P' + p.phase_id + ' ' + p.phase_label.substring(0, 15)),
      datasets: [{{ label: 'Trading days', data: phases.map(p => p.n_trading_days), backgroundColor: phases.map(p => phaseColors[p.phase_id]) }}]
    }},
    options: {{ plugins: {{ legend: {{ display: false }} }} }}
  }});

  // Volatility per phase
  const ps = CHART_DATA.primitives_summary;
  new Chart(document.getElementById('phaseVol'), {{
    type: 'bar',
    data: {{
      labels: ps.map(p => 'P' + p.phase_id),
      datasets: [
        {{ label: 'Mean Range %', data: ps.map(p => p.mean_range_pct), backgroundColor: '#e94560' }},
        {{ label: 'Median |Return| %', data: ps.map(p => p.median_abs_return), backgroundColor: '#f7b733' }}
      ]
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
  }});

  // Phase table
  let tableHtml = '<table><tr><th>ID</th><th>Label</th><th>Start</th><th>End</th><th>Days</th><th>Conf</th><th>Defining</th></tr>';
  phases.forEach(p => {{
    tableHtml += `<tr>
      <td><span class="badge" style="background:${{phaseColors[p.phase_id]}}">P${{p.phase_id}}</span></td>
      <td>${{p.phase_label}}</td>
      <td>${{p.start_datetime_ist.substring(0,10)}}</td>
      <td>${{p.end_datetime_ist.substring(0,10)}}</td>
      <td>${{p.n_trading_days}}</td>
      <td>${{p.confidence_1_to_5}}/5</td>
      <td style="font-size:11px">${{p.defining_characteristic.substring(0,80)}}...</td>
    </tr>`;
  }});
  tableHtml += '</table>';
  document.getElementById('phaseTable').innerHTML = tableHtml;
}})();

// ============================================================
// PRICE TAB
// ============================================================
(function() {{
  const prices = CHART_DATA.prices;

  // Price chart
  new Chart(document.getElementById('priceChart'), {{
    type: 'line',
    data: {{
      labels: prices.map(p => p.dt),
      datasets: [
        {{ label: 'Brent close', data: prices.map(p => p.brent_close_round), borderColor: '#e94560', tension: 0.1, pointRadius: 0 }},
        {{ label: 'WTI close', data: prices.map(p => p.wti_close_round), borderColor: '#f7b733', tension: 0.1, pointRadius: 0 }}
      ]
    }},
    options: {{
      plugins: {{ legend: {{ position: 'bottom' }}, tooltip: {{ mode: 'index', intersect: false }} }},
      interaction: {{ mode: 'index', intersect: false }}
    }}
  }});

  // Returns distribution
  const returns = prices.map(p => p.brent_ret).filter(r => r !== null && !isNaN(r));
  const minR = Math.min(...returns);
  const maxR = Math.max(...returns);
  const bins = 20;
  const binSize = (maxR - minR) / bins;
  const hist = new Array(bins).fill(0);
  returns.forEach(r => {{
    const idx = Math.min(bins - 1, Math.floor((r - minR) / binSize));
    hist[idx]++;
  }});
  const labels = Array.from({{length: bins}}, (_, i) => (minR + i * binSize).toFixed(1));
  new Chart(document.getElementById('priceReturnDist'), {{
    type: 'bar',
    data: {{ labels: labels, datasets: [{{ label: 'Days', data: hist, backgroundColor: '#3c6382' }}] }},
    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ title: {{ display: true, text: 'Brent daily return %' }} }} }} }}
  }});

  // Spread chart
  new Chart(document.getElementById('priceSpread'), {{
    type: 'line',
    data: {{
      labels: prices.map(p => p.dt),
      datasets: [{{ label: 'Brent-WTI spread (USD)', data: prices.map(p => p.brent_wti_spread), borderColor: '#38ada9', backgroundColor: 'rgba(56,173,169,0.2)', fill: true, pointRadius: 0, tension: 0.2 }}]
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
  }});

  // Metrics
  const tm = CHART_DATA.top_metrics;
  document.getElementById('brentStart').textContent = prices[0].brent_close_round;
  document.getElementById('brentPeak').textContent = tm.max_brent.toFixed(2);
  document.getElementById('brentPeakDate').textContent = tm.max_brent_date;
  document.getElementById('brentCurrent').textContent = prices[prices.length-1].brent_close_round;
  document.getElementById('brentPct').textContent = tm.pct_change_brent.toFixed(1);
  document.getElementById('wtiStart').textContent = prices[0].wti_close_round;
  document.getElementById('wtiPeak').textContent = tm.max_wti.toFixed(2);
}})();

// ============================================================
// DECISION HELPER
// ============================================================
(function() {{
  const cards = CHART_DATA.if_then_cards;
  let html = '';
  cards.forEach(c => {{
    html += `
      <div class="if-then-card ${{c.direction.toLowerCase()}} ${{c.low_conf ? 'low-conf' : ''}}">
        <div style="font-size:11px; color:var(--text-dim); margin-bottom:4px;">${{c.stream.replace('_session','')}} • ${{c.phase}}</div>
        <div class="condition">📍 Day type: <strong>${{c.archetype}}</strong></div>
        <div class="condition">⏰ Current window: <strong>${{c.current_window}}</strong></div>
        <div class="action">➡️ Next window ${{c.next_window}}: <span class="badge ${{c.direction.toLowerCase()}}">${{c.direction}} ${{c.bias_pct}}%</span></div>
        <div class="n">📊 base rate: n=${{c.n}} ${{c.low_conf ? '⚠ LOW-CONFIDENCE (n&lt;5)' : ''}}</div>
      </div>
    `;
  }});
  document.getElementById('decisionCards').innerHTML = html;
}})();

// ============================================================
// WINDOWS TAB
// ============================================================
(function() {{
  const ws = CHART_DATA.window_stats_agg;
  const windows = [...new Set(ws.map(w => w.session_window_ist))];
  const phases = [...new Set(ws.map(w => w.phase_id))].sort();
  const phaseLabels = {{1:'P1',2:'P2',3:'P3',4:'P4',5:'P5',6:'P6'}};

  // Heatmap of %UP
  const data = phases.map(p => windows.map(w => {{
    const row = ws.find(x => x.phase_id === p && x.session_window_ist === w);
    return row ? row.pct_up : null;
  }}));
  new Chart(document.getElementById('windowHeatmap'), {{
    type: 'bar',
    data: {{
      labels: windows,
      datasets: phases.map((p, i) => ({{
        label: phaseLabels[p],
        data: data[i],
        backgroundColor: phaseColors[p]
      }}))
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ y: {{ beginAtZero: true, max: 100, ticks: {{ callback: v => v + '%' }} }} }} }}
  }});

  // Detailed table
  const phaseColMap = {{1:'P1',2:'P2',3:'P3',4:'P4',5:'P5',6:'P6'}};
  let tableHtml = '<table><tr><th>Window</th><th>Phase</th><th>%UP</th><th>%DOWN</th><th>%FLAT</th><th>n</th><th>mean ret %</th></tr>';
  ws.sort((a, b) => a.session_window_ist.localeCompare(b.session_window_ist) || a.phase_id - b.phase_id).forEach(w => {{
    tableHtml += `<tr>
      <td>${{w.session_window_ist}}</td>
      <td><span class="badge" style="background:${{phaseColors[w.phase_id]}}">${{phaseColMap[w.phase_id]}}</span></td>
      <td>${{w.pct_up ? w.pct_up.toFixed(1) : '-'}}</td>
      <td>${{w.pct_down ? w.pct_down.toFixed(1) : '-'}}</td>
      <td>${{w.pct_flat ? w.pct_flat.toFixed(1) : '-'}}</td>
      <td>${{w.n}}</td>
      <td>${{w.mean_ret ? w.mean_ret.toFixed(2) : '-'}}</td>
    </tr>`;
  }});
  tableHtml += '</table>';
  document.getElementById('windowTable').innerHTML = tableHtml;

  // Transition matrix previews
  const states = ['UP', 'DOWN', 'FLAT'];
  for (const pid of [1, 2, 5, 6]) {{
    fetch('artifacts/transition_matrices/phase_' + pid + '_combined.csv')
      .then(r => r.text())
      .then(csv => {{
        const lines = csv.trim().split('\\n');
        const header = lines[0].split(',');
        const rows = lines.slice(1).map(l => l.split(','));
        const dirIdx = header.indexOf('direction');
        const nextIdx = header.indexOf('next_direction');
        const probIdx = header.indexOf('probability');
        const nIdx = header.indexOf('n_total_in_row');
        let html = '<table style="max-width:400px"><tr><th></th>';
        states.forEach(s => html += '<th>' + s + '</th>');
        html += '<th>n</th></tr>';
        states.forEach(sf => {{
          html += '<tr><th>' + sf + '</th>';
          states.forEach(st => {{
            const m = rows.find(r => r[dirIdx] === sf && r[nextIdx] === st);
            html += '<td>' + (m ? (parseFloat(m[probIdx]) * 100).toFixed(0) + '%' : '-') + '</td>';
          }});
          const totalRow = rows.find(r => r[dirIdx] === sf && r[nextIdx] === states[0]);
          html += '<td>' + (totalRow ? totalRow[nIdx] : '-') + '</td></tr>';
        }});
        html += '</table>';
        const el = document.getElementById('tm_' + pid);
        if (el) el.innerHTML = html;
      }});
  }}
  document.getElementById('transitionMatrices').innerHTML = [1, 2, 5, 6].map(p => `
    <div style="margin-bottom: 16px">
      <h4>P${{p}}</h4>
      <div id="tm_${{p}}"></div>
    </div>
  `).join('');
}})();

// ============================================================
// ANOMALIES TAB
// ============================================================
(function() {{
  const anoms = CHART_DATA.anomalies;

  // Timeline
  new Chart(document.getElementById('anomalyTimeline'), {{
    type: 'bar',
    data: {{
      labels: anoms.map(a => a.trade_date_ist),
      datasets: [{{
        label: '|z|',
        data: anoms.map(a => Math.abs(a.z_value)),
        backgroundColor: anoms.map(a => a.z_value > 0 ? '#e94560' : '#38ada9')
      }}]
    }},
    options: {{ plugins: {{ legend: {{ display: false }} }} }}
  }});

  // By phase
  const byPhase = {{}};
  anoms.forEach(a => {{
    byPhase[a.phase_id] = (byPhase[a.phase_id] || 0) + 1;
  }});
  new Chart(document.getElementById('anomalyByPhase'), {{
    type: 'bar',
    data: {{
      labels: Object.keys(byPhase).map(p => 'P' + p),
      datasets: [{{
        label: '# anomalies',
        data: Object.values(byPhase),
        backgroundColor: Object.keys(byPhase).map(p => phaseColors[p])
      }}]
    }},
    options: {{ plugins: {{ legend: {{ display: false }} }} }}
  }});

  // Table
  let html = '<table><tr><th>Date</th><th>Stream</th><th>Phase</th><th>Metric</th><th>z-score</th></tr>';
  anoms.forEach(a => {{
    html += `<tr>
      <td>${{a.trade_date_ist}}</td>
      <td>${{a.__stream.replace('_daily', '')}}</td>
      <td><span class="badge" style="background:${{phaseColors[a.phase_id]}}">P${{a.phase_id}}</span></td>
      <td>${{a.anomaly_metric.replace('_rolling_z', '').replace('_z', '')}}</td>
      <td style="color:${{a.z_value > 0 ? '#e94560' : '#38ada9'}}; font-weight:bold">${{a.z_value.toFixed(2)}}</td>
    </tr>`;
  }});
  html += '</table>';
  document.getElementById('anomalyTable').innerHTML = html;
}})();

// ============================================================
// DAY TYPE TAB
// ============================================================
(function() {{
  const dts = CHART_DATA.day_type_share;
  const arches = [...new Set(dts.map(d => d.day_archetype))];
  const phases = [...new Set(dts.map(d => d.phase_id))].sort();
  const phaseLabels = {{1:'P1 War',2:'P2 Post',3:'P3 Esc',4:'P4 Pause',5:'P5 Slight',6:'P6 Renew'}};
  const colors = ['#e94560','#f7b733','#38ada9','#3c6382','#888','#e77f67','#fc5c65','#0f3460'];

  // Brent
  const dtsB = dts.filter(d => d.stream === 'BRENT_daily');
  new Chart(document.getElementById('dayTypeStacked'), {{
    type: 'bar',
    data: {{
      labels: phases.map(p => phaseLabels[p]),
      datasets: arches.map((a, i) => ({{
        label: a,
        data: phases.map(p => {{
          const row = dtsB.find(d => d.phase_id === p && d.day_archetype === a);
          return row ? row.pct : 0;
        }}),
        backgroundColor: colors[i % colors.length]
      }}))
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }} }}
  }});

  // WTI
  const dtsW = dts.filter(d => d.stream === 'WTI_daily');
  new Chart(document.getElementById('dayTypeStackedWTI'), {{
    type: 'bar',
    data: {{
      labels: phases.map(p => phaseLabels[p]),
      datasets: arches.map((a, i) => ({{
        label: a,
        data: phases.map(p => {{
          const row = dtsW.find(d => d.phase_id === p && d.day_archetype === a);
          return row ? row.pct : 0;
        }}),
        backgroundColor: colors[i % colors.length]
      }}))
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }} }}
  }});

  // Table
  let html = '<table><tr><th>Stream</th><th>Phase</th><th>Archetype</th><th>Count</th><th>%</th></tr>';
  dts.forEach(d => {{
    html += `<tr>
      <td>${{d.stream.replace('_daily', '')}}</td>
      <td><span class="badge" style="background:${{phaseColors[d.phase_id]}}">P${{d.phase_id}}</span></td>
      <td>${{d.day_archetype}}</td>
      <td>${{d.count}}</td>
      <td>${{d.pct.toFixed(1)}}</td>
    </tr>`;
  }});
  html += '</table>';
  document.getElementById('dayTypeTable').innerHTML = html;
}})();

// ============================================================
// TRIPLETS TAB
// ============================================================
(function() {{
  const tri = CHART_DATA.top_triplets;

  // Bar chart of composite scores
  const labels = tri.map(t => (t.leg_triplet || '').substring(0, 40) + '...');
  new Chart(document.getElementById('tripletChart'), {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [
        {{ label: 'n occurrences', data: tri.map(t => t.n_occurrences), backgroundColor: '#3c6382', yAxisID: 'y' }},
        {{ label: 'Composite score', data: tri.map(t => t.composite_score), backgroundColor: '#e94560', yAxisID: 'y1' }}
      ]
    }},
    options: {{
      plugins: {{ legend: {{ position: 'bottom' }} }},
      scales: {{ y: {{ position: 'left' }}, y1: {{ position: 'right', grid: {{ drawOnChartArea: false }} }} }},
      indexAxis: 'y'
    }}
  }});

  let html = '<table><tr><th>Stream</th><th>Phase</th><th>Triplet</th><th>n</th><th>support</th><th>conf</th><th>score</th></tr>';
  tri.forEach(t => {{
    html += `<tr>
      <td>${{t.stream.replace('_session', '')}}</td>
      <td><span class="badge" style="background:${{phaseColors[t.phase_id]}}">P${{t.phase_id}}</span></td>
      <td style="font-family:monospace; font-size:11px">${{t.leg_triplet}}</td>
      <td>${{t.n_occurrences}}</td>
      <td>${{t.support ? t.support.toFixed(2) : '-'}}</td>
      <td>${{t.confidence ? t.confidence.toFixed(2) : '-'}}</td>
      <td>${{t.composite_score ? t.composite_score.toFixed(3) : '-'}}</td>
    </tr>`;
  }});
  html += '</table>';
  document.getElementById('tripletTable').innerHTML = html;
}})();

// ============================================================
// CROSS FACTOR TAB
// ============================================================
(function() {{
  const cf = CHART_DATA.cross_factor;
  const ll = cf.filter(c => c.test === 'lead_lag_daily');

  new Chart(document.getElementById('leadLagChart'), {{
    type: 'bar',
    data: {{
      labels: ll.map(l => (l.lag_days > 0 ? 'WTI leads ' : l.lag_days < 0 ? 'BRENT leads ' : 'Contemp') + Math.abs(l.lag_days) + 'd'),
      datasets: [{{ label: 'Correlation', data: ll.map(l => l.corr), backgroundColor: ll.map(l => Math.abs(l.lag_days) === 0 ? '#e94560' : '#3c6382') }}]
    }},
    options: {{ plugins: {{ legend: {{ display: false }} }} }}
  }});

  // Weekly
  const wk = cf.filter(c => c.test === 'weekly_structure');
  new Chart(document.getElementById('weeklyChart'), {{
    type: 'bar',
    data: {{
      labels: wk.map(w => w.factor),
      datasets: [
        {{ label: 'WTI mean ret %', data: wk.map(w => w.mean_wti_ret), backgroundColor: '#f7b733' }},
        {{ label: 'BRENT mean ret %', data: wk.map(w => w.mean_brent_ret), backgroundColor: '#e94560' }}
      ]
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
  }});

  // OPEC
  const op = cf.filter(c => c.test === 'opec_meeting_day');
  new Chart(document.getElementById('opecChart'), {{
    type: 'bar',
    data: {{
      labels: op.map(o => o.factor),
      datasets: [
        {{ label: 'WTI', data: op.map(o => o.mean_wti_ret), backgroundColor: '#f7b733' }},
        {{ label: 'BRENT', data: op.map(o => o.mean_brent_ret), backgroundColor: '#e94560' }}
      ]
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
  }});

  // EIA chart
  const eia = cf.filter(c => c.test === 'eia_wednesday');
  const eiaP = [...new Set(eia.map(e => e.phase_id))].sort();
  new Chart(document.getElementById('eiaChart'), {{
    type: 'bar',
    data: {{
      labels: eiaP.flatMap(p => ['P' + p + ' Wed', 'P' + p + ' nonWed']),
      datasets: [
        {{ label: 'WTI mean ret %', data: eiaP.flatMap(p => {{
          const w = eia.find(e => e.phase_id === p && e.factor === 'is_wed');
          const n = eia.find(e => e.phase_id === p && e.factor === 'non_wed');
          return [w ? w.mean_wti_ret : 0, n ? n.mean_wti_ret : 0];
        }}), backgroundColor: '#f7b733' }},
        {{ label: 'BRENT mean ret %', data: eiaP.flatMap(p => {{
          const w = eia.find(e => e.phase_id === p && e.factor === 'is_wed');
          const n = eia.find(e => e.phase_id === p && e.factor === 'non_wed');
          return [w ? w.mean_brent_ret : 0, n ? n.mean_brent_ret : 0];
        }}), backgroundColor: '#e94560' }}
      ]
    }},
    options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
  }});

  // OPEC table
  const opec = CHART_DATA.opec;
  let html = '<table><tr><th>Date</th><th>Decision</th><th>Δ production</th><th>Note</th></tr>';
  opec.forEach(o => {{
    html += `<tr>
      <td>${{o.meeting_date}}</td>
      <td>${{o.decision}}</td>
      <td>${{o.production_change_kbd}}</td>
      <td style="font-size:11px">${{o.note}}</td>
    </tr>`;
  }});
  html += '</table>';
  document.getElementById('opecTable').innerHTML = html;
}})();

// ============================================================
// MIND MAP
// ============================================================
(function() {{
  const svg = document.getElementById('mindmapSvg');
  svg.innerHTML = `
    <defs>
      <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
        <path d="M0,0 L0,6 L9,3 z" fill="#e94560"/>
      </marker>
    </defs>
    <!-- Center: WAR REGIME -->
    <circle cx="550" cy="300" r="50" fill="#e94560" />
    <text x="550" y="295" text-anchor="middle" fill="white" font-size="14" font-weight="bold">WAR</text>
    <text x="550" y="315" text-anchor="middle" fill="white" font-size="14" font-weight="bold">REGIME</text>

    <!-- Phase cluster (left) -->
    <circle cx="200" cy="100" r="35" fill="#3c6382" />
    <text x="200" y="100" text-anchor="middle" fill="white" font-size="11">PHASES</text>
    <text x="200" y="115" text-anchor="middle" fill="white" font-size="11">(6)</text>
    <line x1="230" y1="120" x2="510" y2="280" stroke="#e94560" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Price cluster (right) -->
    <circle cx="900" cy="100" r="35" fill="#38ada9" />
    <text x="900" y="100" text-anchor="middle" fill="white" font-size="11">PRICE</text>
    <text x="900" y="115" text-anchor="middle" fill="white" font-size="11">(98 days)</text>
    <line x1="870" y1="120" x2="600" y2="280" stroke="#e94560" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Windows cluster (top) -->
    <circle cx="550" cy="50" r="35" fill="#f7b733" />
    <text x="550" y="50" text-anchor="middle" fill="white" font-size="11">WINDOWS</text>
    <text x="550" y="65" text-anchor="middle" fill="white" font-size="11">(10)</text>
    <line x1="550" y1="85" x2="550" y2="250" stroke="#e94560" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Cross-factor cluster (bottom) -->
    <circle cx="350" cy="500" r="35" fill="#fc5c65" />
    <text x="350" y="495" text-anchor="middle" fill="white" font-size="11">CROSS</text>
    <text x="350" y="510" text-anchor="middle" fill="white" font-size="11">FACTOR</text>
    <line x1="380" y1="475" x2="510" y2="330" stroke="#e94560" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Anomalies cluster (right-bottom) -->
    <circle cx="750" cy="500" r="35" fill="#e77f67" />
    <text x="750" y="495" text-anchor="middle" fill="white" font-size="11">ANOMALIES</text>
    <text x="750" y="510" text-anchor="middle" fill="white" font-size="11">(13)</text>
    <line x1="720" y1="475" x2="600" y2="330" stroke="#e94560" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Day types (left-bottom) -->
    <circle cx="100" cy="500" r="35" fill="#888" />
    <text x="100" y="495" text-anchor="middle" fill="white" font-size="11">DAY</text>
    <text x="100" y="510" text-anchor="middle" fill="white" font-size="11">TYPES</text>
    <line x1="130" y1="475" x2="500" y2="330" stroke="#e94560" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Action node (bottom-center) -->
    <circle cx="550" cy="570" r="35" fill="#0f3460" stroke="#fff" stroke-width="2"/>
    <text x="550" y="565" text-anchor="middle" fill="white" font-size="11">TRADE</text>
    <text x="550" y="580" text-anchor="middle" fill="white" font-size="11">ACTION</text>
    <line x1="550" y1="350" x2="550" y2="535" stroke="#e94560" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Labels for connections -->
    <text x="350" y="200" font-size="10" fill="#a0a8b8">conditions</text>
    <text x="700" y="200" font-size="10" fill="#a0a8b8">feeds</text>
    <text x="555" y="170" font-size="10" fill="#a0a8b8">categorizes</text>
    <text x="430" y="410" font-size="10" fill="#a0a8b8">modulates</text>
    <text x="650" y="410" font-size="10" fill="#a0a8b8">flags events</text>
    <text x="280" y="410" font-size="10" fill="#a0a8b8">classifies</text>
    <text x="555" y="450" font-size="10" fill="#a0a8b8">output →</text>
  `;
}})();
</script>

</body>
</html>
"""


def main():
    print(">>> dashboard_engine.py v2 starting", flush=True)
    data = build_chart_data()
    out = render_html(data)
    (BASE / "dashboard.html").write_text(out, encoding="utf-8")
    print(f">>> wrote dashboard.html ({len(out):,} chars)", flush=True)


if __name__ == "__main__":
    main()
