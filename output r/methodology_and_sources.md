# methodology_and_sources

- requested_date_range: 2026-06-02 to 2026-06-04
- instruments: WTI crude futures (CL root), Brent crude futures (BZ root)
- market_bar_source: Yahoo Finance via yfinance
- reference_sources: FRED, EIA
- timezone_logic: all exported timestamps normalized to Asia/Kolkata
- trade_date_logic: session day anchored at 03:30 IST so post-midnight IST bars remain on the prior session date
- roll_logic: no verified contract-level roll metadata available from Yahoo fallback; front-symbol continuity only
- bar_construction: best-available Yahoo bars used by target bucket in priority order 1m -> 5m -> 15m -> 60m, with Yahoo daily endpoint fallback only where no intraday bucket coverage was available for the trade date; output rows carry source_resolution_used/source_resolution_minutes labels
- missing_bar_policy: no synthetic fill rows
- notes: news/rhetoric/event files require separate verified news ingestion

## file_summary
- wti_spot_daily_reference_ist.csv | rows=0 | coverage= ->  | note=FRED WTI spot reference
- brent_spot_daily_reference_ist.csv | rows=0 | coverage= ->  | note=FRED/EIA Brent spot reference
- mcx_spot_daily_reference_ist.csv | rows=0 | coverage= ->  | note=Placeholder MCX spot daily reference
- usd_inr_daily_ist.csv | rows=0 | coverage= ->  | note=Optional USD/INR reference
- wti_5m_ist.csv | rows=792 | coverage=2026-06-02 -> 2026-06-04 | note=Best-available bucket-level build for 5m
- wti_15m_ist.csv | rows=264 | coverage=2026-06-02 -> 2026-06-04 | note=Best-available bucket-level build for 15m
- wti_60m_ist.csv | rows=69 | coverage=2026-06-02 -> 2026-06-04 | note=Best-available bucket-level build for 60m
- wti_daily_ist.csv | rows=3 | coverage=2026-06-02 -> 2026-06-04 | note=Bucket-level intraday daily with 1d fallback only for uncovered dates
- wti_session_windows_summary.csv | rows=29 | coverage=2026-06-02 -> 2026-06-04 | note=Derived from best-available intraday bars
- brent_5m_ist.csv | rows=775 | coverage=2026-06-02 -> 2026-06-04 | note=Best-available bucket-level build for 5m
- brent_15m_ist.csv | rows=264 | coverage=2026-06-02 -> 2026-06-04 | note=Best-available bucket-level build for 15m
- brent_60m_ist.csv | rows=69 | coverage=2026-06-02 -> 2026-06-04 | note=Best-available bucket-level build for 60m
- brent_daily_ist.csv | rows=3 | coverage=2026-06-02 -> 2026-06-04 | note=Bucket-level intraday daily with 1d fallback only for uncovered dates
- brent_session_windows_summary.csv | rows=29 | coverage=2026-06-02 -> 2026-06-04 | note=Derived from best-available intraday bars
- daily_master_summary.csv | rows=3 | coverage=2026-06-02 -> 2026-06-04 | note=Cross-market daily merge
- day_type_labels.csv | rows=3 | coverage=2026-06-02 -> 2026-06-04 | note=Auto labels with optional manual overrides
- deviation_pattern_labels.csv | rows=3 | coverage=2026-06-02 -> 2026-06-04 | note=Prior-5-day deviation labels
- day_window_behavior_matrix.csv | rows=3 | coverage=2026-06-02 -> 2026-06-04 | note=Window behavior summary
- archetype_similarity_features.csv | rows=3 | coverage=2026-06-02 -> 2026-06-04 | note=Clustering feature layer
- scenario_backtest_features.csv | rows=6 | coverage=2026-06-02 -> 2026-06-04 | note=Scenario metrics
- intraday_excursions_combined.csv | rows=58 | coverage=2026-06-02 -> 2026-06-04 | note=Excursion metrics
- contract_roll_log.csv | rows=0 | coverage= ->  | note=Yahoo/Upstox path: no verified contract-level roll metadata
- news_events_master.csv | rows=0 | coverage= ->  | note=Header-only unless verified news input supplied

## coverage_notes
- WTI: source=yahoo | candidate_rows=5072 | resolution_mix={'1m': 3949, '5m': 792, '15m': 264, '60m': 67}
- BRENT: source=yahoo | candidate_rows=4305 | resolution_mix={'1m': 3199, '5m': 775, '15m': 264, '60m': 67}