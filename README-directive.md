# CRUDE OIL WAR-REGIME PATTERN-MINING DIRECTIVE (v3)
### Code-as-Processor / Agent-as-Orchestrator Edition
### For execution in an E2B sandbox (or equivalent code-execution environment) with MCP tool access, against a 65,000+ row dataset

---

## 0. MISSION AND NON-GOALS

**Mission:** Mine the provided historical MCX CRUDEOILM / WTI / Brent price data (65k+ rows across daily and intraday granularity) across the full conflict timeline to surface **concrete, repeatable, statistically-supported patterns** in intraday time-window behavior, sequential move structure, and regime-conditional dynamics — so future trading decisions can be informed by *historically grounded conditional probabilities*, not narrative or gut feel.

**Explicit non-goal:** You are not forecasting where price goes next. You are building a **pattern library with frequencies, confidence levels, and conditions of applicability** — a lookup table, not a prophecy. Any output that reads like a prediction rather than a conditional-probability lookup has failed the brief.

**Standing instruction:** You are operating as a senior quantitative researcher would — rigorous, skeptical of your own findings, allergic to small-sample overconfidence, and explicit about uncertainty. At 65k+ rows, you are **also operating as the engineer who builds the pipeline that makes that rigor possible** — this is not optional infrastructure, it is the only way the analysis in this directive can be done correctly at this scale. Precision and honesty about *what the data does and doesn't support* matters more than the volume of patterns you report or the cleverness of the pipeline.

---

## 1. GROUND RULES (non-negotiable, apply to every step below)

1. **No hallucination.** Every number, date, price, and news reference must trace to the provided data files, the reference folder, a script's actual computed output, or a live web search you actually performed. If you cannot verify something, say so and mark it `UNVERIFIED`.
2. **No silent interpolation.** Missing intraday data for a window/day is marked `DATA_GAP` in the pipeline and excluded from denominators programmatically — never estimated or backfilled by the script or by you.
3. **Sample-size discipline is mandatory and must be computed, not eyeballed.** Every stated frequency or percentage must carry its raw count (`n = X of Y qualifying rows/days`), produced by the script's own groupby/count logic. Any finding with `n < 5` is programmatically flagged `LOW-CONFIDENCE` in the output table itself — this flag must exist as a column in the data, not just as prose you add afterward.
4. **The ≥3-repetition rule.** Nothing is called a "pattern" unless the pipeline's own counting shows it recurring in at least 3 independent, non-adjacent instances. Enforce this as a filter in code, not as a manual judgment call after the fact.
5. **Multiple-comparisons awareness.** You will be testing many window × phase × day-type combinations. Where your script runs many parallel statistical tests, note the total number of comparisons made and flag borderline findings accordingly, rather than reporting every marginally-interesting slice as a discovery.
6. **Regime-relative, not absolute, thresholds — computed programmatically.** Magnitude classification must be computed as a percentile within that phase's own volatility distribution (via `groupby(phase_id)` + `qcut`/`rank(pct=True)`), never as a hardcoded global percentage. This calculation must live in the script, auditable and reproducible — not asserted in the write-up.
7. **Three epistemic tiers, tagged explicitly:** (a) directly computed from the price data by your scripts, (b) informed by quant/trading theory from the reference folder or external literature, (c) your own inference connecting the two. Every claim in the final playbook must carry one of these tags.
8. **Manipulation-pattern findings are heuristic by construction.** Frame every Step 7 finding as "anomalous relative to conventional trading math (z-score computed as X), candidate mechanism Y, recurred N times (see anomalies.csv)" — never as a factual claim of intent.
9. **Token efficiency is a data-integrity requirement, not a cost-saving nicety.** At 65k+ rows, attempting to reason over raw rows in-context is not just expensive — it produces worse, less rigorous analysis than a properly engineered pipeline would. Treat every violation of the execution architecture below (Section 2) as a correctness risk, not merely an efficiency one.
10. **Input data scope — price/volume only, no news fields.** The provided files contain **only price/volume/derived-price data** (OHLCV across MCX CRUDEOILM, WTI, Brent — daily and intraday). No headlines, event labels, news summaries, or pre-tagged geopolitical annotations exist anywhere in the dataset. Do not assume, join against, or reference any `news_events`, `headline`, or similar field as if it were part of the input files — it isn't. The only two legitimate sources of geopolitical/event context in this entire directive are: (a) the trader's 6-phase timeline hypothesis (Step 0), and (b) live web searches you perform yourself at the specific points this directive calls for one (Step 0 phase validation, Step 7 anomaly correlation, Step 9 OPEC+ calendar). Every pattern, frequency, and probability elsewhere in this directive must be derivable from price/volume behavior alone. Also the spot prices for both crude wti and brent for every single day since the war broke out isn't provided in the input csv files but in some gaps of dates, so feel free to web search it for every single day, at the start of day and close/end of day...in whatever form, to whatever extent your analysis of finding whatever possible patterns to capitalize on, requires it.

