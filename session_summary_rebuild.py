# patch_session_windows_summary_phase1_style.py
# Rebuild ONLY the historical 12/03/2025–29/03/2025 WTI + BRENT session_windows_summary rows
# by mirroring the phase1 path as closely as possible using SAVED intraday files:
#   saved intraday candidates -> build_best_timeframe_bars() -> analysis_intraday -> sessionsummary()
# Existing rows outside patch range remain untouched.

from __future__ import annotations
import math
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError as e:
    raise SystemExit("Please install yfinance first: pip install yfinance") from e


# =========================
# USER CONFIG
# =========================
SOURCE_DIR = Path(r"D:\My Docs\Investing\Analysis Files\output r")
WRITE_DIR = Path(r"D:\My Docs\Investing\Analysis Files\new2")
WRITE_DIR.mkdir(parents=True, exist_ok=True)

PATCH_START = pd.Timestamp("2025-05-26")
PATCH_END = pd.Timestamp("2025-06-02")

PRODUCTS = {
    "WTI": {
        "source_file": "wti_session_windows_summary.xlsx",
        "write_file": "wti_session_windows_summary.xlsx",
        "intraday_5m_file": "wti_5m_ist.xlsx",
        "intraday_15m_file": "wti_15m_ist.xlsx",
        "intraday_60m_file": "wti_60m_ist.xlsx",
        "intraday_5m_file_csv": "wti_5m_ist.csv",
        "intraday_15m_file_csv": "wti_15m_ist.csv",
        "intraday_60m_file_csv": "wti_60m_ist.csv",
        "ticker": "CL=F",
        "instrument_name": "WTI Crude Futures",
        "market": "NYMEX",
        "currency_native": "USD",
    },
    "BRENT": {
        "source_file": "brent_session_windows_summary.xlsx",
        "write_file": "brent_session_windows_summary.xlsx",
        "intraday_5m_file": "brent_5m_ist.xlsx",
        "intraday_15m_file": "brent_15m_ist.xlsx",
        "intraday_60m_file": "brent_60m_ist.xlsx",
        "intraday_5m_file_csv": "brent_5m_ist.csv",
        "intraday_15m_file_csv": "brent_15m_ist.csv",
        "intraday_60m_file_csv": "brent_60m_ist.csv",
        "ticker": "BZ=F",
        "instrument_name": "Brent Crude Futures",
        "market": "ICE",
        "currency_native": "USD",
    },
}

IST = "Asia/Kolkata"

INTERVAL_MINUTES = {
    "1m": 1,
    "2m": 2,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "90m": 90,
    "1h": 60,
}

TARGET_BUCKETS = {
    "5m": ["1m", "2m", "5m", "15m", "60m"],
    "15m": ["1m", "2m", "5m", "15m", "60m"],
    "60m": ["1m", "2m", "5m", "15m", "60m"],
}

SESSION_WINDOWS = {
    "global_reopen_pre_mcx": (3.5, 9.0),
    "mcx_open_drive": (9.0, 10.5),
    "india_morning": (10.5, 12.5),
    "india_midday": (12.5, 15.5),
    "europe_open": (15.5, 17.5),
    "europe_mid": (17.5, 20.0),
    "us_pre_open": (20.0, 21.0),
    "us_open": (21.0, 23.0),
    "mcx_tail": (23.0, 24.0),
}

SESSION_WINDOW_ORDER = [
    "global_reopen_pre_mcx",
    "mcx_open_drive",
    "india_morning",
    "india_midday",
    "europe_open",
    "europe_mid",
    "us_pre_open",
    "us_open",
    "mcx_tail",
]

SESSION_WINDOW_RANK = {name: i for i, name in enumerate(SESSION_WINDOW_ORDER)}

