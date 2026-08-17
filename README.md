<div align="center">

# 🛢️ Crude AI — War-Regime Pattern & Trade-Intelligence Engine

**A self-correcting, agentic quantitative-research pipeline that mines 80,000+ rows of WTI / Brent / MCX crude-oil data across a live geopolitical conflict to surface conditional-probability trading patterns — and learns from its own predictions.**

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Pandas](https://img.shields.io/badge/pandas-3.0.3-150458?logo=pandas)](https://pandas.pydata.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.9-F7931E?logo=scikit-learn)](https://scikit-learn.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Pipeline: 15 stages](https://img.shields.io/badge/pipeline-15%20stages-38ada9)]()
[![Status](https://img.shields.io/badge/status-active-brightgreen)]()

**⚡ Not financial advice. This is a conditional-probability lookup table, not a crystal ball.** It tells you *which distribution applies today* — never a price target.

</div>

---

## 🔥 Highlights

- **17-stage agentic pipeline** — from raw OHLCV CSVs to an interactive React/Vite SPA dashboard & a news-conditioned daily trading plan. One command re-runs everything.
- **Regime-conditional intelligence** across 10 war phases (full-scale war → ceasefire → Hormuz war → de-escalation/negotiation) — every pattern is tagged to the regime it applies in.
- **Statistically honest by construction** — Bayesian Dirichlet posteriors with 95% HDI, Benjamini–Hochberg FDR multiple-comparison correction, hierarchical shrinkage, and `n<5 → LOW-CONFIDENCE` flags baked into every output column.
- **Self-correcting Prediction Scorecard (P1)** — resolves every emitted signal against the actual next-window outcome, tracks rolling hit-rate & edge-decay, and auto-down-weights stale patterns. It *learns from its own mistakes*.
- **News-conditioned daily plan** — fetches Al Jazeera / CNN Iran-live / Hormuz Letter headlines, flags escalation vs de-escalation, and forecasts *deviations* from the price-only plan.
- **Cross-phase pattern borrowing** — when the current phase has limited data, computes cosine similarity across all 10 phases (volatility/direction/return/magnitude) and borrows patterns from the most similar historical phase (Phase 10 α-borrows from Phase 7, similarity 0.886).
- **Walk-forward validated** — 297-trade backtest: 63.6% win rate, profit factor 2.10, Sharpe 4.29, **positive expectancy at 95% Monte-Carlo confidence [CI +0.20%, +0.48%].**

---

## 🧠 What it actually does

> Crude oil never follows "kill the chart." During a war, it follows *repeatable conditional distributions* — but which distribution is in play depends entirely on the **regime**. This engine cut the problem in two:

1. **Regime detection** — a calibrated RandomForest classifies *"which phase are we in?"* from price, volatility, and macro features (DXY / SPX / VIX / Gold / Copper).
2. **Regime-conditional patterns** — given `(phase, day-type, session-window)`, it answers *"what has happened next historically, with what n and confidence?"* → entry / stop / target / position-size.

It doesn't fight manipulation — it **quantifies it**: your `whipsaw_two_sided`, `late_session_decisive`, `range_bound` day-types are the *signatures of noise and stop-hunts*, re-learned as tradeable archetypes.

---

## 🚀 Quick start

```bash
# 0. Activate the project venv (me the deps in requirements-style below)
source /home/srikrishna/.venv-wsl-new/bin/activate

# 1. After appending new trading days to the 13 source CSVs:
#    (auto-detects changes → re-runs full pipeline → scores signals → emits plan)
python scripts/enhanced_update_all.py --signals-only

# 2. Full run (includes 10-min walk-forward backtest + macro overlays):
python scripts/enhanced_update_all.py --skip news_events

# 3. Output
#    • dashboard_app/     → React + Vite SPA (serve: bash start_dashboard.sh → localhost:8080)
#    • TODAYS_PLAN.md     → next trading day's window-by-window, news-conditioned plan
#    • artifacts/*.csv    → playbook, scorecard, window stats, triplets, anomalies, …
```

---

## 🧱 Architecture (compute-local, reason-global)

```
[13 source CSVs: WTI/Brent daily+intraday, 80k+ rows]
        │
        ▼
1  enhanced_data_ingestion   checksums, MCX synthesis, change detection
2  data_validator            IST normalize, phase-tag, prune → clean_master.parquet
3  primitives_engine         window returns, regime-relative tiers, legs, ATR
4  window_pattern_engine     direction splits, Markov transitions, high/low attribution
5  triplet_miner             3-leg sequential patterns + composite score
6  conformity_engine         AR(1) half-life, vol clustering, liquidity proxy
7  anomaly_engine            rolling |z|>2.5 anomalies
8  day_type_engine           8 day archetypes + KMeans cross-check
9  cross_factor_engine       Brent–WTI lead-lag, EIA Wed, weekly, OPEC+, expiry
10 statistical_rigor         FDR + Bayesian posteriors + hierarchical shrinkage
11 live_regime_classifier    calibrated RF → current phase + confidence
12 probabilistic_signal_engine  P(UP|conditions), Kelly×vol sizing, ATR stops
13 prediction_scorecard        signal→outcome hit-rate, edge-decay, stale-flag
14 daily_report                news-conditioned next-day window-by-window plan
15 walkforward_backtest        expanding-window, Monte-Carlo CI, realistic fills
16 cross_phase_engine          phase similarity matrix + pattern borrowing (P10←P7)
17 enhanced_cross_asset        DXY/SPX/VIX/Gold regimes, spread signals, rolling corr
        │
        ▼
dashboard_app (React SPA)  ·  TODAYS_PLAN.md  ·  artifacts/* (parquet/csv/json)
```

**Design principle:** all heavy lifting happens in vectorized pandas/numpy/scipy inside scripts; the reasoning layer only ever reads **compact artifacts** (CSV/JSON/parquet), never raw rows — this is what makes 80k+ rows rigorous and auditable, not just fast.

---

## 📊 Sample output — a real Aug-14 plan (condensed)

```
Regime: Phase 10 — second_deescalation_active_negotiation_hormuz_deal (conf 100%)
Last close: WTI $81.18 · BRENT $87.01 (2026-08-13)

Window (IST)        Bias   %UP  %DN  n   mean B%  mean W%
global_reopen       DOWN   24   35   17   +0.07    -0.13
mcx_open_drive      UP     47   35   17   +0.11    +0.04
india_morning       DOWN   24   53   17   -0.03    -0.13
india_midday        UP     56   33   18   +0.37    +0.48   ← strongest LONG
europe_midday       DOWN   33   61   18   -1.04    -1.03   ← strongest SHORT
us_pre_open         FLAT   39   39   18   +0.04    -0.03
us_open             UP     50   19   36   +0.31    +0.32
mcx_tail            UP     39   17   18   +0.18    +0.11

Live news ⚠️ ESCALATORY: 6 killed in Houthi Bab al-Mandeb attack · Iran claims
Hormuz control · Israeli strikes in south Lebanon
→ If an escalation headline breaks, expect an UP spike then whipsaw (reverses
  the base-long plan). Fade the spike; widen stops.
```

---

## 🧪 Statistical rigor (why you can trust the numbers)

| Technique | Where | Why it matters |
|---|---|---|
| **Dirichlet(1,1,1) Bayesian posteriors + 95% HDI** | `statistical_rigor` | Frequencies lie at small n; HDIs widen honestly (n=4 → UP 0.286, HDI [0,0.60]) |
| **Benjamini–Hochberg FDR** per (stream×phase) | `statistical_rigor` | Only 1/184 window biases survived correction — exposes noise instead of celebrating it |
| **Hierarchical shrinkage (weight=20)** | `statistical_rigor` | Pulls extreme small-n estimates toward the phase mean |
| **Regime-relative magnitude tiers** (per-phase percentiles) | `primitives` | Fixed % thresholds die across regimes (P1 ATR 2.95% vs P5 1.27%) |
| **Walk-forward + Monte Carlo CI** | `walkforward_backtest` | Expanding window, no lookahead; expectancy CI [+0.21%, +1.11%] |
| **`n<5 → LOW-CONFIDENCE`** in every output column | all engines | Sample-size discipline is data, not prose |

---

## 🧩 Modules / file map (50+ files, ~20k lines)

| Area | Key files |
|---|---|
| Ingestion & normalization | `crude_data_import.py`, `scripts/enhanced_data_ingestion.py`, `scripts/data_validator.py`, `scripts/_xlsx_helper.py` |
| Core analytics | `primitives`, `window_pattern`, `triplet_miner`, `conformity`, `anomaly`, `day_type`, `cross_factor`, `synthesis` engines |
| Statistical rigor | `scripts/statistical_rigor.py` |
| Predictive layer | `live_regime_classifier.py`, `probabilistic_signal_engine.py` |
| Validation | `walkforward_backtester.py`, `backtester.py`, `risk_management.py` |
| Intelligence overlays | `enhanced_cross_asset.py`, `cross_asset.py`, `news_event_engine.py` |
| Cross-phase similarity | `scripts/cross_phase_engine.py` — Phase 10 borrows from Phase 7 (0.886 similarity) |
| Self-correction | `scripts/prediction_scorecard.py` |
### Dashboard
```bash
# Serve the React SPA (production build):
bash start_dashboard.sh   # → http://localhost:8080

# Development mode (hot reload):
cd dashboard && npm run dev   # → http://localhost:5173
```
| Auto-plan | `scripts/daily_report_generator.py` |
| Orchestration & viz | `enhanced_update_all.py`, `update_all.py`, `build_react_dashboard.py` → `dashboard_app/` (React/Vite SPA) |
| Docs | `README.md` (full directive), `AGENT_INSTRUCTIONS.md`, `CONVERSATION_LOG.md` (single-source handoff), `PROJECT_DOCUMENTATION.md`, `CRITICAL_REVIEW.md`, `LINKEDIN_POST.md` |

Data is stored as **XLSX-under-.csv** (Excel format with `.csv` suffix) across WTI/Brent daily + 5m/15m/60m intraday + session summaries + spot references. `scripts/_xlsx_helper.py` is the canonical reader.

---

## 🛠️ Stack

Python 3.12 · pandas 3.0 · numpy 2.5 · scipy 1.18 · statsmodels 0.14.6 · scikit-learn 1.9 · pyarrow 25 · chart.js (browser dashboard) · requests · yfinance · joblib

**Dependencies** (install into a venv):
```bash
pip install pandas numpy scipy statsmodels scikit-learn pyarrow matplotlib \
            openpyxl joblib scikit-learn requests yfinance
```

---

## ⚠️ Honest limitations (we don't hide the hard parts)

- **Phase-10 sample is tiny** (n≈8–36/window) → most current patterns are `LOW-CONFIDENCE`. This is *by design*: the engine flags its own weak spots.
- **Live news is fail-soft** — if a source is unreachable, the report says so rather than hallucinating headlines.
- **GDELT / NewsAPI news ingestion** is rate-limited (429s); the daily report uses lighter direct fetches.
- **MCX CRUDEOILM is synthetic** (WTI × USD/INR) — no real MCX OI/FX feed was obtainable from free providers; labeled clearly.

---

## 🤝 Contributing

This is a war-regime *concept proof of the "regime-conditional, self-correcting pattern-mining" workflow* — **adapt the template to any instrument / regime / dataset.** PRs welcome for: real broker/MCX data feeds, additional macro overlays (options vol surface, COT), deeper news-sentiment features, and more robust scenario modeling.

**⭐ If this pattern-mining + self-correction architecture resonates, star it** — it's a reusable template for *any* regime-conditional quant/research project.

---

<div align="center">

Made with 🛢️ + 📈 + 🧠 · A conditional-probability engine for a messy world.

*Not financial advice. Trade at your own risk.*

</div>