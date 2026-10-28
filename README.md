# CRUDE PRICES VOLATALITY ANALYSIS DURING THE IRAN WAR/HORMUZ CRISS OF 2026 

## Tech Stack & Tools Used

- Data: yfinance, FRED, EIA, Databento (dead end), GDELT/NewsAPI, Al Jazeera/CNN/Hormuz Letter RSS
- Py libs: pandas, numpy, scipy, statsmodels, scikit-learn, pyarrow, joblib, openpyxl, yfinance, requests, matplotlib, ruptures (optional)
- ML/quant: RandomForest, isotonic calibration, GMM, PCA, HDBSCAN, KMeans, SHAP
- MCP servers (9): context7, filesystem, fetch, brave-search, playwright, sqlite/postgres, e2b sandbox, github, remember (context persistence)
- Agentic tools: Claude Code, Codex, Antigravity, OpenRouter (model swapping), MCPM Manager, Wispr Flow, Whisper (CUDA) for lecture transcription
- Infra/UI: Vercel, GitHub, Cloudflare Tunnel, Vite/React, Chart.js, Ubuntu/WSL


## Technical Architecture & Production Engineering

One section, because for this project the architecture and the operational story are the same object. Planned contents:

- The 17-stage pipeline diagram (raw 13 CSVs → ingestion → validation → primitives → window patterns → triplet miner (1,167 ranked) → conformity (AR(1) half-life, vol clustering) → anomaly engine (|z|>2.5) → day-type engine (8 archetypes + KMeans cross-check) → cross-factor (EIA Wed, OPEC+, expiry, lead-lag) → statistical rigor → regime classifier → signal engine → scorecard → daily report → walk-forward backtester → cross-phase borrowing → cross-asset → dashboard).
- The compute-local, reason-global principle — heavy lifting in Python, agent reads only compact artifacts; token efficiency as a correctness requirement, not a cost.
- Price-phase branch coexistence — 10-step branch, artifacts_pricephases/, original untouched as museum.
- The signal engine anatomy — 3-gate abstention, Kelly ∩ vol-target sizing, ATR stops per magnitude tier, candlestick fallback for 1-sample phases.
- Orchestration — single command, --skip/--only/--incremental flags, checksums, ~9 min runtime, dependency ordering, 20/21 steps passing.
- Data layer — synthetic MCX construction, chunked fetcher, xlsx helper, dynamic date bounds, dual-pipeline parquet/CSV artifacts.
- Microstructure layer — read-only sub-bucket computation as the non-breaking overlay.


## Quant Methodology & Statistical Rigor

The "why you can trust the numbers" section. Planned contents, each with the one-line honest rationale:

- Regime-relative magnitude tiers (per-phase percentiles, not fixed %)
- Dirichlet(1,1,1) Bayesian posteriors + 95% HDI
- Benjamini-Hochberg FDR per (stream × phase)
- Hierarchical shrinkage (weight=20)
- Purged walk-forward + embargo from AR(1) half-life + Monte Carlo CIs
- Brier score / log-loss / calibration curves
- 5-score operational accuracy panel (hit rate, calibration, economic edge, regime accuracy, abstention rate)
- Cross-phase pattern borrowing (cosine similarity, P10 ← P7)
- Vol-regime conditional sizing scalar


## Results / Evidence / Outcomes / Metrics / Final Structure

Cold hard facts only. Every number paired with its honest label (in-sample vs out-of-sample):

- Backtest: 290 trades, 63.4% win rate, PF 2.74, Sharpe 2.09, Sortino 12.01, Max DD −11.02%, expectancy +0.55%/trade, MC 95% CI expectancy [+0.21%, +1.11%], Sharpe CI [1.67, 5.54] — purged walk-forward, not in-sample
- In-sample vs OOS honesty gap table: in-sample Sharpe 4.29 → OOS 2.09 — the system self-reporting its own drop
- Signal resolution: 4 resolved signals, 100% resolution rate, Brier tracked
- Cluster/phase results: 12 phases (P1 27d war, P3 n=4 case study, P10 8d), 7 clusters (BIC-selected), 308 dates re-classified
- Data: ~112,948 rows clean_master, 65k+ original spec, 80k+ rows cited, 13 source CSVs → 18 artifacts
- Performance: checksum incremental run ~9 min, 21-step orchestrator, 20/21 passing
- Validated findings: Brent-WTI correlation 0.725, Monday +1.5%, Friday −0.43%, Wednesday EIA negative bias in war phases
- Final functioning evidence: TODAYS_PLAN.md sample output (the actual plain-English plan with %UP/%DN, n, news flags), dashboard artifact, artifact inventory