SESSION_SUMMARY_COLS = [
    "trade_date_ist", "symbol", "time_frame_used", "session_window_ist",
    "open_native", "high_native", "low_native", "close_native",
    "open_inr", "high_inr", "low_inr", "close_inr",
    "session_return_pct", "session_range_pct", "session_body_direction",
    "session_close_location_pct", "session_reversal_flag", "session_breakout_flag",
    "session_failed_breakout_flag", "session_trend_strength_score_1_to_5",
    "session_whipsaw_score_1_to_5", "session_notes_short", "data_quality_flags"
]


# =========================
# HELPERS
# =========================
def pct(a, b):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    out = (a - b) / b * 100.0
    if isinstance(out, pd.Series):
        out = out.replace([np.inf, -np.inf], np.nan)
    elif pd.notna(out) and not np.isfinite(out):
        out = np.nan
    return out


def combine_unique_strings(series: pd.Series) -> str:
    vals = []
    for x in series.dropna().astype(str):
        x = x.strip()
        if x and x.lower() not in {"nan", "none", "<na>"} and x not in vals:
            vals.append(x)
    return " | ".join(vals)


def ensure_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    return out[cols]


def _hhmm(ts: pd.Timestamp) -> Tuple[int, int]:
    return ts.hour, ts.minute


