# Coverage & Limitations

## Data that existed
- WTI & Brent daily/intraday (5m/15m/60m) for 2026-03-02 to 2026-07-17 (~98 trading days).
- Session-window aggregations pre-computed for both instruments.
- Daily master summary (cross-market joined).

## Data missing
- MCX CRUDEOILM intraday data (configured in `crude_data_import.py` but not in the input directory at run time).
- EIA inventory weekly series (configured but not pulled).
- USD/INR FX rate (configured but empty — explains native-currency-only metrics).
- News events master (placeholder CSV only).

## What was excluded for insufficient sample size
- Phase 3 (4 days): all per-window magnitude-tier and triplet stats flagged LOW-CONFIDENCE.
- Phase 4 (5 days): same.
- Anomaly metrics flagged with `|z| > 2.5` rolling z-score; thresholds raise flag count, don't suppress.

## What should be re-run as more data accumulates
- Re-run all engines weekly as new trading days accumulate, especially Phase 3 and Phase 4.
- Re-validate phase boundaries as the war's evolution continues (use Step 0 changepoint detection).
- Expand to MCX CRUDEOILM if/when that data becomes available.