## The Chronological Journey of building this Training-Analysis-Prediction Model

### PHASE 1: The First Principles — Framing the Problem Before Touching Data

The thinking, before any code: future price action is nothing but a repetition of patterns, and AI's real edge isn't chat — it's ingesting massive data, finding patterns, and telling the big-picture data story. So instead of asking a chatbot "will price go up?", the question was reframed: why not train a model on the price data itself, and let it fish for patterns? That single reframe set the entire project's shape — and the basis on which any later model would predict (which ideologies, which data points) was settled deliberately, through clarifying questions, not assumptions.

The first execution was deliberately primitive — A minimum viable approach to test whether the pattern premise held at all:
  
  Day-type buckets: Categorise days from price movement alone:
  - Full-day rallies
  - Full-day dips
  - Two-sided violent whipsaw
  - Flat days that still ended at the day's high/low
  
  News overlay: Tag each bucket as escalation / de-escalation / neutral. This surfaced the project's founding observation: price repeatedly failed to reflect breakout news — the first hard evidence of manipulation, and the reason "trust the tape, quantify the
  divergence" became a design principle.
  
  Session windows: Split buckets across Asian / European / US market hours, based on the reasoning that countries with different Hormuz exposure (Japan, Europe, India, US) move crude differently at their own market opens.
  
  Output structure: A two-tiered matrix — day-types × session windows × three news flags — built purely on WTI/Brent open-close prices via ChatGPT/Claude web search, over a short timeframe.
  
  Crucially, even this primitive stage was designed backwards from the questions the eventual model must answer. The dataset was structured so a later model could answer:
   
  - What past day is today most similar to?
  - Which session windows drive the day, in which direction, and on what news type?
  - When the normal pattern fails, what alternate repeatable pattern takes over?
  - If pattern P occurred on day-type X in window Y, what Q preceded it and what R succeeded it?
  - How far does price travel in INR/MCX ticks on this kind of day?
  - Which windows are safest for entry, and which are stop-hunt traps?
  - Do manipulative bearish moves follow a signature pattern by time of day and news flag?



### PHASE 2: The Data Wall (the dead-end graveyard) and the workarounds that stuck

Attempted MCX CRUDEOILM from 5 sources — Upstox, Fyers, Dhan, ICICI Breeze, AngelOne, Databento. Also dropped: USD→INR live conversion, MCX data entirely, live RSS news feeds. Pivoted to WTI/Brent via yfinance (no keys); 7-day chunked requests to bypass Yahoo limits; synthetic MCX built from WTI × USD/INR (labeled honestly as synthetic). FRED/EIA keys for FX and inventory. Hardcoded end dates pulling 1987 spot data → dynamic date bounds.


## PHASE 3: Turning a Trader's Vocabulary into Executable Python

The hardest part of the build was never the code — it was that every input started as a subjective phrase. "Psychological warfare is suppressing prices." "Contracts near expiry act weird." "Wednesday inventory days matter." None of these are columns in any API response. Each one had to be decomposed into a measurable primitive, given an explicit threshold, and implemented as a deterministic function — so that the entire qualitative worldview of the market became a computable data structure, and the model's pattern-fishing was shaped by exactly the factors a discretionary trader would reason about.

The translation pattern was applied consistently, factor by factor:

Day-type buckets — "full-day rally," "violent whipsaw," "flat-but-closing-at-extreme" became a rule-based decision tree: day_type_engine.py:23 classify_day() branches on gap-vs-range ratio, trendiness, whipsaw score, and close-location-in-range, with each directional label suffixed _up/_down. The primitives underneath were themselves translated from intuition: crude_data_import_newx.py computes day_efficiency_ratio = |C−O|/(H−L) and bins it into trendiness_score_1_to_5 / whipsaw_score_1_to_5 via np.select thresholds — "trending day" is now a number, not a feeling.
	
60 candlestick patterns — candlestick_pattern_engine.py implements all 60 classics (Marubozu, Hammer, Morning Star, Hikkake, …) as body/wick/range ratios with direction and a 0–1 strength, feeding the signal engine's Bayesian posterior at a 0.7/0.3 Bayesian-to-candlestick blend.
	
Manipulation / violent dumps — you can't code "manipulation," but you can code "statistically extreme": anomaly_engine.py flags rolling 20-session z-scores (|z| > 2.5) on volatility and volume, using rolling rather than global z precisely because global z lets extremes poison the mean.
	