def assign_trade_date_ist(ts: pd.Timestamp) -> str:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(IST)
    else:
        ts = ts.tz_convert(IST)
    if (ts.hour, ts.minute) < (3, 30):
        return (ts.normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return ts.normalize().strftime("%Y-%m-%d")

def hour_float_from_ts(ts: pd.Timestamp) -> float:
    ts = pd.Timestamp(ts)
    return ts.hour + ts.minute / 60.0 + ts.second / 3600.0

def assign_session_window(hour_float: float) -> str:
    for name, (start_h, end_h) in SESSION_WINDOWS.items():
        if start_h <= hour_float < end_h:
            return name
    return ""


def assign_subwindow(ts: pd.Timestamp) -> str:
    hour_float = hour_float_from_ts(ts)
    session_window = assign_session_window(hour_float)

    for name, (start_h, end_h) in SESSION_WINDOWS.items():
        if start_h <= hour_float < end_h:
            return name
    return session_window


def fetch_usdinr_daily(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    tk = yf.Ticker("INR=X")
    hist = tk.history(
        start=(start - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=False,
        actions=False,
    )
    if hist.empty:
        return pd.DataFrame(columns=["trade_date_ist", "fx_rate"])
    out = hist.reset_index()
    date_col = "Date" if "Date" in out.columns else out.columns[0]
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out["trade_date_ist"] = out[date_col].dt.strftime("%Y-%m-%d")
    out["fx_rate"] = pd.to_numeric(out["Close"], errors="coerce")
    return (
        out[["trade_date_ist", "fx_rate"]]
        .dropna(subset=["trade_date_ist"])
        .drop_duplicates("trade_date_ist", keep="last")
    )


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def find_existing_file(preferred_xlsx: Path, preferred_csv: Path) -> Optional[Path]:
    if preferred_xlsx.exists():
        return preferred_xlsx
    if preferred_csv.exists():
        return preferred_csv
    return None


def normalize_saved_intraday(df: pd.DataFrame, productkey: str, interval: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    rename_map = {
        "timestamp_original": "timestamp_utc",
        "timestamp": "timestamp_utc",
        "datetime": "timestamp_utc",
        "Datetime": "timestamp_utc",
        "Date": "timestamp_utc",
        "timeframe": "time_frame",
        "sub_window_label": "sub_window_label",
    }
    for old, new in rename_map.items():
        if old in out.columns and new not in out.columns:
            out = out.rename(columns={old: new})

    if "timestamp_ist" in out.columns:
        out["timestamp_ist"] = pd.to_datetime(out["timestamp_ist"], errors="coerce")
        if out["timestamp_ist"].dt.tz is None:
            out["timestamp_ist"] = out["timestamp_ist"].dt.tz_localize(IST, nonexistent="shift_forward", ambiguous="NaT")
        else:
            out["timestamp_ist"] = out["timestamp_ist"].dt.tz_convert(IST)
    elif "timestamp_utc" in out.columns:
        out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"], errors="coerce", utc=True)
        out["timestamp_ist"] = out["timestamp_utc"].dt.tz_convert(IST)
    else:
        return pd.DataFrame()

    if "timestamp_utc" not in out.columns:
        out["timestamp_utc"] = out["timestamp_ist"].dt.tz_convert("UTC")

    if "trade_date_ist" not in out.columns:
        out["trade_date_ist"] = out["timestamp_ist"].apply(assign_trade_date_ist)
    else:
        out["trade_date_ist"] = out["trade_date_ist"].astype(str)

    if "session_window_ist" not in out.columns:
        out["session_window_ist"] = out["timestamp_ist"].apply(assign_session_window)

    if "sub_window_label" not in out.columns:
        out["sub_window_label"] = out["timestamp_ist"].apply(assign_subwindow)

    if "time_frame" not in out.columns:
        out["time_frame"] = interval

    if "symbol" not in out.columns:
        out["symbol"] = productkey

    if "instrument_name" not in out.columns:
        out["instrument_name"] = PRODUCTS[productkey]["instrument_name"]

    if "market" not in out.columns:
        out["market"] = PRODUCTS[productkey]["market"]

    if "contract_logic" not in out.columns:
        out["contract_logic"] = "yahoofrontsymbolnoverifiedrollmetadata"

    if "contract_symbol" not in out.columns:
        out["contract_symbol"] = PRODUCTS[productkey]["ticker"]

    if "source_name" not in out.columns:
        out["source_name"] = "yahoofinance"

    if "source_url" not in out.columns:
        out["source_url"] = "https://finance.yahoo.com"

    if "source_timezone" not in out.columns:
        out["source_timezone"] = "UTC"

    if "currency_native" not in out.columns:
        out["currency_native"] = PRODUCTS[productkey]["currency_native"]

    if "source_resolution_used" not in out.columns:
        out["source_resolution_used"] = interval

    if "source_resolution_minutes" not in out.columns:
        out["source_resolution_minutes"] = INTERVAL_MINUTES[interval]

    if "coverage_method" not in out.columns:
        out["coverage_method"] = "saved_intraday_file"

    for c in ["open_native", "high_native", "low_native", "close_native", "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    volume_series = out["volume"] if "volume" in out.columns else pd.Series(np.nan, index=out.index, dtype="float64")
    out["volume"] = pd.to_numeric(volume_series, errors="coerce")

    if "notes_data_quality" not in out.columns:
        out["notes_data_quality"] = ""

    if "data_quality_flags" not in out.columns:
        out["data_quality_flags"] = ""

    keep = [
        "timestamp_utc", "timestamp_ist", "trade_date_ist", "symbol", "instrument_name", "market",
        "time_frame", "source_resolution_used", "source_resolution_minutes", "coverage_method",
        "contract_logic", "contract_symbol", "source_name", "source_url", "source_timezone",
        "open_native", "high_native", "low_native", "close_native", "volume", "currency_native",
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
        "notes_data_quality", "data_quality_flags", "session_window_ist", "sub_window_label"
    ]
    for c in keep:
        if c not in out.columns:
            out[c] = np.nan

    out = out[keep].dropna(subset=["timestamp_ist"]).sort_values("timestamp_ist").reset_index(drop=True)
    return out


def apply_fx_from_daily_if_missing(df: pd.DataFrame, fxdf: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = df.copy()
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    fx = fxdf.copy()
    fx["trade_date_ist"] = fx["trade_date_ist"].astype(str)

    if "fx_rate_used" not in out.columns:
        out["fx_rate_used"] = np.nan

    out = out.merge(fx, how="left", on="trade_date_ist")

    out["fx_rate_used"] = pd.to_numeric(out["fx_rate_used"], errors="coerce")
    out["fx_rate"] = pd.to_numeric(out["fx_rate"], errors="coerce")
    out["fx_rate_used"] = out["fx_rate_used"].fillna(out["fx_rate"])

    if "currency_native" not in out.columns:
        out["currency_native"] = "USD"

    for base_col in ["open", "high", "low", "close"]:
        native_col = f"{base_col}_native"
        inr_col = f"{base_col}_inr"

        if native_col in out.columns:
            out[native_col] = pd.to_numeric(out[native_col], errors="coerce")

        if inr_col not in out.columns:
            out[inr_col] = np.nan
        out[inr_col] = pd.to_numeric(out[inr_col], errors="coerce")

        missing_inr = out[inr_col].isna() & out[native_col].notna() & out["fx_rate_used"].notna()
        out.loc[missing_inr, inr_col] = out.loc[missing_inr, native_col] * out.loc[missing_inr, "fx_rate_used"]

    if "notes_data_quality" not in out.columns:
        out["notes_data_quality"] = ""
    if "data_quality_flags" not in out.columns:
        out["data_quality_flags"] = ""

    missing_fx = out["fx_rate_used"].isna()
    out["notes_data_quality"] = np.where(
        missing_fx,
        np.where(out["notes_data_quality"].astype(str).str.strip() == "", "Missing FX for INR conversion", out["notes_data_quality"]),
        out["notes_data_quality"],
    )
    out["data_quality_flags"] = np.where(
        missing_fx,
        np.where(out["data_quality_flags"].astype(str).str.strip() == "", "MISSING_DAILY_FX", out["data_quality_flags"]),
        out["data_quality_flags"],
    )

    out = out.drop(columns=["fx_rate"], errors="ignore")
    return out


def load_saved_intraday_candidates(productkey: str, start: pd.Timestamp, end: pd.Timestamp) -> Dict[str, pd.DataFrame]:
    info = PRODUCTS[productkey]
    fxdf = fetch_usdinr_daily(start, end)

    out: Dict[str, pd.DataFrame] = {}
    for interval in ["5m", "15m", "60m"]:
        xlsx_key = f"intraday_{interval}_file"
        csv_key = f"intraday_{interval}_file_csv"

        file_path = find_existing_file(
            SOURCE_DIR / info[xlsx_key],
            SOURCE_DIR / info[csv_key],
        )

        if file_path is None:
            out[interval] = pd.DataFrame()
            continue

        raw = read_table(file_path)
        part = normalize_saved_intraday(raw, productkey, interval)
        if not part.empty:
            part = apply_fx_from_daily_if_missing(part, fxdf)
            mask = (
                (pd.to_datetime(part["trade_date_ist"], errors="coerce") >= start) &
                (pd.to_datetime(part["trade_date_ist"], errors="coerce") <= end)
            )
            part = part.loc[mask].copy().reset_index(drop=True)
        out[interval] = part

    out["1m"] = pd.DataFrame()
    out["2m"] = pd.DataFrame()
    return out


def _interval_rank(interval: str) -> int:
    return INTERVAL_MINUTES.get(interval, 10_000)


def _choose_finest_covering_source(candidates: Dict[str, pd.DataFrame], target_ts: pd.Timestamp, target_minutes: int) -> Optional[pd.Series]:
    best_row = None
    best_rank = None

    for interval, df in candidates.items():
        if df is None or df.empty:
            continue
        minutes = INTERVAL_MINUTES[interval]
        if minutes > target_minutes:
            continue

        if minutes == target_minutes:
            rows = df[df["timestamp_ist"] == target_ts]
            if not rows.empty:
                rank = _interval_rank(interval)
                if best_row is None or best_rank is None or rank < best_rank:
                    best_row = rows.sort_values("timestamp_ist").iloc[-1]
                    best_rank = rank
            continue

        start_ts = target_ts
        end_ts = target_ts + pd.Timedelta(minutes=target_minutes)
        rows = df[(df["timestamp_ist"] >= start_ts) & (df["timestamp_ist"] < end_ts)].sort_values("timestamp_ist")
        if rows.empty:
            continue

        expected = math.ceil(target_minutes / minutes)
        coverage = rows["timestamp_ist"].nunique()
        if coverage >= expected:
            o = rows["open_native"].iloc[0]
            h = rows["high_native"].max()
            l = rows["low_native"].min()
            c = rows["close_native"].iloc[-1]
            oi = rows["open_inr"].iloc[0] if "open_inr" in rows.columns else np.nan
            hi = rows["high_inr"].max() if "high_inr" in rows.columns else np.nan
            li = rows["low_inr"].min() if "low_inr" in rows.columns else np.nan
            ci = rows["close_inr"].iloc[-1] if "close_inr" in rows.columns else np.nan

            row = rows.iloc[0].copy()
            row["timestamp_utc"] = rows["timestamp_utc"].iloc[0]
            row["timestamp_ist"] = target_ts
            row["open_native"] = o
            row["high_native"] = h
            row["low_native"] = l
            row["close_native"] = c
            row["open_inr"] = oi
            row["high_inr"] = hi
            row["low_inr"] = li
            row["close_inr"] = ci
            row["volume"] = pd.to_numeric(rows["volume"], errors="coerce").sum()
            row["source_resolution_used"] = interval
            row["source_resolution_minutes"] = minutes
            row["coverage_method"] = "bestavailable_fullbucket"
            row["notes_data_quality"] = combine_unique_strings(rows.get("notes_data_quality", pd.Series(dtype=object)))
            row["data_quality_flags"] = combine_unique_strings(rows.get("data_quality_flags", pd.Series(dtype=object)))
            row["time_frame"] = f"{target_minutes}m" if target_minutes != 60 else "60m"
            row["session_window_ist"] = assign_session_window(hour_float_from_ts(target_ts))
            row["sub_window_label"] = assign_subwindow(target_ts)

            rank = _interval_rank(interval)
            if best_row is None or best_rank is None or rank < best_rank:
                best_row = row
                best_rank = rank

    return best_row


def _choose_finest_partial_source(candidates: Dict[str, pd.DataFrame], target_ts: pd.Timestamp, target_minutes: int) -> Optional[pd.Series]:
    best_row = None
    best_score = None

    for interval, df in candidates.items():
        if df is None or df.empty:
            continue
        minutes = INTERVAL_MINUTES[interval]
        if minutes > target_minutes:
            continue

        if minutes == target_minutes:
            rows = df[df["timestamp_ist"] == target_ts].sort_values("timestamp_ist")
        else:
            start_ts = target_ts
            end_ts = target_ts + pd.Timedelta(minutes=target_minutes)
            rows = df[(df["timestamp_ist"] >= start_ts) & (df["timestamp_ist"] < end_ts)].sort_values("timestamp_ist")

        if rows.empty:
            continue

        coverage = rows["timestamp_ist"].nunique()
        rank = _interval_rank(interval)
        score = (-coverage, rank)

        o = rows["open_native"].iloc[0]
        h = rows["high_native"].max()
        l = rows["low_native"].min()
        c = rows["close_native"].iloc[-1]
        oi = rows["open_inr"].iloc[0] if "open_inr" in rows.columns else np.nan
        hi = rows["high_inr"].max() if "high_inr" in rows.columns else np.nan
        li = rows["low_inr"].min() if "low_inr" in rows.columns else np.nan
        ci = rows["close_inr"].iloc[-1] if "close_inr" in rows.columns else np.nan

        row = rows.iloc[0].copy()
        row["timestamp_utc"] = rows["timestamp_utc"].iloc[0]
        row["timestamp_ist"] = target_ts
        row["open_native"] = o
        row["high_native"] = h
        row["low_native"] = l
        row["close_native"] = c
        row["open_inr"] = oi
        row["high_inr"] = hi
        row["low_inr"] = li
        row["close_inr"] = ci
        row["volume"] = pd.to_numeric(rows["volume"], errors="coerce").sum()
        row["source_resolution_used"] = interval
        row["source_resolution_minutes"] = minutes
        row["coverage_method"] = "bestavailable_partialbucket"
        row["notes_data_quality"] = combine_unique_strings(rows.get("notes_data_quality", pd.Series(dtype=object)))
        row["data_quality_flags"] = combine_unique_strings(rows.get("data_quality_flags", pd.Series(dtype=object)))
        row["time_frame"] = f"{target_minutes}m" if target_minutes != 60 else "60m"
        row["session_window_ist"] = assign_session_window(hour_float_from_ts(target_ts))
        row["sub_window_label"] = assign_subwindow(target_ts)

        if best_row is None or best_score is None or score < best_score:
            best_row = row
            best_score = score

    return best_row


def build_best_timeframe_bars(candidates: Dict[str, pd.DataFrame], target_label: str) -> pd.DataFrame:
    target_minutes = INTERVAL_MINUTES[target_label]
    base_times = set()

    for interval, df in candidates.items():
        if df is None or df.empty:
            continue
        minutes = INTERVAL_MINUTES[interval]
        if minutes > target_minutes:
            continue
        floored = df["timestamp_ist"].dt.floor(f"{target_minutes}min")
        base_times.update(floored.dropna().tolist())

    if not base_times:
        return pd.DataFrame()

    rows = []
    for ts in sorted(base_times):
        row = _choose_finest_covering_source(candidates, ts, target_minutes)
        if row is None:
            row = _choose_finest_partial_source(candidates, ts, target_minutes)
        if row is not None:
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).sort_values(["trade_date_ist", "timestamp_ist"]).reset_index(drop=True)
    return out


def session_summary(intraday: pd.DataFrame, symbol: str, timeframe_used: str) -> pd.DataFrame:
    if intraday.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist","symbol","timeframe_used","session_window_ist",
            "open_native","high_native","low_native","close_native",
            "open_inr","high_inr","low_inr","close_inr",
            "session_return_pct","session_range_pct","session_body_direction",
            "session_close_location_pct","session_reversal_flag","session_breakout_flag",
            "session_failed_breakout_flag","session_trend_strength_score_1_to_5",
            "session_whipsaw_score_1_to_5","session_notes_short","data_quality_flags"
        ])

    rows = []
    work = intraday.copy()
    work = work.dropna(subset=["trade_date_ist", "session_window_ist"])
    work = _sort_session_rows(work)

    for (d, win), g in work.groupby(["trade_date_ist", "session_window_ist"], sort=False):
        g = g.sort_values("timestamp_ist")
        o = g["open_native"].iloc[0]
        h = g["high_native"].max()
        l = g["low_native"].min()
        c = g["close_native"].iloc[-1]

        oi = g["open_inr"].iloc[0] if "open_inr" in g.columns else np.nan
        hi = g["high_inr"].max() if "high_inr" in g.columns else np.nan
        li = g["low_inr"].min() if "low_inr" in g.columns else np.nan
        ci = g["close_inr"].iloc[-1] if "close_inr" in g.columns else np.nan

        rng = h - l
        eff = abs(c - o) / rng if pd.notna(rng) and rng else np.nan

        rows.append({
            "trade_date_ist": d,
            "symbol": symbol,
            "timeframe_used": g["source_resolution_used"].iloc[0] if "source_resolution_used" in g.columns else timeframe_used,
            "session_window_ist": win,
            "open_native": o,
            "high_native": h,
            "low_native": l,
            "close_native": c,
            "open_inr": oi,
            "high_inr": hi,
            "low_inr": li,
            "close_inr": ci,
            "session_return_pct": ((c - o) / o * 100.0) if pd.notna(o) and o else np.nan,
            "session_range_pct": ((h - l) / o * 100.0) if pd.notna(o) and o else np.nan,
            "session_body_direction": "UP" if c > o else ("DOWN" if c < o else "FLAT"),
            "session_close_location_pct": ((c - l) / rng * 100.0) if pd.notna(rng) and rng else np.nan,
            "session_reversal_flag": False,
            "session_breakout_flag": False,
            "session_failed_breakout_flag": False,
            "session_trend_strength_score_1_to_5": 5 if pd.notna(eff) and eff >= 0.75 else 3 if pd.notna(eff) and eff >= 0.4 else 2,
            "session_whipsaw_score_1_to_5": 5 if pd.notna(eff) and eff < 0.2 else 2,
            "session_notes_short": "",
            "data_quality_flags": "",
        })

    return _sort_session_rows(pd.DataFrame(rows))


def load_existing_session_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=SESSION_SUMMARY_COLS)

    if path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path)
    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    if "trade_date_ist" in df.columns:
        df["trade_date_ist"] = df["trade_date_ist"].astype(str)
    return df


def merge_patch(existing: pd.DataFrame, patched: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    existing = existing.copy()

    if existing.empty:
        out = patched.copy()
        return ensure_cols(out, SESSION_SUMMARY_COLS)

    existing["trade_date_ist"] = existing["trade_date_ist"].astype(str)

    mask = (
        (pd.to_datetime(existing["trade_date_ist"], errors="coerce") >= start) &
        (pd.to_datetime(existing["trade_date_ist"], errors="coerce") <= end)
    )
    untouched = existing.loc[~mask].copy()

    all_cols = list(dict.fromkeys(list(existing.columns) + SESSION_SUMMARY_COLS))
    untouched = ensure_cols(untouched, all_cols)
    patched = ensure_cols(patched, all_cols)

    out = pd.concat([untouched, patched], ignore_index=True, sort=False)

    if {"trade_date_ist", "session_window_ist"}.issubset(out.columns):
        out = out.drop_duplicates(subset=["trade_date_ist", "session_window_ist"], keep="last")

    session_rank = {k: i for i, k in enumerate(SESSION_WINDOW_ORDER)}
    out["_rk"] = out["session_window_ist"].map(session_rank).fillna(999)
    out = out.sort_values(["trade_date_ist", "_rk"]).drop(columns="_rk").reset_index(drop=True)
    return out


def rebuild_product(productkey: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    candidates = load_saved_intraday_candidates(productkey, start, end)

    i5 = build_best_timeframe_bars(candidates, "5m")
    i15 = build_best_timeframe_bars(candidates, "15m")
    i60 = build_best_timeframe_bars(candidates, "60m")

    analysis_intraday = i15.copy() if not i15.empty else i60.copy()
    if analysis_intraday.empty and not i5.empty:
        analysis_intraday = i5.copy()

    if analysis_intraday.empty:
        return pd.DataFrame(columns=SESSION_SUMMARY_COLS)

    sess = session_summary(analysis_intraday, productkey, "bestavailableintraday")
    sess["trade_date_ist"] = sess["trade_date_ist"].astype(str)
    sess = sess[
        (pd.to_datetime(sess["trade_date_ist"], errors="coerce") >= start) &
        (pd.to_datetime(sess["trade_date_ist"], errors="coerce") <= end)
    ].copy()

    return ensure_cols(sess, SESSION_SUMMARY_COLS)

def _sort_session_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()

    out = df.copy()
    if "session_window_ist" in out.columns:
        out["_session_rank"] = (
            out["session_window_ist"].map(SESSION_WINDOW_RANK).fillna(999).astype(int)
        )

    sort_cols = [c for c in ["trade_date_ist", "_session_rank", "timestamp_ist"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols)

    return out.drop(columns=["_session_rank"], errors="ignore").reset_index(drop=True)

def build_phase1_style_session_patch(intraday_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if intraday_df is None or intraday_df.empty:
        return pd.DataFrame()

    work = intraday_df.copy()
    work["timestamp_ist"] = pd.to_datetime(work["timestamp_ist"], errors="coerce")
    work = work.dropna(subset=["timestamp_ist"]).copy()

    if "trade_date_ist" not in work.columns:
        work["trade_date_ist"] = work["timestamp_ist"].dt.strftime("%Y-%m-%d")

    hh = work["timestamp_ist"].dt.hour + work["timestamp_ist"].dt.minute / 60.0
    work["session_window_ist"] = hh.map(assign_session_window)
    work = work[work["session_window_ist"] != ""].copy()

    if work.empty:
        return pd.DataFrame()

    if "source_resolution_used" not in work.columns:
        work["source_resolution_used"] = "best_available_intraday"

    return session_summary(work, symbol, "best_available_intraday")

def merge_session_patch_selective(existing_df: pd.DataFrame, patched_df: pd.DataFrame) -> pd.DataFrame:
    if patched_df is None or patched_df.empty:
        return existing_df.copy() if existing_df is not None else pd.DataFrame()

    key_cols = ["trade_date_ist", "session_window_ist"]
    repair_cols = ["open_inr", "high_inr", "low_inr", "close_inr"]

    if existing_df is None or existing_df.empty:
        return _sort_session_rows(patched_df)

    out = existing_df.copy()

    for c in key_cols:
        out[c] = out[c].astype(str)
        patched_df[c] = patched_df[c].astype(str)

    out = out.set_index(key_cols)
    patch = patched_df.set_index(key_cols)

    missing_keys = patch.index.difference(out.index)
    if len(missing_keys):
        out = pd.concat([out, patch.loc[missing_keys]], axis=0)

    common_keys = patch.index.intersection(out.index)
    for col in repair_cols:
        if col not in out.columns:
            out[col] = np.nan
        if col in patch.columns:
            needs_fill = out.loc[common_keys, col].isna()
            fill_vals = patch.loc[common_keys, col]
            out.loc[common_keys, col] = out.loc[common_keys, col].where(~needs_fill, fill_vals)

    for col in ["symbol","timeframe_used","open_native","high_native","low_native","close_native",
                "session_return_pct","session_range_pct","session_body_direction",
                "session_close_location_pct","session_reversal_flag","session_breakout_flag",
                "session_failed_breakout_flag","session_trend_strength_score_1_to_5",
                "session_whipsaw_score_1_to_5","session_notes_short","data_quality_flags"]:
        if col not in out.columns and col in patch.columns:
            out[col] = np.nan
        if col in patch.columns:
            needs_fill = out.loc[common_keys, col].isna()
            out.loc[common_keys, col] = out.loc[common_keys, col].where(~needs_fill, patch.loc[common_keys, col])

    out = out.reset_index()
    return _sort_session_rows(out)

def main():
    WRITE_DIR.mkdir(parents=True, exist_ok=True)

    for productkey, info in PRODUCTS.items():
        src_path = SOURCE_DIR / info["source_file"]
        dst_path = WRITE_DIR / info["write_file"]

        existing = load_existing_session_file(src_path)
        patched = rebuild_product(productkey, PATCH_START, PATCH_END)
        merged = merge_patch(existing, patched, PATCH_START, PATCH_END)

        backup = dst_path.with_suffix(dst_path.suffix + ".bak_pre_phase1style_patch")
        if dst_path.exists() and not backup.exists():
            dst_path.replace(backup)

        if dst_path.suffix.lower() == ".xlsx":
            merged.to_excel(dst_path, index=False)
        else:
            merged.to_csv(dst_path, index=False)

        print(f"{productkey}: source_file = {src_path}")
        print(f"{productkey}: write_file = {dst_path}")
        print(f"{productkey}: wrote {len(merged)} rows")
        print(f"{productkey}: patched_rows_in_range = {len(patched)}")

        if not patched.empty:
            cols = [
                c for c in [
                    "trade_date_ist", "session_window_ist",
                    "open_native", "high_native", "low_native", "close_native"
                ]
                if c in patched.columns
            ]
            if cols:
                print(patched[cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()