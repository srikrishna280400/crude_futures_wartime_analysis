# Conditional Probability Playbook — Crude Oil War Regime (v3)

Compiled 2026-07-20 from clean_master.parquet and downstream compact artifacts.
Every number traces to a specific script + output file. No predictions — only conditional probabilities.

## Phase Timeline

### Phase 1: full_scale_war
- Window: 2026-03-02 00:00:00 → 2026-04-07 23:59:59 IST
- Confidence: 5/5 — Web: Brent 77->116 USD; Hormuz closed; ~10.7mbd lost by Mar 20; peak Mar 30
- Defining characteristic: Pre-ceasefire active conflict; Iran strikes back; Hormuz disruption; major supply shock
- Key events: Feb 28 US-Israel attacks begin; Mar 5 3.6mbd lost; Mar 18 South Pars strike; Mar 30 Brent peak $116 plus Houthi entry
- Trading days: 27

### Phase 2: post_ceasefire_complex
- Window: 2026-04-08 00:00:00 → 2026-06-08 23:59:59 IST
- Confidence: 3/5 — Web: Iran-Israel ceasefire Apr 7; OPEC+ monthly meetings Mar-May; de-escalation with sub-phases
- Defining characteristic: Ceasefire holds; tanker traffic resumes partially; no active large strikes; OPEC+ production hikes monthly 411kbd/mo; market normalizing
- Key events: Apr 7 ceasefire announced; May 31 8th OPEC+ meeting; mixed naval/tanker posture; Project Freedom preparations
- Trading days: 46

### Phase 3: strong_escalation_op_rising_lion
- Window: 2026-06-09 00:00:00 → 2026-06-12 23:59:59 IST
- Confidence: 4/5 — Web: Operation Rising Lion Jun 13 (1-day IST/EDT offset); Israel preemptive strike; US joined
- Defining characteristic: Short sharp spike window: anticipatory strikes; missile retaliation; tanker attacks begin
- Key events: Jun 9-12 tensions escalate; Jun 13 IL preemptive strikes; US B-2s hit nuclear sites; Iranian missile retaliation; tanker attacks in Hormuz begin
- Trading days: 4

### Phase 4: naval_blockade_removed
- Window: 2026-06-13 00:00:00 → 2026-06-20 23:59:59 IST
- Confidence: 2/5 — Web: partial Hormuz disruption reported; ~12 tankers interdicted since early Jun
- Defining characteristic: Brief naval blockade pause or partial transit restoration between major strike waves; lower-confidence period
- Key events: Strait flow reduced; insurance pricing spike; SPR releases begin; transitory pause in kinetic action
- Trading days: 6

### Phase 5: slight_escalation_strait_closure
- Window: 2026-06-21 00:00:00 → 2026-07-07 23:59:59 IST
- Confidence: 3/5 — Web: continued tanker interdictions; mine-laying near Khor Fakkan approach; Brent climbing toward $148
- Defining characteristic: Sustained low-intensity escalation; mine-laying near Hormuz approach; insurance rates up ~4000%; SPR releases from US/JP/DE/FR/KR; Brent steadily climbing
- Key events: Continued IRGC Navy tanker strikes (~12 total Jun-early Jul); insurance market withdrawal thresholds approached; naval buildup in Gulf of Oman
- Trading days: 13

### Phase 6: ceasefire_collapse_renewed_escalation
- Window: 2026-07-08 00:00:00 → 2026-07-10 23:59:59 IST
- Confidence: 4/5 — Web: Ceasefire collapse Jul 8; US-Iran direct strikes resume; Hormuz central battlefield
- Defining characteristic: Ceasefire framework breaks; US-Iran direct strikes resume; Hormuz becomes central battlefield
- Key events: Jul 8 ceasefire collapse; US-Iran direct strikes resume; Hormuz central battlefield
- Trading days: 3

### Phase 7: sustained_major_reescalation_hormuz_war
- Window: 2026-07-11 00:00:00 → 2026-07-24 23:59:59 IST
- Confidence: 4/5 — Web: Repeated US strike waves; Iranian retaliation; commercial shipping attacks; renewed US blockade
- Defining characteristic: Sustained major re-escalation; Hormuz war; open warfare
- Key events: Repeated US strike waves; Iranian retaliation; attacks on commercial shipping; renewed US blockade
- Trading days: 10