News flags & geopolitics — news_event_engine.py pulls GDELT events, filters on Iran/Israel/Hormuz/OPEC/inventory keywords, and maps events to war phases and anomaly days — so "escalation vs de-escalation" and "Ukraine strikes on Russian ports" became joinable data points, not anecdotes.
	
Wednesday inventory effect — cross_factor_engine.py Test 2 reduces it to an is_wed boolean and per-phase mean-return comparisons, with EIA inventory data fetched directly via get_eia_inventory_reference().
	
Brent–WTI spread — Test 1 of the same engine pivots session returns wide and computes lead-lag correlations at lags −2…+2, so "does Brent lead WTI?" became a measured correlation table.
	
Expiry premium & roll-over — enhanced_data_ingestion.py resolves the active MCX contract per date (resolve_mcx_contract(), days_to_expiry, MCX_ROLL_DAYS_BEFORE_EXPIRY=5) and normalizes consecutive contracts into one continuous series — the "expiry premium" intuition is now a date-bounded contract-selection function.
	
Where honesty mattered — enhanced_cross_asset.py leaves term_structure_slope = np.nan with a comment "would need multiple expiries": the backwardation/contango factor is marked as not-yet-implementable rather than faked. Similarly, the synthetic MCX series is stamped SYNTHETIC_MCX end-to-end.

Every factor was translated into its own standalone engine, each writing versioned artifacts, and all wired into a single 21-step orchestrator (enhanced_update_all.py) running the full training-analysis-prediction cycle in one command — with the quant ideologies layered in as code: Dirichlet posteriors with 95% HDI (dirichlet_posterior()), Benjamini-Hochberg FDR and hierarchical shrinkage (statistical_rigor.py), Kelly ∩ vol-target sizing (kelly_fraction(), vol_target_position()), and a 3-gate abstention rule that refuses to emit a signal when pattern_n, regime confidence, or staleness say it shouldn't.
	
Competency: the core competency here is decomposition of an unstructured domain — converting a trader's gut vocabulary into measurable primitives, thresholds, and functions, each independently testable. Supporting it: systems thinking (independent engines, single artifacts, one orchestrator); edge-case discipline (roll-over normalization, low-sample guards, flag-only anomaly output); and intellectual honesty (features that can't be computed yet are labeled, not fabricated — the same "no silent assumptions" policy enforced on the coding agent was applied to the product itself)


### PHASE 4: The Founding Bet — and the Root-Cause Reckoning

With the data structured, the next decision shaped everything downstream: the entire training-analysis-prediction exercise would be conditioned on a classification of the war itself. Across the 7-month period, the conflict kept recurring in recognizably similar phases — full-scale war, complete ceasefire with deal, ceasefire without deal, naval blockade with escalation flashpoints — so the period was carved into 12 war phases (P1–P12) built from geopolitical reality. The bet was deliberate: if war behavior is repetitive, then a phase label is a legitimate conditioning variable, and every pattern mined "within Phase 5" inherits that repetition.

The bet carried the system for a long time — and then became its deepest flaw. After multiple rounds of optimization (purged backtesting, calibration, abstention gates), the honest realization landed: the model's ceiling wasn't in any of the sophisticated machinery — it was in the classification at the source. Two defects made it structural: first, the phases were a subjective, human-enforced labeling — news-derived date ranges, not objective ground-truth classes; second, and more damning, price sequences on consecutive days sharing a phase showed no day-to-day similarity — the same phase label was being stamped onto whipsaw days, trend days, and gap days alike, so the daily plan generated the same predictions for every day inside a phase, regardless of what the tape was actually doing.

Competency: navigating ambiguity (imposing structure on a market with no labels at all); decisions under uncertainty (a falsifiable bet made explicit, not hidden); and the rarest one — root-cause diagnosis against one's own investment: after months of building atop the phase taxonomy, correctly indicting the taxonomy itself rather than patching symptoms downstream.


### PHASE 5: Re-Founding the Classification on Price Itself

The fix was to make the market classify itself. Phases would no longer be continuous news date-ranges but non-continuous clubs of days that actually look alike: if Sept 21 and Oct 15 both print "strong climb, low volatility, marubozu-type candles," they belong to the same phase — even months apart. Consecutive days with different price action land in different clusters, no matter what the news said.

