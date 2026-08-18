# Pruning log — data_validator.py

Total input rows after vertical union: 83,827
Total input columns before pruning: 66
Columns pruned: 4

## Dropped columns
  - currency_native: only 1 unique non-null value(s) across 83827 rows → DROP
  - source_timezone: only 1 unique non-null value(s) across 83827 rows → DROP
  - reversal_strength_score_1_to_5: 100% NaN → DROP
  - follow_through_vs_gap_flag: 100% NaN → DROP

## Kept invariant candidates (must NOT drop):
- timestamp_ist, trade_date_ist (timestamps)
- open_native/high_native/low_native/close_native (OHLC)
- volume
- session_window_ist, phase_id, phase_label (downstream joins)
- data_quality_flags, weekday, is_monday, is_friday, is_wednesday_eia_day
- instrument_name, symbol, __source_file, __stream (auditability)