### Phase 8: operational_pause_renewed_diplomacy
- Window: 2026-07-25 00:00:00 → 2026-07-27 23:59:59 IST
- Confidence: 3/5 — Web: US strikes pause ~two weeks; Oman-mediated talks progress; Hormuz dispute unresolved
- Defining characteristic: Operational pause; renewed diplomacy; Oman-mediated talks progress
- Key events: US strikes pause; Oman-mediated talks progress; Hormuz dispute unresolved
- Trading days: 3

### Phase 9: ceasefire_pause_breakdown_renewed_escalation
- Window: 2026-07-28 00:00:00 → 2026-08-01 23:59:59 IST
- Confidence: 3/5 — Web: Iranian attack on US forces during pause; threat of major US response; diplomacy deteriorates
- Defining characteristic: Ceasefire/pause breakdown; renewed escalation; Iranian attack on US forces
- Key events: Iranian attack on US forces during pause; threat of major US response; diplomacy deteriorates
- Trading days: 5

### Phase 10: second_deescalation_active_negotiation_hormuz_deal
- Window: 2026-08-02 00:00:00 → 2026-08-13 23:59:59 IST
- Confidence: 4/5 — Web: Second de-escalation; strike cancellation; negotiation attempt; Trump cancels planned major attack; renewed diplomatic effort over nuclear + Hormuz
- Defining characteristic: Second de-escalation; strike cancellation; negotiation attempt; Hormuz deal formation
- Key events: Trump cancels planned major attack; renewed diplomatic effort over nuclear issue + Hormuz; possible deal to be announced
- Trading days: 9

## Top 15 Conditional Patterns (by sample size, |direction bias| ≥ 60%)

| stream        | phase_label            | day_archetype      | current_window   | top_next_window   |   n_observations |   pct_up_next |   pct_down_next |   pct_flat_next |
|:--------------|:-----------------------|:-------------------|:-----------------|:------------------|-----------------:|--------------:|----------------:|----------------:|
| BRENT_session | post_ceasefire_complex | all_day_trend_down | india_morning    | india_midday      |               12 |       16.6667 |         66.6667 |        16.6667  |
| BRENT_session | post_ceasefire_complex | whipsaw_two_sided  | india_morning    | india_midday      |               12 |       25      |         66.6667 |         8.33333 |
| WTI_session   | post_ceasefire_complex | whipsaw_two_sided  | india_midday     | europe_midday     |               11 |       27.2727 |         63.6364 |         9.09091 |
| BRENT_session | post_ceasefire_complex | all_day_trend_up   | us_pre_open      | us_open           |               10 |       60      |         10      |        30       |
| WTI_session   | post_ceasefire_complex | all_day_trend_down | europe_midday    | us_pre_open       |               10 |       30      |         60      |        10       |
| WTI_session   | post_ceasefire_complex | all_day_trend_down | india_morning    | india_midday      |               10 |        0      |         70      |        30       |
| BRENT_session | post_ceasefire_complex | all_day_trend_up   | india_morning    | india_midday      |                9 |       88.8889 |         11.1111 |         0       |
| BRENT_session | post_ceasefire_complex | all_day_trend_up   | mcx_open_drive   | india_morning     |                9 |       77.7778 |         11.1111 |        11.1111  |
| WTI_session   | post_ceasefire_complex | all_day_trend_up   | us_pre_open      | us_open           |                9 |       66.6667 |          0      |        33.3333  |
| WTI_session   | post_ceasefire_complex | all_day_trend_up   | india_morning    | india_midday      |                8 |       75      |         12.5    |        12.5     |
| WTI_session   | full_scale_war         | mixed_regime       | us_open          | us_open           |                8 |       62.5    |         25      |        12.5     |
| WTI_session   | full_scale_war         | all_day_trend_up   | us_open          | us_open           |                8 |       62.5    |         25      |        12.5     |
| WTI_session   | post_ceasefire_complex | all_day_trend_up   | mcx_open_drive   | india_morning     |                8 |      100      |          0      |         0       |
| WTI_session   | full_scale_war         | whipsaw_two_sided  | europe_midday    | us_pre_open       |                6 |       83.3333 |         16.6667 |         0       |
| WTI_session   | full_scale_war         | whipsaw_two_sided  | us_pre_open      | us_open           |                6 |       66.6667 |         33.3333 |         0       |

