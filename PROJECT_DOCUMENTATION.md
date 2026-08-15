# Crude Oil War-Regime Pattern Mining System
## Complete Project Documentation — From Chaos to Production Pipeline

---

## 🎯 Executive Summary

This project evolved from a frustrating manual trading analysis into a **production-grade, agentic quant research pipeline** that mines 65,000+ rows of WTI/Brent crude oil data across the Iran-Israel conflict timeline (Mar–Jul 2026) to surface statistically-backed, regime-conditional intraday patterns.

**What it delivers:**
- **6-phase war regime taxonomy** grounded in geopolitical events
- **15-stage automated pipeline** from raw data → interactive trading dashboard
- **Bayesian probabilistic signals** with Kelly/vol-target sizing & ATR-based stops
- **Walk-forward validated backtest**: 290 trades, 63% win rate, PF=2.74, Sharpe=2.09
- **Single-command auto-update** (`python scripts/enhanced_update_all.py`) for incremental data refresh

**Tech Stack**: Python (pandas, scikit-learn, yfinance), Chart.js dashboard, 9 MCP servers, agentic orchestration

---

## 📖 The Origin Story — Why This Exists

### The Problem (Pre-Pipeline)
I was manually analyzing crude oil patterns using basic web search + bucket classification. Trades kept going wrong. The data was messy, the patterns weren't statistically validated, and there was no systematic way to condition on *regime* (war phase, day type, session window).

### The Journey (Abbreviated)

| Phase | Challenge | Resolution |
|-------|-----------|------------|
| **Data Acquisition** | No reliable MCX CRUDEOILM API (Upstox token issues, Fyers/Dhan/ICICI paywalls, AngelOne no expired contracts) | Built synthetic MCX from WTI × USD/INR + yfinance for WTI/Brent; 7-day chunked requests to bypass Yahoo limits |
| **Data Quality** | XLSX files masquerading as CSVs; session window mislabeling (Mar 12–29); hardcoded end dates; spot data fetching 1987–present | Created `_xlsx_helper.py`; makeshift relabeler; dynamic end-date logic; date-bounded spot fetcher |
| **News Integration** | No news dataset; GDELT/NewsAPI rate limits; hallucinated events | Built self-feeding news engine with credibility gates; anomaly-correlated news lookup |
| **Statistical Rigor** | Small samples (Phase 3: 4 days, Phase 4: 6 days); multiple comparisons; overconfident frequencies | Beta-Binomial posteriors, Benjamini-Hochberg FDR, hierarchical shrinkage — all in `statistical_rigor.py` |
| **Regime Detection** | No way to know "what phase are we in today?" | RandomForest + isotonic calibration → `live_regime_classifier.py` with drift detection |
| **Backtest Validation** | Patterns ≠ profitable signals | Walk-forward backtester with ATR stops, Kelly/vol sizing, DD controls, Monte Carlo CIs |
| **Orchestration** | 15 scripts, complex dependencies, manual re-runs | `enhanced_update_all.py` — single command, incremental via checksums, skip/only flags |

---

