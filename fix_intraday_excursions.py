import pandas as pd
import numpy as np

SRC_FILE = "intraday_excursions_combined.xlsx"
REF_FILE = "intraday_excursions_combined_n.xlsx"
OUT_FILE = "intraday_excursions_combined_modified.xlsx"

WINDOW_ORDER = [
    "global_reopen_pre_mcx",
    "mcx_open_drive",
    "india_morning",
    "india_midday",
    "europe_open",
    "europe_mid",
    "us_pre_open",
    "us_open",
    "mcx_tail",
    "other_valid_hours",
]

def main() -> None:
    src = pd.read_excel(SRC_FILE)
    ref = pd.read_excel(REF_FILE)

    src = src.copy()
    ref = ref.copy()

    if "Unnamed: 10" in src.columns:
        src = src.drop(columns=["Unnamed: 10"])

    src["trade_date_ist"] = pd.to_datetime(src["trade_date_ist"], errors="coerce")
    ref["trade_date_ist"] = pd.to_datetime(ref["trade_date_ist"], errors="coerce")

    all_dates = sorted(src["trade_date_ist"].dropna().unique())
    out_rows: list[dict[str, object]] = []

    for d in all_dates:
        s_day = src[src["trade_date_ist"] == d]
        r_day = ref[ref["trade_date_ist"] == d]

        symbol_vals = s_day["symbol"].dropna()
        symbol = symbol_vals.iloc[0] if not symbol_vals.empty else np.nan

        for w in WINDOW_ORDER:
            r_rows = r_day[r_day["session_window_ist"] == w]
            if not r_rows.empty:
                row: dict[str, object] = r_rows.iloc[0].to_dict()
            else:
                s_rows = s_day[s_day["session_window_ist"] == w]
                if not s_rows.empty:
                    row = s_rows.iloc[0].to_dict()
                else:
                    row = {c: np.nan for c in src.columns}
                    row["direction_reference"] = np.nan

            row["trade_date_ist"] = d
            row["session_window_ist"] = w
            symbol_value = row.get("symbol")
            if symbol_value is None or (isinstance(symbol_value, float) and pd.isna(symbol_value)):
                row["symbol"] = symbol

            out_rows.append(row)

    out = pd.DataFrame(out_rows)
    out = out[src.columns.tolist()]
    out.to_excel(OUT_FILE, index=False)

if __name__ == "__main__":
    main()