The execution was as deliberate as the idea. A parallel branch (price_phase_clustering/) was built so the original pipeline stayed untouched as a museum artifact — both pipelines coexisting via distinct _PRICE_PHASES output filenames. PCA+GMM clustering on z-scored candlestick features, with k selected by BIC rather than guessed, produced the first pass: 3 clusters for 146 days. That exposed two more judgment calls. The 3-cluster granularity felt too coarse against the richness of the day-type taxonomy, so a day-type one-hot feature augmentation pushed BIC-optimal clustering to 7 labeled clusters. And a deeper inspection revealed the day-type labels themselves were contaminated — they had been assigned by war-phase date ranges, so all 308 dates were re-classified news-independently from pure candlestick logic. Finally, when the question arose whether each cluster should map 1:1 to a day-type, the instinct was challenged and answered: rigid 1:1 would force misclassification — the data-driven many-to-many mapping (each cluster a measurable mix of day-types, each day-type spread across clusters) is the accurate representation, and cluster composition is reported, not constrained.

The new cluster_id was then threaded through every downstream engine — primitives, transition matrices, FDR correction, posteriors, regime classifier, signal engine, daily plan — as a like-for-like replacement of phase_id, with an incremental cluster_model.pkl classifying new dates without re-clustering history.

Competency: root-cause-driven re-architecture (rebuilding the foundation, not the facade); experiment isolation (parallel branch, zero destruction of working state); granular trade-off judgment (3 vs 7 clusters, 1:1 vs many-to-many — each argued from accuracy, not aesthetics); and auditing AI's own work rather than accepting it (catching the contaminated labels the agent had happily inherited).


### PHASE 6: The Window-Granularity Problem — and the Discipline of Not Breaking Things

One prediction-quality issue survived all of this: session windows like us_open aggregate two to five hours of price action into a single "%UP/%DOWN" line in the daily plan, so the window-to-window movement prediction stayed coarse no matter how sophisticated everything upstream was. The obvious fix — re-label the windows into finer slices — was caught before it was executed: session-window labels are baked into clean_master at ingestion time, so relabeling would split history into two incompatible regimes — seven months trained under old labels, new dates arriving under new ones, every grouped analysis comparing apples to oranges.

The chosen alternative was an additive, non-breaking overlay: the 5-minute bars already , timestamped and window-tagged, so a microstructure engine splits each wide window intoearly/late sub-buckets and computes per-sub-bucket directional stats — run identically over all dates, past and future, so no old-vs-new split ever exists. Window labels never change; the existing window_stats.csv and every downstream analysis stays valid; the plan simply gains a resolution layer beneath the aggregate. The trade-off was stated, not hidden: sub-buckets mean smaller samples per cell, answered with Bayesian shrinkage and pooling rather than pretending the numbers are stro

Competency: skepticism toward one's own first solution (catching a data-lineage trap in a fix that looked obviously right); blast-radius thinking (overlay > relabel, additive > destructive); and
honest trade-off accounting (smaller n acknowledged and mitigated, not obscured).


### PHASE 7: Closing the Loop — Making the Model Auditable and Fast Without Making It Wrong

Once the pipeline could emit predictions, the uncomfortable question surfaced: nothing ever went back and checked them. Signals were emitted daily, but yesterday's entry/stop/target was never compared against what price actually did — the scorecard sat at 0 resolved rows. That admission restructured the daily workflow around three tickets. First, a forward signal resolution loop: every emitted signal is appended to an append-only history, and each new run resolves all pending ones against realized prices before emitting fresh signals — hit/miss, actual return, growing operational track record. Second, the "backtester" was honestly re-diagnosed as in-sample fit dressed as walk-forward — it tested dates against a playbook mined from all dates, including the ones being tested. The fix was a purged, embargoed rebuild: at every test date, the playbook is rebuilt using only observations that precede it. Third, calibration: when the system announces "44% DOWN," Brier score now checks whether DOWN actually happened ~44% of the time. Alongside came a per-pattern freshness check (the last N live occurrences of each pattern, with an edge-decay flag when live hit rate falls below the playbook's claim) and volatility-regime-conditional sizing that shrinks positions in the highest-ATR phases automatically.

Competency mapping: closing the evaluation loop end-to-end (signal → resolve → history → metrics — owning the outcome, not just the output); intellectual honesty as engineering (naming the in-sample illusion before fixing it); and speed-vs-correctness judgment — refusing an optimization where correctness would silently degrade, and finding speed in caching and incrementality instead.


### PHASE 8: The Rigor Upgrade — Honest Labels, a Panel of Scores, and Explicit Refusals

The next pass (execution_prompt3) was a deliberate philosophy shift: from "does it work?" to "can it prove it works, and does it admit what it doesn't know?" The backtester's embargo stopped being arbitrary — it was derived from the data's own autocorrelation structure (the AR(1) half-life computed by the conformity engine), rather than picked from a textbook. And the report now carries both numbers side by side, explicitly labeled IN_SAMPLE vs OUT_OF_SAMPLE, so the honesty gap between them is permanently visible instead of buried — the OOS numbers dropped, and that drop was treated as the correct outcome, not a regression.