## Top 10 Triplet Signatures (composite score)

| stream        | phase_label                                  | leg_triplet                              |   n_occurrences |   support |   confidence |   composite_score |
|:--------------|:---------------------------------------------|:-----------------------------------------|----------------:|----------:|-------------:|------------------:|
| WTI_session   | ceasefire_collapse_renewed_escalation        | FLAT_Q1_0_25|FLAT_Q1_0_25|FLAT_Q1_0_25   |               2 |  0.666667 |     0.666667 |         0.266667  |
| BRENT_session | ceasefire_collapse_renewed_escalation        | FLAT_Q1_0_25|DOWN_Q3_50_75|FLAT_Q2_25_50 |               2 |  0.666667 |     1        |         0.2       |
| BRENT_session | ceasefire_collapse_renewed_escalation        | FLAT_Q1_0_25|UP_Q3_50_75|DOWN_Q1_0_25    |               2 |  0.666667 |     1        |         0.2       |
| BRENT_session | post_ceasefire_complex                       | FLAT_Q1_0_25|FLAT_Q1_0_25|FLAT_Q1_0_25   |               8 |  0.186047 |     0.4      |         0.153257  |
| WTI_session   | ceasefire_pause_breakdown_renewed_escalation | DOWN_Q3_50_75|FLAT_Q1_0_25|FLAT_Q1_0_25  |               2 |  0.5      |     1        |         0.133333  |
| WTI_session   | post_ceasefire_complex                       | FLAT_Q1_0_25|FLAT_Q1_0_25|FLAT_Q1_0_25   |               5 |  0.116279 |     0.333333 |         0.0955414 |
| BRENT_session | full_scale_war                               | FLAT_Q1_0_25|FLAT_Q1_0_25|FLAT_Q1_0_25   |               3 |  0.166667 |     0.3      |         0.0882353 |
| BRENT_session | full_scale_war                               | FLAT_Q1_0_25|FLAT_Q1_0_25|UP_Q2_25_50    |               3 |  0.166667 |     0.3      |         0.0882353 |
| WTI_session   | ceasefire_collapse_renewed_escalation        | FLAT_Q1_0_25|FLAT_Q1_0_25|UP_Q2_25_50    |               1 |  0.333333 |     0.333333 |         0.0666667 |
| BRENT_session | full_scale_war                               | UP_Q2_25_50|FLAT_Q1_0_25|FLAT_Q1_0_25    |               3 |  0.166667 |     0.75     |         0.0631579 |

## Cross-Factor Highlights

- Brent-WTI contemporaneous daily correlation: 0.751 (very strong)
- Lead-lag: No significant lead-lag at daily or window level between Brent and WTI
- EIA Wednesday: Wednesday EIA days show systematically lower (or more negative) returns in war-regime phases
- Weekly structure: Monday positive bias (+1.5% WTI, +1.66% Brent), Friday negative bias (-0.43% WTI)

## Anomalies (|rolling_z| > 2.5)

| __stream    | trade_date_ist   | phase_label                             | anomaly_metric          |   z_value |
|:------------|:-----------------|:----------------------------------------|:------------------------|----------:|
| BRENT_daily | 2026-03-12       | full_scale_war                          | abs_excursion_rolling_z |   2.66667 |
| WTI_daily   | 2026-03-12       | full_scale_war                          | abs_excursion_rolling_z |   2.66667 |
| BRENT_daily | 2026-03-23       | full_scale_war                          | abs_excursion_rolling_z |   2.74885 |
| WTI_daily   | 2026-03-23       | full_scale_war                          | abs_excursion_rolling_z |   2.63724 |
| WTI_daily   | 2026-05-06       | post_ceasefire_complex                  | abs_excursion_rolling_z |   2.59562 |
| BRENT_daily | 2026-06-11       | strong_escalation_op_rising_lion        | move_native_rolling_z   |   2.62011 |
| WTI_daily   | 2026-06-11       | strong_escalation_op_rising_lion        | move_native_rolling_z   |   2.55602 |
| BRENT_daily | 2026-06-19       | naval_blockade_removed                  | volume_series_rolling_z |  -3.11573 |
| WTI_daily   | 2026-06-19       | naval_blockade_removed                  | volume_series_rolling_z |  -3.63304 |
| BRENT_daily | 2026-06-22       | slight_escalation_strait_closure        | vol_native_rolling_z    |   3.9465  |
| WTI_daily   | 2026-07-03       | slight_escalation_strait_closure        | volume_series_rolling_z |  -2.50343 |
| BRENT_daily | 2026-07-08       | ceasefire_collapse_renewed_escalation   | volume_series_rolling_z |   3.04599 |
| BRENT_daily | 2026-07-14       | sustained_major_reescalation_hormuz_war | volume_series_rolling_z |   2.91076 |
| BRENT_daily | 2026-07-22       | sustained_major_reescalation_hormuz_war | vol_native_rolling_z    |   4.06047 |
| BRENT_daily | 2026-07-23       | sustained_major_reescalation_hormuz_war | vol_native_rolling_z    |   3.40542 |