---

## 2. EXECUTION ARCHITECTURE — "COMPUTE-LOCAL, REASON-GLOBAL" (mandatory paradigm)

This section governs *how* every step from Section 3 onward must be carried out. It is not optional scaffolding — it is the mechanism that makes Section 1's rigor achievable at this row count.

### 2.1 The pipeline shape

```
[Raw Data: 65k+ rows]
        │
        ▼
[E2B Python Engine — MAP]
  • load, clean, dtype-optimize
  • timezone-normalize to IST
  • classify time windows, phases, day-types
  • compute primitives (returns, thresholds, tiers)
  • run transition-matrix / triplet-mining / z-score anomaly math
        │
        ▼
[Structured Parquet / compact CSV / JSON — intermediate + final artifacts]
        │
        ▼
[Agent — REDUCE: targeted, coordinate-based reads of ONLY the compact outputs]
        │
        ▼
[Final Playbook — written from the compact artifacts, never from raw rows]
```

### 2.2 Standing execution rules

1. **Never read raw data rows or verbose CSV dumps directly into your reasoning context.** All parsing, joining, timezone conversion, and statistics happen in Python inside the sandbox.
2. **Every derived table, matrix, or catalog must be written to a file** (`.parquet` for intermediate/large data, `.csv`/`.json` for final compact outputs meant for your own later reading) before you inspect it.
4. Reading the py code file is absolutely necessary in understanding the rows, columns data and all the other entries and context surrounding it within the csv files. Although some of the fields/columns that were generated in the csv...from running the code were intentionally deleted/discarded in the csv files..since they were too limited/vague/unreliable in their scope to be built upon and extrapolated into patterns, insights with probabilities. But you must absolutely make total use to the fullest extent possible of all the entries and data that are present in the existing csv files
3. **When you do inspect an output, use targeted reads only** — specific line ranges, `.head()`/`.describe()` on already-reduced tables, or explicit top-N slices (e.g., "top 30 ranked triplets") — never a full dump of a large file.
4. **Prune only genuinely redundant/constant columns programmatically**, and only after confirming they are constant across the relevant subset (e.g., `source_timezone`, `currency_native` if invariant within an instrument's file, `instrument_name`, `market`). **Never prune, merge away, or silently drop:** `data_quality_flags`, any timestamp field, price fields (OHLCV), `rolled_flag`/`contract_symbol`, or any field a later step depends on. If uncertain whether a column is safe to drop, keep it and flag it as "candidate for pruning, unconfirmed" rather than dropping it.
5. **Vectorize, don't loop, at this row count.** Time-window classification, return calculations, percentile thresholding, and transition-matrix construction should use pandas/numpy vectorized operations (`groupby`, `transform`, `shift`, `pd.cut`/`qcut`, `crosstab`) — not row-by-row Python loops.
6. **Use the right library for the job rather than reinventing it:** `pandas`/`numpy` for core transforms; `pyarrow` for parquet I/O; `scipy.stats` for z-scores and distributional tests; `statsmodels` for autocorrelation/Markov-style transition analysis where useful; a sequential-pattern-mining approach (either a custom sliding-window enumeration — trivial at this scale — or `mlxtend`/`prefixspan`-style tooling reframed with order-encoded tokens) for Step 5; `ruptures` (or an equivalent changepoint-detection method) as an optional cross-check on the Step 0 phase boundaries, run *in addition to* the news-based dating, not instead of it; `matplotlib`/`plotly` only if a visual artifact would materially help the final synthesis.
7. **Rate limits and resilience:** if any tool call (web search or otherwise) hits a 429/throttling response, apply exponential backoff (2s, 4s, 8s) and retry before treating it as a failure.

### 2.3 The script library

Build the analysis as a small library of scripts in the workspace, each mapped to specific Directive steps — not one monolithic script:

| Script | Directive steps covered | Key output artifact(s) |
|---|---|---|
| `data_validator.py` | Step 0 (phase table), Step 1 (ingestion, IST conversion, window/phase/day-type tagging, column pruning) | `phase_lookup.csv`, `clean_master.parquet` |
| `primitives_engine.py` | Step 2 (returns, regime-relative thresholds, magnitude tiers) | `primitives.parquet` |
| `window_pattern_engine.py` | Step 3, Step 4 (frequency tables, transition matrices, magnitude distributions) | `transition_matrices/*.csv`, `window_stats.csv` |
| `triplet_miner.py` | Step 5 (sequential triplet mining, composite scoring) | `triplets_catalog.json` (top-N ranked) |
| `conformity_engine.py` | Step 6 (trading-math conformity vs. deviation, referencing reference-folder concepts) | `conformity_stats.csv`, `concept_citations.md` |
| `anomaly_engine.py` | Step 7 (z-score anomaly detection, manipulation-pattern candidates) | `anomalies.csv` (flagged dates only) |
| `day_type_engine.py` | Step 8 (day-type bucket classification, phase cross-tab) | `day_types.csv` |
| `cross_factor_engine.py` | Step 9 (EIA/weekly/OPEC+/expiry/lead-lag overlays) | `cross_factor_stats.csv`, `opec_calendar.csv` |
| `synthesis_engine.py` | Step 11 (compiles all prior compact outputs into the final lookup table) | `playbook.json`, `playbook_summary.csv` |
| `viz_engine.py` *(optional)* | Any step where a static chart materially aids interpretation | `.png` charts |
| `dashboard_engine.py` | **Required.** Reads every compact output artifact above and renders the full analysis as one interactive page (see Section 2.6) | `dashboard.html` |

### 2.4 The Approval Gate (QA Director checkpoint)

After `data_validator.py` produces `phase_lookup.csv` and `clean_master.parquet`, **stop and present, before running any further mining script**:
- The script itself (or a clear summary of its logic).
- Row counts per phase, per window, and per day-type — compact summary stats only, not raw rows.
- The exact bucketing/threshold logic chosen (e.g., how phase boundaries were finalized, how the regime-relative percentile thresholds were computed).

This is a genuine checkpoint, not a formality: if the trader disagrees with a bucketing choice, the parameters should be adjustable **before** they propagate through 65k+ rows of downstream analysis. Do not proceed past this gate silently.

### 2.5 What you read back into context

At every later step, you read only: compact CSV/JSON summary tables, top-N slices of ranked catalogs, targeted line-range excerpts, and `.describe()`-level statistics — never the full `clean_master.parquet`, never a raw file dump. If you find yourself about to paste more than a screen's worth of raw rows into your own reasoning, stop and write a script to reduce it first.

### 2.6 Interactive Dashboard Deliverable (required, not optional)

The final output of this entire directive is read by a human making trading decisions, not just consumed as text. Alongside every JSON/CSV/parquet/script artifact, `dashboard_engine.py` must build a **single self-contained HTML page** (`dashboard.html` — opens directly in a browser, no server required) that visually presents every conclusion from Steps 0–11. It must be a low-med fidelity frontend dashboard site with not many fancy animations, renderings, stylings, etc...don't burn through too many tokens for building this. I want it to be presentable but also only have the essentials.

- **Built exclusively from the already-produced compact output files** (`phase_lookup.csv`, `window_stats.csv`, `transition_matrices/*.csv`, `triplets_catalog.json`, `conformity_stats.csv`, `anomalies.csv`, `day_types.csv`, `cross_factor_stats.csv`, `playbook.json`) — never from `clean_master.parquet` or raw rows. If the dashboard script needs data that isn't in one of these compact files, that's a signal a prior engine's output was incomplete, not a reason to reach back into raw data.
- **Navigation:** tabs (or an equivalent toggle/category nav) for at least: Phase Timeline, Time-Window Frequency & Transition Matrices, Magnitude Distributions, Triplet Pattern Catalog, Trading-Math Conformity vs. Anomaly, Manipulation/Anomaly Patterns, Day-Type Buckets, Cross-Factor Overlays, and the final Synthesis Playbook.
- **Global filters/toggles** that apply across tabs: phase selector, time-window selector, and a confidence-level toggle that visibly greys out / hides `LOW-CONFIDENCE` (`n < 5`) findings rather than presenting them with the same visual weight as well-supported ones.
- **Every visualized number carries its `n` and confidence tag on hover or inline** — the dashboard must not lose the sample-size discipline from Section 1 just because it's now a chart instead of a table. A finding that's flagged low-confidence in the CSV must still read as low-confidence on the page.
- Use lightweight, CDN-loaded or inlined charting (e.g., Plotly.js or Chart.js) and plain HTML/CSS/JS — no build step, no framework installation required to view it.
- This is a rendering layer over already-computed truth, not a new analysis step — it must not introduce numbers that don't trace back to one of the compact files it reads.

---

## 3. STEP 0 — VALIDATE AND FORMALIZE THE PHASE/REGIME TIMELINE

The phase list below is a **working hypothesis, not verified ground truth**. Audit and formalize it before any pattern mining:

**Working hypothesis (to validate, not assume):**
- Phase 1 (Mar 2-Apr 7): full-scale war, 27 days
- Phase 2 (Apr 8-Jun 8): post-ceasefire complex, 46 days
- Phase 3 (Jun 9-12): strong escalation Op Rising Lion, 4 days
- Phase 4 (Jun 13-20): naval blockade removed, 6 days
- Phase 5 (Jun 21-Jul 7): slight escalation Strait closure, 13 days
- Phase 6 (Jul 8–10): Ceasefire collapse / renewed escalation, June framework effectively breaks; U.S.–Iran direct strikes resume; Hormuz becomes central battlefield
- Phase 7 (Jul 11–24): Sustained major re-escalation / Hormuz war, Repeated U.S. strike waves, Iranian retaliation, attacks on commercial shipping, renewed U.S. blockade; essentially open warfare
- Phase 8 (Jul 25–27): Operational pause / renewed diplomacy, U.S. strikes pause after ~two weeks; Oman-mediated talks make progress, but Hormuz dispute remains unresolved
- Phase 9 (Jul 28–Aug 1): Ceasefire/pause breakdown — renewed escalation, Iranian attack on U.S. forces during the pause; threat of another major U.S. response; diplomacy deteriorates
P10 (Aug 2–Present): Second De-escalation / Active Negotiation & Hormuz Deal Formation, Second de-escalation / strike cancellation / negotiation attempt, Trump cancels planned major attack; renewed diplomatic effort over nuclear issue + Hormuz, possible deal to be announced today i.e. (06/08/2026)

**Analytical tasks:**
- Reconstruct the actual regime timeline with exact IST cutover timestamps via live web search only — no news-event file exists in the input data (see Ground Rule 10); the only pre-existing structure you have is the 6-phase hypothesis itself.
- Disambiguate phase 2 specifically — determine whether "ceasefire," "naval blockade," "Project Freedom," and "slight escalation" were sequential or overlapping, and split accordingly if evidence supports it.
- Produce a **Phase Ground-Truth Table**: `phase_id, phase_label, start_datetime_ist, end_datetime_ist, source(s), confidence_1_to_5, defining_characteristic, key_events`.
- Flag any phase too short to support standalone intraday statistics; report it as a case study rather than force it into "pattern" status, or propose a clearly-labeled, lower-confidence merge with an adjacent similar-character phase.

**Execution method:**
- Do the narrative/news-based dating first (this step is inherently research, not pure computation).
- Then, as a **quantitative cross-check**, run a changepoint-detection pass (e.g., `ruptures`) over the daily return/volatility series to see whether statistically-detected regime breaks align with the news-based boundaries. Report agreement/disagreement explicitly — don't silently prefer one over the other.
- Save the finalized table as `phase_lookup.csv`. All downstream scripts join against this file (e.g., `pd.merge_asof`) to tag every row with `phase_id` — phase tagging of 65k+ rows must happen via this join, not via manual date-range logic repeated in every script.

---

## 4. STEP 1 — DATA INGESTION, NORMALIZATION, AND TIME-WINDOW RECLASSIFICATION

- Inventory every data file actually present (MCX CRUDEOILM, WTI, Brent — daily and intraday) and the reference folder. List what exists before doing anything else.
- **Discard any pre-existing `session_window` labels in the source files.** Recompute every row's time window purely from its raw timestamp, converted to IST, against these buckets:

| Window ID | IST Range |
|---|---|
| `global_reopen_pre_mcx` | 03:30–09:00 |
| `mcx_open_drive` | 09:00–10:30 |
| `india_morning` | 10:30–12:30 |
| `india_midday` | 12:30–15:30 |
| `europe_midday` | 15:30–18:00 |
| `us_pre_open` | 18:00–20:00 |
| `us_open` | 20:00–23:00 |
| `mcx_tail` | 23:00–00:00 |
| `us_late` | 00:00–01:30 |

- The **01:30–03:30 IST gap** corresponds to the CME/Globex daily settlement halt — confirm against the actual exchange calendar and document; don't misattribute boundary rows.
- Tag every day with: `phase_id` (via join to `phase_lookup.csv`), `weekday`, `is_monday`, `is_friday`, `is_wednesday_eia_day`, `days_to_nearest_contract_expiry`, `within_7d_of_expiry_flag`.

**Execution method (`data_validator.py`):**
- Load all raw files, optimize dtypes (categorical for symbol/window/phase fields, datetime64 for timestamps, float32/float64 as appropriate for prices).
- Vectorized IST conversion via `tz_convert`/`zoneinfo`; vectorized window assignment via `pd.cut` or a searchsorted lookup against the table above — not row-wise `apply`.
- Programmatically identify and drop truly constant/redundant columns per the pruning rule in Section 2.2, logging exactly what was dropped and why, into a short `pruning_log.md`.
- Output `clean_master.parquet` (full lossless cleaned dataset) and `phase_lookup.csv`.
- **This is the Approval Gate checkpoint (Section 2.4) — pause here for confirmation before proceeding.**

---

## 5. STEP 2 — DEFINE THE ANALYTICAL PRIMITIVES

- **`window_return_pct`** = (close − open)/open × 100, per instrument, per window, per day.
- **Direction threshold — regime-relative, computed per phase**, not fixed globally. Document the exact formula (e.g., a fraction of that phase's median/IQR of absolute window returns).
- **Magnitude tiers** — percentile-based within each phase's own distribution (e.g., <25th, 25–50th, 50–75th, 75–90th, >90th), reported alongside the absolute % range each tier corresponds to in that phase.
- **"Leg"** = one window's classified direction + magnitude tier.
- **"Triplet pattern"** = three consecutive legs (specify whether window-adjacent or allowing gaps, and why).
- **ATR-equivalent** = rolling typical range measure per phase, for later normalized stop/target translation.

**Execution method (`primitives_engine.py`):**
- Compute `window_return_pct` via vectorized `groupby(['trade_date','symbol','window_id'])` aggregation.
- Compute regime-relative thresholds and percentile tiers via `groupby('phase_id')['window_return_pct'].transform(...)` — this must be a single reproducible function, not recomputed ad hoc in later scripts.
- Save `primitives.parquet`. State the exact formulas used in a short `definitions.md` companion file so every downstream number is auditable.

---

## 6. STEP 3 — TIME-WINDOW FREQUENCY & DIRECTION ANALYSIS

For every window × phase (and overall, separately labeled):
- Direction split (up/down/flat) with counts and %, `n` disclosed.
- Mean/median/dispersion of `window_return_pct` per direction.
- Which window most often sets the day's high; which most often sets the day's low — counts, by phase.
- A **transition/Markov-style matrix**: P(window i+1 direction | window i direction), per phase, with `n` on every cell.

**Execution method (`window_pattern_engine.py`):**
- Build transition counts via `groupby('phase_id')` + `shift(-1)` + `crosstab`, normalized to probabilities.
- Output one compact 9×9 (window × window, or direction-state × direction-state as specified) matrix per phase as `transition_matrices/{phase_id}.csv` — each costs a trivial amount of context to read despite representing the full 65k+ row computation behind it.
- Output `window_stats.csv` for the frequency/direction tables.
- Read back only these compact files, never the row-level data behind them.

---

## 7. STEP 4 — MAGNITUDE-BUCKETED DISTRIBUTION ANALYSIS

- For each window × phase, % of days in each magnitude tier, with `n`.
- Answer explicitly: "In phase X, window Y showed a [tier] move on [n/N = %] of days, most often [direction]."
- Cross-tabulate magnitude tier against `is_wednesday_eia_day`, `is_monday`, `is_friday`, `within_7d_of_expiry_flag`.

**Execution method:** extend `window_pattern_engine.py` — these are additional `groupby`/`crosstab` outputs appended to `window_stats.csv` or a sibling `magnitude_crosstabs.csv`. Same rule: compute in code, read back compact.

---

## 8. STEP 5 — SEQUENTIAL "TRIPLET" PATTERN MINING

- Treat as sequential pattern mining: support = frequency of occurrence, confidence = conditional likelihood of leg 3 given legs 1–2.
- Enumerate the most frequent triplet signatures, reporting support (% of qualifying days) and which window slots they occupy.
- Test whether the *same* signature recurs in **different window locations** on different days — report both window-anchored and window-agnostic frequencies.
- Rank by composite score = support × consistency × sample confidence.
- List actual dates behind each reported triplet.

**Execution method (`triplet_miner.py`):**
- At this row count, brute-force sliding-window enumeration of all 3-leg sequences is computationally trivial — no need for approximate mining. Encode each leg as a single categorical token (direction+magnitude), enumerate consecutive (and, separately, gapped) triplets, and count with `groupby`/`value_counts`.
- Compute support, confidence, and the composite score in the same script.
- Output `triplets_catalog.json`, ranked, with supporting dates attached to each entry.
- **Read only the top 30 (or however many are needed) via a targeted, coordinate-based read** — never the full catalog dump.

---

## 9. STEP 6 — TRADING-MATH CONFORMITY VS. ANOMALY CLASSIFICATION

- Inventory the reference folder's actual contents (lecture transcripts, notes) and list the specific frameworks/concepts present.
- For major moves, assess conformity to conventional frameworks — mean reversion, momentum, volatility clustering, session-overlap liquidity effects, microstructure/order-flow effects, VWAP-anchoring, backwardation/contango roll dynamics — citing the specific source (named file or external literature) each time.
- Mark external-literature-sourced concepts distinctly from dataset-observed findings.
- Quantify how often each window/phase conforms vs. deviates, with `n` and %.

**Execution method (`conformity_engine.py`):**
- Compute the quantitative conformity/deviation statistics (e.g., autocorrelation checks via `statsmodels`, mean-reversion half-life estimates) in code, output `conformity_stats.csv`.
- The qualitative concept-citation work (matching a statistical finding to a named framework from the reference folder) is inherently a reading/reasoning task — do this from the reference folder's actual text, not from memory, and log citations in `concept_citations.md`.

---

## 10. STEP 7 — MANIPULATION / ANOMALY PATTERN STUDY (heuristic)

- Define operationally what counts as anomalous here: a statistically significant divergence between news-implied direction/magnitude and realized price action; suppressed volatility in a window that historically expands sharply on comparable news; a late-window ramp/dump with no proportional catalyst; unusually fast full-reversion after a spike relative to the phase's typical mean-reversion half-life.
- Report which windows/phases each anomaly type clusters in, how often, and whether it clears the ≥3-repetition bar.
- Address explicitly: can these be capitalized on? If a suppressed-then-release or stop-hunt-then-reversal pattern recurs with adequate `n`, describe the conditional setup and historical follow-through — keeping the "manipulation" framing explicitly heuristic.

**Execution method (`anomaly_engine.py`):**
- Compute rolling z-scores of volatility and volume for every window across the full dataset via `scipy.stats.zscore` (or an equivalent rolling implementation), filter for `|z| > 2.5`.
- Output **only the flagged dates/timestamps** to `anomalies.csv` — this is the entire point of the z-score filter: it reduces 65k+ rows down to a small, tractable set of genuinely unusual sessions.
- Only for those flagged dates, run targeted web searches to correlate with geopolitical news (with exponential backoff on any rate-limit errors). Do not run news correlation on ordinary, non-anomalous sessions — that defeats the purpose of the filter.

---

## 11. STEP 8 — DAY-TYPE BUCKET CLASSIFICATION

- Classify whole days into repeatable archetypes (e.g., "gap-and-hold," "gap-and-fade," "late-session-decisive," "range-bound-all-day," "whipsaw-two-sided") with the same `n`/% rigor and representative dates.
- Cross-tabulate day-type mix against phase — does the *mix* of day-types shift meaningfully between phases? Quantify, don't assert.

**Execution method (`day_type_engine.py`):**
- Compute the day-level feature set (gap %, range %, close-location-in-range, session-return sequence) programmatically, then apply the rule-based archetype labels defined by your criteria.
- Optionally, run an unsupervised clustering pass (e.g., `KMeans` or hierarchical clustering on standardized day-level features) as a **cross-check** on whether the rule-based archetypes correspond to genuinely distinct clusters in the data, or whether the boundaries are fuzzier than the labels suggest — report this comparison honestly.
- Output `day_types.csv`.

---

## 12. STEP 9 — CROSS-FACTOR OVERLAYS

Test each as an independent conditioning variable, reporting effect size and `n`:

1. **Brent vs. WTI spot lead-lag** — run window/triplet/day-type analyses for both in parallel; test whether one instrument's window move tends to precede the other's, and whether the lead-lag direction shifts by phase or session.
2. **Wednesday EIA inventory day** — test `us_pre_open`/`us_open` distributions on EIA Wednesdays vs. non-Wednesdays, by phase.
3. **Weekly structure** — Monday `global_reopen_pre_mcx`/`mcx_open_drive` vs. other weekdays; Friday `mcx_tail`/`us_late` vs. other weekdays.
4. **OPEC+ meeting calendar** — identify actual meeting/announcement dates via web search, test for a distinct signature.
5. **Contract roll/expiry proximity** (`within_7d_of_expiry_flag`) — test whether windows/triplets behave differently in expiry week, for MCX specifically.

Report any factor combination that jointly produces a materially different pattern than any single factor alone.

**Execution method (`cross_factor_engine.py`):**
- All five tests are `groupby`/statistical-comparison operations on `clean_master.parquet` joined against small lookup tables (`opec_calendar.csv` built from targeted web searches, cached so it isn't re-fetched repeatedly).
- Output `cross_factor_stats.csv`. Read back compact summary tables only.

---

## 13. STEP 10 — OPEN-ENDED DISCOVERY

You are not limited to the structure above. If the pipeline surfaces a strong, repeatable (≥3 instances), well-evidenced pattern outside these categories, report it — held to the same standard: `n`, %, dates, regime-relative magnitude, and explicit (a)/(b)/(c) epistemic tagging. Do not pad the output with speculative observations that fail the repetition or sample-size bar; if you mention them at all, flag them as noted-but-unconfirmed. Any such discovery should still be produced via a script and a compact output file, not asserted from memory of having skimmed the data.

---

## 14. STEP 11 — SYNTHESIS: CONDITIONAL PROBABILITY PLAYBOOK

- A table keyed by `(phase or phase-type, day-type-so-far, current time window)` → historical distribution of what happened next (direction %, magnitude tier %, `n`), with specific historical analog dates.
- Translate historical MFE/MAE into **regime-normalized units** (% of that phase's typical window range, or ATR-equivalent multiples) rather than fixed price levels.
- Rank patterns in this playbook by composite confidence (sample size × consistency × recency-relevance to the current phase).

**Execution method (`synthesis_engine.py`):**
- This script's sole job is to join and compile the compact outputs of every prior engine (`window_stats.csv`, `triplets_catalog.json`, `anomalies.csv`, `day_types.csv`, `cross_factor_stats.csv`) into the final lookup structure — it should not need to touch `clean_master.parquet` directly at all, which is itself a good sanity check that the pipeline was properly compact at every prior stage.
- Output `playbook.json` (machine-readable) and `playbook_summary.csv` (human-scannable), then write the final narrative playbook from these two files only.

---

## 15. REQUIRED DELIVERABLES

**Narrative/analytical:**
1. Phase Ground-Truth Table (Step 0)
2. Definitions section (Step 2), referenced throughout
3. Time-window frequency/direction tables + transition matrices (Step 3)
4. Magnitude-bucketed distribution tables (Step 4)
5. Triplet pattern catalog, ranked, with supporting dates (Step 5)
6. Trading-math conformity/anomaly assessment with cited frameworks (Step 6)
7. Manipulation/anomaly pattern catalog, heuristic-labeled, with capitalization notes (Step 7)
8. Day-type bucket catalog cross-tabbed by phase (Step 8)
9. Cross-factor overlay findings (Step 9)
10. Open-ended discoveries, held to the same evidentiary bar (Step 10)
11. Conditional Probability Playbook (Step 11)
12. A **Coverage & Limitations** note: what data existed, what was missing, what was excluded for insufficient sample size, what should be re-run as more data accumulates.

**Engineering artifacts (must exist in the workspace, not just be described):**
13. The full script library (Section 2.3), each script individually inspectable.
14. All intermediate/final data artifacts: `clean_master.parquet`, `phase_lookup.csv`, `primitives.parquet`, `transition_matrices/*.csv`, `triplets_catalog.json`, `anomalies.csv`, `day_types.csv`, `cross_factor_stats.csv`, `playbook.json`, `playbook_summary.csv`, plus `pruning_log.md`, `definitions.md`, `concept_citations.md`.
15. **`dashboard.html`** — the interactive, tab/toggle-navigable single-page visualization of every conclusion in this directive (Section 2.6), generated programmatically from the artifacts in item 14, not hand-authored or mocked.

---

## 16. FINAL QA CHECKLIST (verify before delivering)

- [ ] Every % has an `n` next to it, computed in code.
- [ ] Every `n < 5` finding is programmatically flagged low-confidence.
- [ ] No fixed absolute-% thresholds anywhere magnitude was classified — all regime-relative, computed per phase.
- [ ] Every phase boundary used was sourced/dated, cross-checked against a changepoint-detection pass, not assumed from the original list.
- [ ] No claim states or implies a prediction of future price direction.
- [ ] Every "manipulation" framing is explicitly heuristic.
- [ ] Every borrowed quant concept cites its source (reference folder file or external search).
- [ ] Nothing labeled a "pattern" recurs fewer than 3 times.
- [ ] **No raw row-level data was ever pasted into the reasoning context** — every inspection was of a compact, pre-reduced artifact.
- [ ] The Approval Gate (Section 2.4) was actually honored — mining scripts did not run against the full dataset before the bucketing logic was reviewed.
- [ ] Every derived statistic traces to a specific script and output file, such that the entire analysis is reproducible end-to-end by rerunning the script library.
- [ ] No step assumed a news/headline/event field existed in the input data — all geopolitical context came only from the Step 0 phase hypothesis or live web search (Ground Rule 10).
- [ ] `dashboard.html` was generated from the actual compact output files (not placeholder/mock data), every tab/toggle in Section 2.6 is present, and every visualized finding still shows its `n`/confidence tag.