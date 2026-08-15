# Definitions — primitives_engine.py

## Formulas (per directive §5)

- `window_return_pct = (close - open) / open * 100`
- `window_range_pct = (high - low) / open * 100`
- `direction_threshold_pct = 0.5 * median(|window_return_pct|) per phase` — regime-relative noise floor
- `direction ∈ {UP, DOWN, FLAT}` per above threshold (FLAT when |return| ≤ threshold)
- `magnitude_tier ∈ {Q1_0_25, Q2_25_50, Q3_50_75, Q4_75_90, Q5_90_100}` from pd.qcut on |return| within (phase × window); UNCLASSIFIED if n<5
- `leg = direction + magnitude_tier` (categorical token for sequential mining)
- `phase_atr_pct = mean(window_range_pct) within phase` (ATR-equivalent)
- `magnitude_pctile = rank(|return|, pct=True) within phase × window`

## Aggregation level

- One row per `(trade_date, symbol, session_window)` in `*_session_windows_summary.csv`
- One row per 5m/15m/60m bar in `*_5m/15m/60m_ist.csv` (with leg = INTRADAY_BAR)
- One row per day in `*_daily_ist.csv` (with leg = DAILY_BAR)

## Source

Directive README v3 §5 (analytical primitives).