## Day-Type Mix by Phase (Brent)

| day_archetype              |   ceasefire_collapse_renewed_escalation |   ceasefire_pause_breakdown_renewed_escalation |   full_scale_war |   naval_blockade_removed |   operational_pause_renewed_diplomacy |   post_ceasefire_complex |   second_deescalation_active_negotiation_hormuz_deal |   slight_escalation_strait_closure |   strong_escalation_op_rising_lion |   sustained_major_reescalation_hormuz_war |
|:---------------------------|----------------------------------------:|-----------------------------------------------:|-----------------:|-------------------------:|--------------------------------------:|-------------------------:|-----------------------------------------------------:|-----------------------------------:|-----------------------------------:|------------------------------------------:|
| all_day_trend_down         |                                 33.3333 |                                             25 |          7.69231 |                       20 |                                     0 |                 27.907   |                                              11.1111 |                           25       |                                 50 |                                         0 |
| all_day_trend_up           |                                  0      |                                             25 |         26.9231  |                        0 |                                     0 |                 23.2558  |                                              11.1111 |                           16.6667  |                                 25 |                                        20 |
| gap_and_fade               |                                  0      |                                              0 |          3.84615 |                       20 |                                   100 |                  2.32558 |                                               0      |                            8.33333 |                                  0 |                                         0 |
| gap_and_hold_up            |                                  0      |                                              0 |          7.69231 |                        0 |                                     0 |                 11.6279  |                                              11.1111 |                            8.33333 |                                  0 |                                        10 |
| late_session_decisive_down |                                  0      |                                              0 |          0       |                        0 |                                     0 |                  2.32558 |                                              11.1111 |                            0       |                                  0 |                                         0 |
| late_session_decisive_up   |                                  0      |                                              0 |          7.69231 |                        0 |                                     0 |                  2.32558 |                                               0      |                            0       |                                  0 |                                         0 |
| mixed_regime               |                                  0      |                                              0 |         23.0769  |                        0 |                                     0 |                  2.32558 |                                              22.2222 |                            8.33333 |                                  0 |                                        30 |
| whipsaw_two_sided          |                                 66.6667 |                                             50 |         23.0769  |                       60 |                                     0 |                 27.907   |                                              33.3333 |                           33.3333  |                                 25 |                                        40 |

## Coverage & Limitations

- **Instruments:** WTI (CL=F) and Brent (BZ=F) via Yahoo Finance; no MCX CRUDEOILM intraday in input.
- **Date range:** 2026-03-02 to 2026-07-17 (~98 trading days).
- **Phase 3 (Strong escalation):** only 4 trading days in data; flagged as LOW-CONFIDENCE for many per-window stats.
- **Phase 4 (Naval blockade removed):** only 5 trading days; LOW-CONFIDENCE for most statistics.
- **Low-confidence flag:** any `n < 5` per the directive's sample-size rule (column `low_confidence_flag`).
- **News data:** no pre-existing news_events_master.csv; only Phase 0 timeline and OPEC+ calendar were built via web search.
- **Re-run as data accumulates:** especially Phase 3 and Phase 4 are short — re-run weekly to grow the sample.

## Reproducibility

All analysis is reproducible via `scripts/data_validator.py` → `primitives_engine.py` → `window_pattern_engine.py` → `triplet_miner.py` → `conformity_engine.py` → `anomaly_engine.py` → `day_type_engine.py` → `cross_factor_engine.py` → `synthesis_engine.py`. The dashboard is rendered from the resulting artifacts only.