A single "credibility score" was rejected as the wrong framing and replaced with a 5-score accuracy panel, each answering a different question: directional hit rate (class-balanced, against a persistence baseline, with CI), calibration (Brier + curve near the diagonal), economic edge (expectancy after commission and slippage, bootstrapped), regime-classification accuracy (out-of-sample, not the flattering in-sample CV), and epistemic honesty — abstention rate, checked against whether abstention actually avoided losses. Abstention itself was made explicit and logged: three gates (pattern sample too small, regime confidence too low, anomaly z-score too extreme), each refusal written to abstention_log.csv with its specific reason — the system now says "insufficient data" instead of emitting a 0.00-confidence garbage signal. When a brand-new war phase appeared with near-zero observations, the silent-default bug (signals quietly generated from the wrong phase's patterns) was diagnosed to its root, fixed with a LOO-CV fallback and confidence-halving for 1–2-sample phases, and guarded with a regression check so the next phase transition can't silently repeat it.

Competency mapping: measurement design (rejecting a single vanity metric for a panel that can catch different failure modes); data-driven parameterization (embargo from AR(1) half-life, not folklore); and designing for honesty — making refusal a first-class, logged behavior rather than a failure mode.


### PHASE 9: Learning From Its Own Mistakes — Three Fears, Three Design Answers

The provision for the model to learn from its own errors started by naming three fears explicitly and refusing to wave any of them away. Fear 1 — news is the critical driver and we can't feed it live: resolved by reframing — news tells you which rulebook to use, not the price path. A headline flips the regime; what you trade is the phase-conditional statistical distribution built from months of data. The tractable problem is detecting regime change fast (the regime classifier + news-event engine), not predicting headlines. Fear 2 — future news is unknowable and there's manipulation anyway: resolved by the system's core identity — it is a conditional-probability, risk-managed engine, not a point forecaster. It never says "price will go X"; it says "in this phase, on this day-type, in this window, the next window went UP 100% (n=3) — LOW CONFIDENCE." That framing survives manipulation: the path gets distorted, but the conditional distribution re-learns as data accumulates — and even "absurd" manipulative moves get captured as repeatable archetypes (whipsaw, late-session decisive, range-bound are precisely manipulation signatures). Fear 3 — old patterns keep breaking, so what's the point: named as regime drift, and answered structurally — every pattern is a decaying prior, not a law (posterior = f(prior, new data), re-fit on every append), weighted by recency and phase relevance, with the honest admission that error-learning was so far only implicit (re-runs absorb deviations) and therefore needed the explicit prediction-vs-actual resolution loop of point 12 to become real.

Competency mapping: adversarial self-questioning as a design tool (fears turned into architecture, not optimism); concept clarity (regime drift, calibration, decaying priors — borrowed from quant practice and implemented, not name-dropped); and knowing the difference between implicit learning and an actual feedback loop.


### PHASE 10: The Daily Report Card — Translating Sophistication Into One Readable Page

All of the statistical machinery funnels into a single, deliberately humble artifact: the daily report card, organized so a non-quant can act on it in minutes. The card teaches its own reading rules on its face — n is how many historical days match this exact situation (n=5 is OK, n=20+ is solid); 67% UP doesn't mean "67% chance," it means "in 12 of 18 comparable sessions, the next window closed up"; a LOW-CONFIDENCE badge fires at n<5; and phase context matters most — a 67% pattern in war-phase means nothing in a post-ceasefire phase. Just as prominent is what the card insists it is not: not a prediction ("the future is not the past"), not a position size ("you'd still need stops and targets"), not a complete signal ("combine with current news to know which phase you're in today"). The usage flow is a six-step walk: identify the current phase → find today's day-type → look up the Decision Helper → cross-check the window's historical mix → apply cross-factor overlays (EIA Wednesday, Monday, OPEC day) → apply your own risk management. The distilled form of every pattern is a sentence like: IF it's 8pm IST, the day has been an all-day trend, and we're in Phase 1 (war) — THEN historically the mcx_tail window closed UP 67% of the time. Decision-helper cards like these are the most actionable artifact in the project — the point where Dirichlet posteriors and FDR corrections become "if today looks like that, lean long."

Competency mapping: user-first information design (the end consumer of six months of machinery is one trader at one screen — the card is written for them, with its own limits stated on its face); honest communication (what-it-is-NOT sections that most projects bury); and the FDE skill of translation — converting statistical output into literal, decision-ready language without overselling it.
