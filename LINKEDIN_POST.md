# LinkedIn Post — Crude Oil War-Regime Pattern Mining

---

**The honest version of what 6 months of "vibe coding" a quant pipeline actually looks like 🛢️📊**

---

I've been quiet for a while. Building something that started as a frustrated trader's spreadsheet and ended up as a 15-stage agentic pipeline that mines 65,000+ rows of WTI/Brent data across the Iran-Israel conflict timeline.

**What it does**: Given (war phase, day type, current session window) → outputs conditional probabilities with Bayesian posteriors, Kelly/vol-target position sizing, ATR-based stops, and FDR-corrected significance.

**What it doesn't do**: Predict where price goes next. It's a lookup table, not a crystal ball.

---

## The journey in 7 acts

**Act 1: "Just give me the data"**
Wanted MCX CRUDEOILM. Upstox token broken. Fyers/Dhan/ICICI paywalled. AngelOne — no expired contracts. Spent weeks on API dead ends. Eventually: synthetic MCX from WTI × USD/INR + yfinance for WTI/Brent. 7-day chunked requests to dodge Yahoo rate limits.

**Act 2: "The data is lying to me"**
XLSX files saved as .csv. Session windows mislabeled for Mar 12–29. Hardcoded end dates fetching 1987 spot data. Built `_xlsx_helper.py`, makeshift relabeler, dynamic date bounds.

**Act 3: "News? What news?"**
No news dataset. GDELT rate limits. Hallucinated events. Built self-feeding news engine with credibility gates. Anomaly-correlated news lookup (|z|>2.5 → "what happened that day?").

**Act 4: "My patterns are overconfident"**
Phase 3: 4 trading days. Phase 4: 6 days. Frequencies lying at n<5. Added Beta-Binomial posteriors (95% HDI), Benjamini-Hochberg FDR per (stream×phase), hierarchical shrinkage (weight=20). All in `statistical_rigor.py`.

**Act 5: "What phase are we in TODAY?"**
RandomForest + isotonic calibration → `live_regime_classifier.py`. Drift detection. SHAP explanations. Trains in 24s.

**Act 6: "Patterns ≠ profitable signals"**
Walk-forward backtester: expanding window, realistic fills (next-bar-open + slippage), ATR stops per magnitude tier, Kelly ∩ vol-target sizing, DD controls (reduce at 5%, stop at 10%), Monte Carlo CIs.

Results: 290 trades, 63% WR, PF=2.74, Sharpe=2.09, MC 95% CI expectancy [+0.21%, +1.11%] ✅

**Act 7: "Make it run with one command"**
`enhanced_update_all.py` — 15 scripts, checksum-based incremental updates, skip/only flags, auto-dashboard rebuild. ~9 minutes end-to-end.

---

## The Dashboard (my favorite part)

`dashboard_v3.html` — opens in browser, no build step. 13 tabs:
- 🎯 **Live Signals** — "IF Phase 6 + whipsaw_day + us_open → THEN mcx_tail DOWN 62.5% (n=8)"
- 🤖 **Regime** — Current phase + confidence + feature importance
- 🌍 **Macro** — DXY/SPX/VIX/Gold regimes + conditional crude returns
- 📊 **Backtest** — Equity curve, per-signal/phase/archetype attribution
- ⚠️ **Anomalies** — |z|>2.5 days + correlated news headlines
- 📝 **Review** — Honest gaps: no real MCX, no live feed, no options vol

---

## What I learned (the hard way)

1. **Regime-relative everything** — Fixed thresholds die across vol regimes. Phase 1 ATR=2.95%, Phase 5 ATR=1.27%.

2. **Bayesian > frequencies at small n** — Dirichlet(1,1,1) posteriors give honest 95% HDI that widen when data is thin.

3. **Multiple comparisons will kill you** — FDR per family, not Bonferroni. Found exactly 1 significant window bias after correction (WTI us_open in P1).

4. **ATR-based stops per tier** — Q1=0.5×ATR, Q5=2.0×ATR. Respects regime vol, not fixed rupees.

5. **Kelly ∩ Vol-target** — Kelly maximizes growth, vol-target caps risk. `min()` of both + drawdown controls.

6. **Synthetic data has a place** — No MCX API? Synthetic MCX from WTI×USD/INR preserves cross-asset structure for research. Label it honestly.

7. **Single-command UX matters** — `python scripts/enhanced_update_all.py --incremental` beats "read the wiki" every time.

---

## The honest gaps (recruiters: this is the "known unknowns" section)

| Missing | Why | Effort |
|---------|-----|--------|
| Real MCX CRUDEOILM | AngelOne/Upstox integration | 1-2 weeks |
| Live data feed | Static artifacts only | 2 weeks |
| Real-time news | GDELT rate-limited | 1 week |
| Options vol surface | Placeholder only | 1 week |
| Rolling walk-forward | Single expanding window | 1 week |

**This is research infrastructure, not a trading system.** The patterns are validated; the live execution layer isn't built.

---

## Why I'm sharing this

Because the "vibe coding" narrative skips the 6 months of API dead ends, rate limits, hallucinated news, mislabeled session windows, hardcoded 1987 spot data, and the 47 times I wanted to delete the repo.

The pipeline works because every design choice was **forced by data reality** — small samples demanded Bayesian shrinkage; regime shifts demanded phase-relative thresholds; execution reality demanded ATR stops and Kelly sizing.

**The output isn't "price goes up."** It's: *"Historically, in Phase 6, on a whipsaw day, in us_open window → next window (mcx_tail) went DOWN 62.5% of the time (n=8). Here's your entry, stop, target, and position size."*

That's the difference between gambling and a conditional probability lookup table.

---

## Tech Stack
Python (pandas, scikit-learn, yfinance) • Chart.js • 9 MCP servers • Agentic orchestration • Isotonic calibration • Benjamini-Hochberg • Hierarchical shrinkage • Walk-forward validation • Monte Carlo CIs

---

*If you're building something similar — energy/commodities quant, regime-conditional patterns, agentic research pipelines — happy to swap notes. DM me.*

---

#QuantFinance #AlgorithmicTrading #CrudeOil #MachineLearning #Python #AgenticAI #DataScience #TradingSystems #VibeCoding #PortfolioProject