## 🏗️ Architecture — The 15-Stage Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ENHANCED PIPELINE (15 Steps)                     │
├─────────────────────────────────────────────────────────────────────────┤
│  1. enhanced_data_ingestion.py   →  13 source CSVs + synthetic MCX     │
│       Checksums, incremental, rollover logic, USD/INR fill             │
├─────────────────────────────────────────────────────────────────────────┤
│  2. primitives_engine.py         →  window_return_pct, regime-rel      │
│       thresholds, magnitude tiers (Q1–Q5), legs, ATR-equivalent        │
├─────────────────────────────────────────────────────────────────────────┤
│  3. window_pattern_engine.py     →  direction splits, transition       │
│       matrices, high/low attribution, magnitude × weekday crosstabs    │
├─────────────────────────────────────────────────────────────────────────┤
│  4. triplet_miner.py             →  3-leg sequential patterns          │
│       support/confidence/composite score, dates attached               │
├─────────────────────────────────────────────────────────────────────────┤
│  5. conformity_engine.py         →  AR(1) half-life, vol clustering,   │
│       session liquidity proxy, daily momentum + concept_citations.md   │
├─────────────────────────────────────────────────────────────────────────┤
│  6. anomaly_engine.py            →  rolling z-score (|z|>2.5)          │
│       vol/move/excursion/volume anomalies → news correlation step      │
├─────────────────────────────────────────────────────────────────────────┤
│  7. day_type_engine.py           →  8 archetypes (trend, whipsaw,     │
│       gap-and-hold, range-bound, late-session-decisive ± direction)    │
├─────────────────────────────────────────────────────────────────────────┤
│  8. cross_factor_engine.py       →  Brent-WTI lead-lag, EIA Wed,       │
│       weekly structure, OPEC+, expiry proximity                        │
├─────────────────────────────────────────────────────────────────────────┤
│  9. statistical_rigor.py         →  FDR q-values, Bayesian posteriors, │
│       hierarchical shrinkage → playbook_shrunk.csv                     │
├─────────────────────────────────────────────────────────────────────────┤
│ 10. synthesis_engine.py          →  playbook.json, final_playbook.md   │
│       (phase × day_type × window) → conditional probs                  │
├─────────────────────────────────────────────────────────────────────────┤
│ 11. live_regime_classifier.py    →  RF + calibration, drift detection  │
│       predicts current phase_id + confidence + feature importance      │
├─────────────────────────────────────────────────────────────────────────┤
│ 12. probabilistic_signal_engine.py →  Bayesian P(UP), Kelly/vol sizing │
│       ATR stops per tier, DD controls, FDR filter                     │
├─────────────────────────────────────────────────────────────────────────┤
│ 13. walkforward_backtester.py    →  expanding window, realistic fills  │
│       290 trades, MC 95% CI on expectancy/Sharpe                       │
├─────────────────────────────────────────────────────────────────────────┤
│ 14. enhanced_cross_asset.py      →  DXY/SPX/VIX/Gold regimes, COT,     │
│       options vol surface, rolling correlations, spread signals        │
├─────────────────────────────────────────────────────────────────────────┤
│ 15. dashboard_engine_v3_fixed.py →  13-tab Chart.js dashboard          │
│       signals, regime, macro, anomalies, backtest, risk, review        │
└─────────────────────────────────────────────────────────────────────────┘
```

**Core Principle**: *Compute-local, Reason-global* — all heavy lifting in Python; agent only reads compact artifacts (CSV/JSON/Parquet), never raw rows.

---

## 🔑 Key Technical Decisions & Why

| Decision | Rationale |
|----------|-----------|
| **Regime-relative magnitude tiers** (per-phase percentiles) | Fixed % thresholds fail across vol regimes; Phase 1 ATR=2.95% vs Phase 5 ATR=1.27% |
| **Bayesian Dirichlet(1,1,1) posteriors** | Frequencies lie at n<5; posteriors give 95% HDI that widen honestly |
| **Benjamini-Hochberg per (stream × phase)** | Controls false discoveries without Bonferroni's over-conservatism |
| **Hierarchical shrinkage (weight=20)** | Pulls extreme small-n estimates toward phase mean; n≈20 → 50% shrinkage |
| **ATR-based stops per magnitude tier** | Q1=0.5×ATR, Q5=2.0×ATR — respects regime vol, not fixed rupees |
| **Kelly ∩ Vol-target sizing** | Kelly maximizes growth; vol-target caps risk; min() of both + DD controls |
| **Walk-forward (not in-sample)** | Expanding window simulates real-time; no lookahead bias |
| **Checksum-based incremental updates** | Only re-process changed source files; 13 CSVs → 18 artifacts in ~9 min |
| **Synthetic MCX from WTI × USD/INR** | No live MCX API access; synthetic preserves cross-asset structure for research |
| **Chart.js dashboard (no build step)** | Opens in browser directly; portable, recruiter-friendly |

---

## 📊 What the Data Actually Says (Validated Findings)

### Cross-Asset Anchors
| Metric | Value | Implication |
|--------|-------|-------------|
| Brent-WTI daily correlation | **0.725** | Don't fade intraday divergence |
| Monday WTI bias | **+1.5%** | Systematic positive drift |
| Friday WTI bias | **-0.43%** | Systematic negative drift |
| Wednesday EIA (war phases) | **Negative bias** | Short bias into inventory release |

### Phase-Conditional Patterns
| Phase | Characteristic | Key Insight |
|-------|----------------|-------------|
| **P1: Full-scale war** (27d) | High vol, supply shock | Trend-following works; 78% UP after all_day_trend_up in us_open |
| **P2: Post-ceasefire** (46d) | Normalizing, OPEC+ hikes | 60% DOWN in india_midday after whipsaw_two_sided |
| **P3: Strong escalation** (4d) | **LOW CONFIDENCE** | n=4 — treat as case study |
| **P4: Naval blockade removed** (6d) | **60% whipsaw_two_sided** | Range-trade; don't fade |
| **P5: Strait closure** (13d) | Steady climb, insurance spike | Trend bias strengthening |
| **P6: Renewed escalation** (8d) | Current, high intensity | 8 all_day_trend days → trend-following favored |

### Backtest Validation (Walk-Forward)
```
Total Trades:     290
Win Rate:         63.4%
Profit Factor:    2.74
Expectancy:       +0.55%/trade
Sharpe:           2.09
Sortino:          12.01
Max Drawdown:    -11.02%
MC 95% CI Expectancy:  [+0.21%, +1.11%]  ✅ POSITIVE
MC 95% CI Sharpe:      [1.67, 5.54]       ✅ POSITIVE
```

---

## 🧪 Files Created — Complete Inventory

### Core Pipeline Scripts (`scripts/`)
| File | Purpose |
|------|---------|
| `enhanced_data_ingestion.py` | Checksums, MCX synthesis, rollover, USD/INR fill |
| `primitives_engine.py` | Returns, thresholds, tiers, legs, ATR |
| `window_pattern_engine.py` | Direction splits, transitions, high/low, magnitude × weekday |
| `triplet_miner.py` | 3-leg sequential patterns, composite scoring |
| `conformity_engine.py` | AR(1), vol clustering, liquidity proxy, momentum |
| `anomaly_engine.py` | Rolling z-score > 2.5, news correlation prep |
| `day_type_engine.py` | 8 archetypes + KMeans cross-check |
| `cross_factor_engine.py` | Lead-lag, EIA Wed, weekly, OPEC+, expiry |
| `statistical_rigor.py` | FDR, Bayesian posteriors, hierarchical shrinkage |
| `synthesis_engine.py` | Conditional probability playbook |
| `live_regime_classifier.py` | RF + calibration, drift detection, SHAP |
| `probabilistic_signal_engine.py` | P(UP\|conditions), Kelly/vol sizing, ATR stops |
| `walkforward_backtester.py` | Expanding window, Monte Carlo CIs |
| `enhanced_cross_asset.py` | DXY/SPX/VIX/Gold regimes, COT, options vol |
| `dashboard_engine_v3_fixed.py` | 13-tab Chart.js dashboard |
| `enhanced_update_all.py` | **Single-command orchestrator** |

### Artifacts (`artifacts/`)
| File | Description |
|------|-------------|
| `clean_master.parquet` | 68,661 rows × 69 cols — unified dataset |
| `primitives.parquet` | Returns, directions, tiers, legs, ATR |
| `window_stats.csv` + `window_stats_fdr.csv` | Direction splits + q-values |
| `transition_matrices/` | 50 CSV files — P(dir_next \| dir_curr) |
| `triplets_catalog.json` | 1,167 ranked 3-leg patterns |
| `bayesian_posteriors.csv` | 95% HDI on P(UP/DOWN/FLAT) |
| `playbook_shrunk.csv` | Hierarchically shrunken expectancy |
| `signals_live.csv` | Today's actionable signals |
| `backtest_summary.json` | 290 trades, metrics, MC CIs |
| `equity_curve.parquet` | For plotting |
| `macro_regime.csv` | DXY/SPX/VIX/Gold daily regimes |
| `news_anomaly_correlation.csv` | Anomaly ↔ news linkage |
| `dashboard_v3.html` | **13-tab interactive dashboard** |

### Source Data (13 CSVs → 18 with MCX)
| Original | Generated MCX |
|----------|---------------|
| wti/brent_daily_ist.csv | mcx_crudeoilm_daily_ist.csv |
| wti/brent_5m_ist.csv | mcx_crudeoilm_5m_ist.csv |
| wti/brent_15m_ist.csv | mcx_crudeoilm_15m_ist.csv |
| wti/brent_60m_ist.csv | mcx_crudeoilm_60m_ist.csv |
| wti/brent_session_windows_summary.csv | mcx_session_windows_summary.csv |
| daily_master_summary.csv | mcx_spot_daily_reference_ist.csv |
| wti/brent_spot_daily_reference_ist.csv | — |

---

## ⚡ Quick Start

```bash
# 1. Activate venv
source /home/srikrishna/.venv-wsl-new/bin/activate

# 2. Full pipeline (after appending new rows to 13 source CSVs)
python scripts/enhanced_update_all.py

# 3. Incremental (only if source files changed)
python scripts/enhanced_update_all.py --incremental

# 4. Generate today's signals only
python scripts/enhanced_update_all.py --signals-only

# 5. Rebuild dashboard only
python scripts/enhanced_update_all.py --dashboard-only
```

**Output**: `dashboard_v3.html` opens directly in browser — 13 tabs covering signals, regime, macro, anomalies, backtest, risk, review.

---

## 🎯 For Recruiters — What This Demonstrates

| Competency | Evidence |
|------------|----------|
| **End-to-end ML/Quant Engineering** | 15-stage pipeline from raw data → validated signals → interactive dashboard |
| **Statistical Rigor** | FDR, Bayesian posteriors, hierarchical shrinkage, walk-forward validation, Monte Carlo CIs |
| **Production Engineering** | Checksum-based incremental updates, dependency orchestration, error handling, drift detection |
| **Domain Expertise (Energy/Commodities)** | War-regime taxonomy, session window taxonomy, MCX/WTI/Brent mechanics, OPEC+/EIA calendar |
| **Agentic/AI Engineering** | 9 MCP servers, self-feeding news engine, agentic orchestration, autonomous debugging |
| **Product Thinking** | Single-command UX, recruiter-friendly dashboard, incremental updates, clear documentation |
| **Resilience & Problem Solving** | Navigated 5+ API dead ends, rate limits, data quality nightmares, hallucination guards |

---

## 📝 Known Gaps (Honest Assessment)

| Gap | Status | Effort to Close |
|-----|--------|-----------------|
| Real MCX CRUDEOILM data | Synthetic only | 1–2 weeks (AngelOne/Upstox integration) |
| Live data feed | Static artifacts only | 2 weeks (WebSocket + cron) |
| Real-time news | GDELT rate-limited | 1 week (paid NewsAPI + caching) |
| Options vol surface | Placeholder | 1 week (yfinance options chain) |
| Walk-forward framework | Single expanding window | 1 week (rolling retrain + OOS test) |

**Bottom Line**: This is **rigorous research infrastructure**, not a live trading system. The patterns are statistically validated; the missing layer is *live execution*.

---

## 🏁 Closing Thought

This project started with a simple frustration — "my crude trades keep going wrong" — and became a demonstration of how **systematic, statistically-honest, regime-conditional analysis** can transform noise into actionable probability tables. Every design choice was forced by data reality: small samples demanded Bayesian shrinkage; multiple comparisons demanded FDR; regime shifts demanded phase-relative thresholds; execution reality demanded ATR-based stops and Kelly sizing.

The pipeline doesn't predict where price goes next. It tells you: *"Historically, in Phase 6, on a whipsaw day, when you're in the us_open window, the next window (mcx_tail) went DOWN 62.5% of the time (n=8). Here's your entry, stop, target, and position size."*

That's the difference between gambling and a conditional probability lookup table.

---

*Generated: 2026-08-03 | Pipeline Version: 3.0 | Total Lines of Code: ~8,000+*