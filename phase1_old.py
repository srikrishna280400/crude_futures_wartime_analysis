#phase1_old.py
#!/usr/bin/env python3

from __future__ import annotations
import os
import json
import math
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Mapping
import numpy as np
import pandas as pd
import requests
import yfinance as yf

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ============================================================
# CONFIG
# ============================================================

START_DATE = os.getenv("START_DATE", "2026-03-01")
END_DATE = os.getenv("END_DATE", "2026-05-08")
TZ_NAME = os.getenv("TZ", "Asia/Kolkata")

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INPUT_DIR = Path(os.getenv("INPUT_DIR", "input"))
INPUT_DIR.mkdir(parents=True, exist_ok=True)

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
EIA_API_KEY = os.getenv("EIA_API_KEY", "")

FRED_WTI_SERIES_ID = os.getenv("FRED_WTI_SERIES_ID", "DCOILWTICO")
FRED_BRENT_SERIES_ID = os.getenv("FRED_BRENT_SERIES_ID", "DCOILBRENTEU")
FRED_USDINR_SERIES_ID = os.getenv("FRED_USDINR_SERIES_ID", "DEXINUS")

# Better EIA shape: route + facets, not just bare route strings
EIA_SPOT_ROUTE = os.getenv("EIA_SPOT_ROUTE", "petroleum/pri/spt/data")
EIA_BRENT_FACETS_JSON = os.getenv("EIA_BRENT_FACETS_JSON", '{"series":["RBRTE"]}')
EIA_WTI_FACETS_JSON = os.getenv("EIA_WTI_FACETS_JSON", "")
EIA_INVENTORY_ROUTE = os.getenv("EIA_INVENTORY_ROUTE", "")
EIA_INVENTORY_FACETS_JSON = os.getenv("EIA_INVENTORY_FACETS_JSON", "")

NEWS_EVENTS_INPUT_CSV = os.getenv("NEWS_EVENTS_INPUT_CSV", str(INPUT_DIR / "news_events_master.csv"))
MANUAL_DAY_LABELS_INPUT_CSV = os.getenv("MANUAL_DAY_LABELS_INPUT_CSV", str(INPUT_DIR / "manual_day_labels.csv"))

YF_INTRADAY_PERIOD = os.getenv("YF_INTRADAY_PERIOD", "7d")

YF_1M_LOOKBACK_DAYS = int(os.getenv("YF_1M_LOOKBACK_DAYS", "30"))
YF_LT1D_LOOKBACK_DAYS = int(os.getenv("YF_LT1D_LOOKBACK_DAYS", "60"))

YF_INTERVAL_PLAN = [
    ("1m", 7, YF_1M_LOOKBACK_DAYS),
    ("5m", 30, YF_LT1D_LOOKBACK_DAYS),
    ("15m", 30, YF_LT1D_LOOKBACK_DAYS),
    ("60m", 60, YF_LT1D_LOOKBACK_DAYS),
]

INTERVAL_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "60m": 60,
    "1d": 1440,
}

IST_ANCHOR_HOUR = 3
IST_ANCHOR_MINUTE = 30

PRODUCTS = {
    "WTI": {
        "yahoo_symbol": "CL=F",
        "market": "NYMEX",
        "instrument_name": "WTI Crude Futures",
        "currency_native": "USD",
        "root": "CL",
    },
    "BRENT": {
        "yahoo_symbol": "BZ=F",
        "market": "ICE",
        "instrument_name": "Brent Crude Futures",
        "currency_native": "USD",
        "root": "BZ",
    },
}

SESSION_WINDOWS = {
    "asia_early": (3.5, 9.0),
    "europe_open": (15.5, 17.5),
    "europe_mid": (17.5, 20.0),
    "us_pre_open": (20.0, 21.0),
    "us_open": (21.0, 23.0),
    "us_late": (23.0, 26.0),
}

SUB_WINDOWS = {
    "first_30m_after_europe_open": (15.5, 16.0),
    "first_hour_after_europe_open": (15.5, 16.5),
    "first_30m_after_us_open": (21.0, 21.5),
    "first_hour_after_us_open": (21.0, 22.0),
    "us_late_reversal_window": (23.0, 24.0),
    "final_hour_of_session_if_identifiable": (24.0, 25.0),
}

EXPECTED_OUTPUTS = [
    "wti_daily_ist.csv",
    "wti_60m_ist.csv",
    "wti_15m_ist.csv",
    "wti_5m_ist.csv",
    "brent_daily_ist.csv",
    "brent_60m_ist.csv",
    "brent_15m_ist.csv",
    "brent_5m_ist.csv",
    "wti_spot_daily_reference_ist.csv",
    "brent_spot_daily_reference_ist.csv",
    "usdinr_daily_ist.csv",
    "wti_session_windows_summary.csv",
    "brent_session_windows_summary.csv",
    "daily_master_summary.csv",
    "day_type_labels.csv",
    "deviation_pattern_labels.csv",
    "news_events_master.csv",
    "contract_roll_log.csv",
    "day_window_behavior_matrix.csv",
    "archetype_similarity_features.csv",
    "scenario_backtest_features.csv",
    "intraday_excursions_combined.csv",
    "methodology_and_sources.md",
]

# ============================================================
# HELPERS
# ============================================================

def dt_ist(s):
    return pd.Timestamp(s, tz=TZ_NAME)

def to_num(s: Any) -> pd.Series:
    if s is None:
        return pd.Series(dtype="float64")
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    return pd.to_numeric(s, errors="coerce")

def utc_ts(x):
    x = pd.to_datetime(x, utc=True, errors="coerce")
    return x

def choose_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for n in names:
        if n.lower() in cols:
            return cols[n.lower()]
    return None

def session_trade_date_ist(ts_ist: pd.Series) -> pd.Series:
    ts = pd.Series(ts_ist)
    anchor = ts.dt.normalize() + pd.Timedelta(hours=IST_ANCHOR_HOUR, minutes=IST_ANCHOR_MINUTE)
    out = pd.Series(
        np.where(ts < anchor, (ts - pd.Timedelta(days=1)).dt.date, ts.dt.date),
        index=ts.index,
    )
    return out

def hour_float(ts: pd.Timestamp) -> float:
    h = ts.hour + ts.minute / 60.0
    if h < 3.5:
        h += 24.0
    return h

def assign_session_window(ts: pd.Timestamp) -> str:
    h = hour_float(ts)
    for name, (a, b) in SESSION_WINDOWS.items():
        if a <= h < b:
            return name
    return "other_valid_hours"

def assign_sub_window(ts: pd.Timestamp) -> str:
    h = hour_float(ts)
    for name, (a, b) in SUB_WINDOWS.items():
        if a <= h < b:
            return name
    return ""

def non_weekend_trade_dates(start: str, end: str) -> pd.DatetimeIndex:
    days = pd.date_range(start, end, freq="D")
    return days[days.dayofweek < 5]

def safe_to_df(obj) -> pd.DataFrame:
    df = obj.to_df()
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()
    else:
        df = df.reset_index(drop=False)
    return df

def ensure_datetime_col(df: pd.DataFrame, candidates: List[str], utc=True) -> pd.Series:
    c = choose_col(df, candidates)
    if c is None:
        return pd.Series([pd.NaT] * len(df))
    return pd.to_datetime(df[c], utc=utc, errors="coerce")

def pct(a: pd.Series, b: pd.Series) -> pd.Series:
    a_s = pd.Series(a)
    b_s = pd.Series(b)
    out = pd.Series(np.where((a_s.notna()) & (b_s.notna()) & (b_s != 0), (a_s - b_s) / b_s * 100.0, np.nan))
    out.index = a_s.index
    return out

def write_csv(df: pd.DataFrame, filename: str):
    (OUTPUT_DIR / filename).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / filename, index=False)

def empty_csv(columns: List[str], filename: str):
    write_csv(pd.DataFrame(columns=columns), filename)


def parse_json_env_dict(text: str) -> Optional[dict]:
    txt = str(text or "").strip()
    if not txt:
        return None
    try:
        obj = json.loads(txt)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def ensure_input_templates():
    news_cols = [
        "event_id","trade_date_ist","event_datetime_original","event_datetime_ist","source_name","source_url","headline",
        "summary_1_sentence","event_type","trump_statement_flag","trump_post_flag","trump_direct_quote_short",
        "iran_hormuz_flag","shipping_disruption_flag","sanctions_flag","talks_negotiation_flag","ceasefire_flag",
        "attack_threat_flag","OPEC_supply_flag","inventory_flag","usd_macro_flag","equity_risk_sentiment_flag",
        "market_interpretation_bucket","expected_wti_bias","expected_brent_bias","confidence_1_to_5"
    ]

    manual_day_cols = [
        "trade_date_ist","symbol_focus","geo_bucket_primary","geo_bucket_secondary",
        "price_path_bucket_primary","price_path_bucket_secondary","bucket_confidence_1_to_5",
        "why_this_bucket_short","main_evidence_short","deviation_from_recent_pattern_flag","deviation_type_short"
    ]

    news_path = Path(NEWS_EVENTS_INPUT_CSV)
    news_path.parent.mkdir(parents=True, exist_ok=True)
    if not news_path.exists():
        pd.DataFrame(columns=news_cols).to_csv(news_path, index=False)

    manual_path = Path(MANUAL_DAY_LABELS_INPUT_CSV)
    manual_path.parent.mkdir(parents=True, exist_ok=True)
    if not manual_path.exists():
        pd.DataFrame(columns=manual_day_cols).to_csv(manual_path, index=False)


def apply_manual_day_label_overrides(auto_df: pd.DataFrame) -> pd.DataFrame:
    if auto_df is None or auto_df.empty:
        return auto_df

    path = Path(MANUAL_DAY_LABELS_INPUT_CSV)
    if not MANUAL_DAY_LABELS_INPUT_CSV or not path.exists():
        return auto_df

    manual = pd.read_csv(path)
    if manual.empty or "trade_date_ist" not in manual.columns:
        return auto_df

    out = auto_df.copy()
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    manual["trade_date_ist"] = manual["trade_date_ist"].astype(str)

    for c in out.columns:
        if c not in manual.columns:
            manual[c] = np.nan

    manual = manual[out.columns].copy()

    base = out.set_index("trade_date_ist")
    override = manual.set_index("trade_date_ist")

    overlap = override.index.intersection(base.index)
    if len(overlap) > 0:
        base.loc[overlap, :] = override.loc[overlap, :]

    extra = override.loc[~override.index.isin(base.index)].copy()
    merged = pd.concat([base, extra], axis=0).reset_index()

    return merged.sort_values("trade_date_ist").reset_index(drop=True)

# ============================================================
# API LAYERS
# ============================================================

def fred_series(series_id: str) -> pd.DataFrame:
    if not series_id or not FRED_API_KEY:
        return pd.DataFrame(columns=["trade_date_ist", "value"])
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": START_DATE,
        "observation_end": END_DATE,
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json().get("observations", [])
    out = pd.DataFrame(data)
    if out.empty:
        return pd.DataFrame(columns=["trade_date_ist", "value"])
    out["trade_date_ist"] = pd.to_datetime(out["date"]).dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out[["trade_date_ist", "value"]].dropna()

def eia_route(route: str, facets: Optional[dict] = None, frequency: str = "daily") -> pd.DataFrame:
    if not route or not EIA_API_KEY:
        return pd.DataFrame()
    params = {"api_key": EIA_API_KEY, "frequency": frequency, "data[0]": "value", "sort[0][column]": "period", "sort[0][direction]": "asc"}
    if facets:
        for facet_name, facet_values in facets.items():
            for i, v in enumerate(facet_values):
                params[f"facets[{facet_name}][{i}]"] = v
    url = f"https://api.eia.gov/v2/{route}"
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    payload = r.json()
    rows = (((payload or {}).get("response") or {}).get("data")) or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    period_col = choose_col(df, ["period", "date"])
    value_col = choose_col(df, ["value"])
    df["trade_date_ist"] = pd.to_datetime(df[period_col], errors="coerce").dt.date
    df["value"] = pd.to_numeric(df[value_col], errors="coerce")
    return df

def get_eia_brent_reference() -> pd.DataFrame:
    facets = parse_json_env_dict(EIA_BRENT_FACETS_JSON)
    if not EIA_SPOT_ROUTE or not facets:
        return pd.DataFrame(columns=["trade_date_ist", "close_native"])
    df = eia_route(EIA_SPOT_ROUTE, facets=facets, frequency="daily")
    if df.empty:
        return pd.DataFrame(columns=["trade_date_ist", "close_native"])
    df = df.rename(columns={"value": "close_native"})
    df["symbol"] = "BRENT_SPOT_EIA"
    df["source_name"] = "EIA"
    df["source_url"] = "https://www.eia.gov"
    return df[["trade_date_ist", "close_native", "symbol", "source_name", "source_url"]]


def get_eia_wti_reference() -> pd.DataFrame:
    facets = parse_json_env_dict(EIA_WTI_FACETS_JSON)
    if not EIA_SPOT_ROUTE or not facets:
        return pd.DataFrame(columns=["trade_date_ist", "close_native"])
    df = eia_route(EIA_SPOT_ROUTE, facets=facets, frequency="daily")
    if df.empty:
        return pd.DataFrame(columns=["trade_date_ist", "close_native"])
    df = df.rename(columns={"value": "close_native"})
    df["symbol"] = "WTI_SPOT_EIA"
    df["source_name"] = "EIA"
    df["source_url"] = "https://www.eia.gov"
    return df[["trade_date_ist", "close_native", "symbol", "source_name", "source_url"]]


def get_eia_inventory_reference() -> pd.DataFrame:
    facets = parse_json_env_dict(EIA_INVENTORY_FACETS_JSON)
    if not EIA_INVENTORY_ROUTE:
        return pd.DataFrame()
    df = eia_route(EIA_INVENTORY_ROUTE, facets=facets, frequency="weekly")
    return df if not df.empty else pd.DataFrame()

# def databento_client() -> db.Historical:
#     return db.Historical(DATABENTO_API_KEY)

# ============================================================
# YAHOO INGESTION
# ============================================================

def yahoo_ticker(product_key: str) -> yf.Ticker:
    return yf.Ticker(PRODUCTS[product_key]["yahoo_symbol"])


def get_definitions(product_key: str) -> pd.DataFrame:
    cfg = PRODUCTS[product_key]
    return pd.DataFrame([{
        "raw_symbol": cfg["yahoo_symbol"],
        "instrument_id": cfg["yahoo_symbol"],
        "asset": cfg["root"],
        "instrument_class": "FUT",
        "contract_expiry_date": pd.NaT,
    }])


def get_stats(product_key: str) -> pd.DataFrame:
    return pd.DataFrame(columns=["trade_date_ist", "instrument_id", "volume", "open_interest"])


def build_roll_schedule(def_df: pd.DataFrame, stats_df: pd.DataFrame, product_key: str) -> pd.DataFrame:
    dates = pd.Series(non_weekend_trade_dates(START_DATE, END_DATE).date, name="trade_date_ist")
    cfg = PRODUCTS[product_key]
    return pd.DataFrame({
        "trade_date_ist": dates,
        "symbol": product_key,
        "contract_symbol": cfg["yahoo_symbol"],
        "contract_expiry_date": pd.NaT,
        "rolled_flag": False,
        "roll_reference": "",
        "days_to_expiry": np.nan,
        "open_interest": np.nan,
        "volume": np.nan,
    })


def _normalize_yf_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.reset_index().copy()

    dt_col = "Datetime" if "Datetime" in out.columns else "Date"
    out["timestamp_utc"] = pd.to_datetime(out[dt_col], utc=True, errors="coerce")

    rename_map = {}
    for c in out.columns:
        cl = str(c).lower()
        if cl == "open":
            rename_map[c] = "open_native"
        elif cl == "high":
            rename_map[c] = "high_native"
        elif cl == "low":
            rename_map[c] = "low_native"
        elif cl == "close":
            rename_map[c] = "close_native"
        elif cl == "volume":
            rename_map[c] = "volume"

    out = out.rename(columns=rename_map)
    out["timestamp_ist"] = out["timestamp_utc"].dt.tz_convert(TZ_NAME)
    out["trade_date_ist"] = session_trade_date_ist(out["timestamp_ist"])

    for c in ["open_native", "high_native", "low_native", "close_native", "volume"]:
        if c not in out.columns:
            out[c] = np.nan

    return out[[
        "timestamp_utc", "timestamp_ist", "trade_date_ist",
        "open_native", "high_native", "low_native", "close_native", "volume"
    ]].dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc")


def _combine_unique_strings(values) -> str:
    vals = [str(x).strip() for x in pd.Series(values).dropna().astype(str).tolist()]
    vals = [x for x in vals if x and x.lower() != "nan"]
    seen = []
    for x in vals:
        if x not in seen:
            seen.append(x)
    return " | ".join(seen)


def _concat_nonempty(frames: List[pd.DataFrame]) -> pd.DataFrame:
    frames = [x for x in frames if x is not None and not x.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def _append_text_series(series: pd.Series, extra: str) -> pd.Series:
    base = pd.Series(series, dtype="string").fillna("").str.strip()
    if not extra:
        return pd.Series(base, index=base.index)

    extra_series = pd.Series([extra] * len(base), index=base.index, dtype="string")
    out = base.where(base.eq(""), base.str.cat(extra_series, sep=" | "))
    out = out.where(~base.eq(""), extra_series)
    return pd.Series(out, index=base.index)


def _target_freq_from_label(timeframe_label: str) -> str:
    return {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "60m": "60min",
    }[timeframe_label]


def get_intraday_candidates(
    product_key: str,
    schedule: pd.DataFrame,
    fx_df: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    candidates: Dict[str, pd.DataFrame] = {}

    for interval, chunk_days, lookback_days in YF_INTERVAL_PLAN:
        raw = _fetch_yf_intraday_interval(
            product_key=product_key,
            interval=interval,
            chunk_days=chunk_days,
            lookback_days=lookback_days,
        )
        if raw.empty:
            continue

        df = apply_schedule_to_1m(raw, schedule, product_key)
        df = apply_fx(df, fx_df)
        df["source_name"] = "yahoo_finance"
        df["source_url"] = "https://finance.yahoo.com"
        df["source_timezone"] = "UTC"

        candidates[interval] = df.sort_values("timestamp_ist").reset_index(drop=True)

    return candidates


def _select_best_rows_for_target_bucket(
    candidates: Dict[str, pd.DataFrame],
    timeframe_label: str,
) -> pd.DataFrame:
    target_minutes = INTERVAL_MINUTES[timeframe_label]
    target_freq = _target_freq_from_label(timeframe_label)

    allowed_labels = [
        k for k in sorted(candidates.keys(), key=lambda x: INTERVAL_MINUTES[x])
        if INTERVAL_MINUTES[k] <= target_minutes and not candidates[k].empty
    ]
    if not allowed_labels:
        return pd.DataFrame()

    selected_frames = []
    taken_keys = set()

    # Pass 1: choose buckets where a source fully covers the target bucket.
    for src_label in allowed_labels:
        src_df = candidates[src_label].copy()
        src_df["bucket_ist"] = src_df["timestamp_ist"].dt.floor(target_freq)

        expected_rows = max(1, target_minutes // INTERVAL_MINUTES[src_label])
        counts = (
            src_df.groupby(["trade_date_ist", "bucket_ist"], dropna=False)
            .size()
            .rename("bucket_row_count")
            .reset_index()
        )
        counts = counts[counts["bucket_row_count"] >= expected_rows].copy()
        if counts.empty:
            continue

        counts["_bucket_key"] = list(zip(counts["trade_date_ist"], counts["bucket_ist"]))
        counts = counts[~counts["_bucket_key"].isin(taken_keys)].copy()
        if counts.empty:
            continue

        tmp = src_df.merge(
            counts[["trade_date_ist", "bucket_ist"]],
            how="inner",
            on=["trade_date_ist", "bucket_ist"],
        )

        tmp["coverage_method"] = _append_text_series(
            tmp["coverage_method"],
            f"bucket_complete_{src_label}_for_{timeframe_label}",
        )

        selected_frames.append(tmp)
        taken_keys.update(counts["_bucket_key"].tolist())

    # Pass 2: if nothing fully covers a remaining bucket, use the finest partial source left.
    for src_label in allowed_labels:
        src_df = candidates[src_label].copy()
        src_df["bucket_ist"] = src_df["timestamp_ist"].dt.floor(target_freq)

        expected_rows = max(1, target_minutes // INTERVAL_MINUTES[src_label])
        counts = (
            src_df.groupby(["trade_date_ist", "bucket_ist"], dropna=False)
            .size()
            .rename("bucket_row_count")
            .reset_index()
        )
        counts = counts[counts["bucket_row_count"] < expected_rows].copy()
        if counts.empty:
            continue

        counts["_bucket_key"] = list(zip(counts["trade_date_ist"], counts["bucket_ist"]))
        counts = counts[~counts["_bucket_key"].isin(taken_keys)].copy()
        if counts.empty:
            continue

        tmp = src_df.merge(
            counts[["trade_date_ist", "bucket_ist"]],
            how="inner",
            on=["trade_date_ist", "bucket_ist"],
        )

        tmp["coverage_method"] = _append_text_series(
            tmp["coverage_method"],
            f"bucket_partial_{src_label}_for_{timeframe_label}",
        )
        tmp["notes_data_quality"] = _append_text_series(
            tmp["notes_data_quality"],
            f"Partial {src_label} coverage used for {timeframe_label} bucket because no fuller finer bucket was available",
        )
        tmp["data_quality_flags"] = _append_text_series(
            tmp["data_quality_flags"],
            f"PARTIAL_{timeframe_label.upper()}_BUCKET_FROM_{src_label.upper()}",
        )

        selected_frames.append(tmp)
        taken_keys.update(counts["_bucket_key"].tolist())

    out = _concat_nonempty(selected_frames)
    if out.empty:
        return out

    return out.sort_values(["trade_date_ist", "bucket_ist", "timestamp_ist"]).reset_index(drop=True)


def build_best_timeframe_bars(
    candidates: Dict[str, pd.DataFrame],
    timeframe_label: str,
) -> pd.DataFrame:
    chosen = _select_best_rows_for_target_bucket(candidates, timeframe_label)
    if chosen.empty:
        return pd.DataFrame()

    agg = (
        chosen.groupby(
            [
                "trade_date_ist", "bucket_ist", "symbol", "instrument_name", "market",
                "contract_logic", "contract_symbol", "contract_expiry_date",
                "rolled_flag", "roll_reference", "currency_native"
            ],
            dropna=False,
        )
        .agg(
            timestamp_original=("timestamp_utc", "first"),
            timestamp_utc=("timestamp_utc", "first"),
            timestamp_ist=("bucket_ist", "first"),
            open_native=("open_native", "first"),
            high_native=("high_native", "max"),
            low_native=("low_native", "min"),
            close_native=("close_native", "last"),
            volume=("volume", "sum"),
            fx_rate_used=("fx_rate_used", "last"),
            open_inr=("open_inr", "first"),
            high_inr=("high_inr", "max"),
            low_inr=("low_inr", "min"),
            close_inr=("close_inr", "last"),
            source_resolution_used=("source_resolution_used", _combine_unique_strings),
            source_resolution_minutes=("source_resolution_minutes", "max"),
            coverage_method=("coverage_method", _combine_unique_strings),
            notes_data_quality=("notes_data_quality", _combine_unique_strings),
            data_quality_flags=("data_quality_flags", _combine_unique_strings),
            source_name=("source_name", "last"),
            source_url=("source_url", "last"),
            source_timezone=("source_timezone", "last"),
        )
        .reset_index(drop=False)
        .sort_values(["trade_date_ist", "timestamp_ist"])
    )

    agg["timeframe"] = timeframe_label
    agg["session_window_ist"] = agg["timestamp_ist"].apply(assign_session_window)
    agg["sub_window_label"] = agg["timestamp_ist"].apply(assign_sub_window)
    return agg.reset_index(drop=True)


def _fetch_yf_intraday_interval(
    product_key: str,
    interval: str,
    chunk_days: int,
    lookback_days: int,
) -> pd.DataFrame:
    cfg = PRODUCTS[product_key]
    ticker = yahoo_ticker(product_key)

    start_ist = pd.Timestamp(START_DATE, tz=TZ_NAME)
    end_ist = pd.Timestamp(END_DATE, tz=TZ_NAME) + pd.Timedelta(days=1)

    now_utc = pd.Timestamp.now("UTC")
    min_allowed_utc = pd.Timestamp.now("UTC") - pd.Timedelta(days=YF_LT1D_LOOKBACK_DAYS)

    requested_start_utc = start_ist.tz_convert("UTC")
    requested_end_utc = end_ist.tz_convert("UTC")

    fetch_start_utc = max(requested_start_utc, min_allowed_utc)
    fetch_end_utc = requested_end_utc

    if fetch_end_utc <= min_allowed_utc:
        return pd.DataFrame()

    frames = []
    chunk_start = fetch_start_utc

    while chunk_start < fetch_end_utc:
        chunk_end = min(chunk_start + pd.Timedelta(days=chunk_days), fetch_end_utc)

        try:
            raw = ticker.history(
                start=chunk_start.tz_localize(None),
                end=chunk_end.tz_localize(None),
                interval=interval,
                auto_adjust=False,
                actions=False,
                prepost=True,
            )
            chunk = _normalize_yf_history(raw)
            if not chunk.empty:
                frames.append(chunk)
        except Exception:
            pass

        chunk_start = chunk_end

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True, sort=False)
    out = out.drop_duplicates(subset=["timestamp_utc"]).sort_values("timestamp_utc")

    out = out[
        (out["timestamp_ist"] >= start_ist) &
        (out["timestamp_ist"] < end_ist)
    ].copy()

    if out.empty:
        return out

    requested_truncated = requested_start_utc < min_allowed_utc

    out["contract_symbol"] = cfg["yahoo_symbol"]
    out["source_resolution_used"] = interval
    out["source_resolution_minutes"] = INTERVAL_MINUTES[interval]
    out["coverage_method"] = "yahoo_intraday_direct"
    out["notes_data_quality"] = np.where(
        requested_truncated,
        f"Yahoo {interval} history truncated by provider lookback window",
        ""
    )
    out["data_quality_flags"] = np.where(
        requested_truncated,
        f"YF_{interval.upper()}_LOOKBACK_TRUNCATED",
        ""
    )
    return out.reset_index(drop=True)


def get_daily_bars(product_key: str) -> pd.DataFrame:
    cfg = PRODUCTS[product_key]
    ticker = yahoo_ticker(product_key)

    raw = ticker.history(
        start=START_DATE,
        end=(pd.Timestamp(END_DATE) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=False,
        actions=False,
    )
    out = _normalize_yf_history(raw)
    if out.empty:
        return out

    out["contract_symbol"] = cfg["yahoo_symbol"]
    return out

# ============================================================
# BAR FETCH + RESAMPLING
# ============================================================

def apply_schedule_to_1m(base_1m: pd.DataFrame, schedule: pd.DataFrame, product_key: str) -> pd.DataFrame:
    if base_1m.empty:
        return pd.DataFrame()

    cfg = PRODUCTS[product_key]
    df = base_1m.copy()
    df["symbol"] = product_key
    df["instrument_name"] = cfg["instrument_name"]
    df["market"] = cfg["market"]
    df["currency_native"] = cfg["currency_native"]
    df["contract_logic"] = "yahoo_front_symbol_no_verified_roll_metadata"
    df["contract_expiry_date"] = pd.NaT
    df["rolled_flag"] = False
    df["roll_reference"] = ""
    return df.sort_values("timestamp_ist")

def resample_from_1m(df_1m: pd.DataFrame, freq: str, timeframe_label: str) -> pd.DataFrame:
    if df_1m.empty:
        return pd.DataFrame()

    target_minutes = INTERVAL_MINUTES[timeframe_label]
    df = df_1m.copy()

    if "source_resolution_minutes" in df.columns:
        df = df[df["source_resolution_minutes"] <= target_minutes].copy()

    if df.empty:
        return pd.DataFrame()

    df["bucket_ist"] = df["timestamp_ist"].dt.floor(freq)

    agg = (
        df.groupby(
            [
                "trade_date_ist", "bucket_ist", "symbol", "instrument_name", "market",
                "contract_logic", "contract_symbol", "contract_expiry_date", "rolled_flag",
                "roll_reference", "currency_native"
            ],
            dropna=False
        )
        .agg(
            timestamp_original=("timestamp_utc", "first"),
            timestamp_ist=("bucket_ist", "first"),
            open_native=("open_native", "first"),
            high_native=("high_native", "max"),
            low_native=("low_native", "min"),
            close_native=("close_native", "last"),
            volume=("volume", "sum"),
            fx_rate_used=("fx_rate_used", "last"),
            open_inr=("open_inr", "first"),
            high_inr=("high_inr", "max"),
            low_inr=("low_inr", "min"),
            close_inr=("close_inr", "last"),
            source_resolution_used=("source_resolution_used", _combine_unique_strings),
            source_resolution_minutes=("source_resolution_minutes", "max"),
            coverage_method=("coverage_method", _combine_unique_strings),
            notes_data_quality=("notes_data_quality", _combine_unique_strings),
            data_quality_flags=("data_quality_flags", _combine_unique_strings),
        )
        .reset_index(drop=False)
    )

    agg["timeframe"] = timeframe_label
    agg["source_name"] = "yahoo_finance"
    agg["source_url"] = "https://finance.yahoo.com"
    agg["source_timezone"] = "UTC"
    agg["session_window_ist"] = agg["timestamp_ist"].apply(assign_session_window)
    agg["sub_window_label"] = agg["timestamp_ist"].apply(assign_sub_window)
    return agg


def build_daily_from_1m(df_1m: pd.DataFrame) -> pd.DataFrame:
    if df_1m.empty:
        return pd.DataFrame()

    daily = (
        df_1m.groupby(
            [
                "trade_date_ist", "symbol", "instrument_name", "market",
                "contract_logic", "contract_symbol", "contract_expiry_date",
                "rolled_flag", "roll_reference", "currency_native"
            ],
            dropna=False
        )
        .agg(
            open_native=("open_native", "first"),
            high_native=("high_native", "max"),
            low_native=("low_native", "min"),
            close_native=("close_native", "last"),
            volume=("volume", "sum"),
            fx_rate_used=("fx_rate_used", "last"),
            open_inr=("open_inr", "first"),
            high_inr=("high_inr", "max"),
            low_inr=("low_inr", "min"),
            close_inr=("close_inr", "last"),
            open_time_original=("timestamp_utc", "first"),
            close_time_original=("timestamp_utc", "last"),
            open_time_ist=("timestamp_ist", "first"),
            close_time_ist=("timestamp_ist", "last"),
            source_resolution_used=("source_resolution_used", _combine_unique_strings),
            source_resolution_minutes=("source_resolution_minutes", "max"),
            coverage_method=("coverage_method", _combine_unique_strings),
            notes_data_quality=("notes_data_quality", _combine_unique_strings),
            data_quality_flags=("data_quality_flags", _combine_unique_strings),
        )
        .reset_index()
        .sort_values("trade_date_ist")
    )

    daily["source_name"] = "yahoo_finance"
    daily["source_url"] = "https://finance.yahoo.com"
    daily["source_timezone"] = "UTC"
    return daily


def merge_intraday_daily_with_fallback(
    intraday_for_daily: pd.DataFrame,
    product_key: str,
    schedule: pd.DataFrame,
    fx_df: pd.DataFrame,
) -> pd.DataFrame:
    intraday_daily = build_daily_from_1m(intraday_for_daily) if not intraday_for_daily.empty else pd.DataFrame()

    daily_src = get_daily_bars(product_key)
    if daily_src.empty:
        return intraday_daily.sort_values("trade_date_ist").reset_index(drop=True) if not intraday_daily.empty else pd.DataFrame()

    fallback = apply_schedule_to_1m(daily_src, schedule, product_key)
    fallback["open_time_original"] = fallback["timestamp_utc"]
    fallback["close_time_original"] = fallback["timestamp_utc"]
    fallback["open_time_ist"] = fallback["timestamp_ist"]
    fallback["close_time_ist"] = fallback["timestamp_ist"]

    fallback = (
        fallback.groupby(
            [
                "trade_date_ist", "symbol", "instrument_name", "market", "contract_logic",
                "contract_symbol", "contract_expiry_date", "rolled_flag", "roll_reference",
                "currency_native"
            ],
            dropna=False
        )
        .agg(
            open_native=("open_native", "first"),
            high_native=("high_native", "max"),
            low_native=("low_native", "min"),
            close_native=("close_native", "last"),
            volume=("volume", "sum"),
            open_time_original=("open_time_original", "first"),
            close_time_original=("close_time_original", "last"),
            open_time_ist=("open_time_ist", "first"),
            close_time_ist=("close_time_ist", "last"),
        )
        .reset_index()
        .sort_values("trade_date_ist")
    )

    fallback["source_name"] = "yahoo_finance"
    fallback["source_url"] = "https://finance.yahoo.com"
    fallback["source_timezone"] = "UTC"
    fallback["source_resolution_used"] = "1d"
    fallback["source_resolution_minutes"] = INTERVAL_MINUTES["1d"]
    fallback["coverage_method"] = "yahoo_daily_endpoint_fallback"
    fallback["notes_data_quality"] = "Daily fallback used because no intraday bucket coverage was available for this trade date"
    fallback["data_quality_flags"] = "DAILY_FALLBACK_NO_INTRADAY"

    fallback = apply_fx(fallback, fx_df)

    if intraday_daily.empty:
        return fallback.sort_values("trade_date_ist").reset_index(drop=True)

    covered_dates = set(pd.Series(intraday_daily["trade_date_ist"]).dropna().tolist())
    fallback_only = fallback[~fallback["trade_date_ist"].isin(covered_dates)].copy()

    out = pd.concat([intraday_daily, fallback_only], ignore_index=True, sort=False)
    return out.sort_values("trade_date_ist").reset_index(drop=True)

# ============================================================
# FX / INR
# ============================================================

def get_usdinr_reference() -> pd.DataFrame:
    if FRED_USDINR_SERIES_ID:
        fx = fred_series(FRED_USDINR_SERIES_ID).rename(columns={"value": "fx_rate"})
        if not fx.empty:
            return fx[["trade_date_ist", "fx_rate"]]
    return pd.DataFrame(columns=["trade_date_ist", "fx_rate"])

def apply_fx(df: pd.DataFrame, fx_df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.merge(fx_df, how="left", on="trade_date_ist")

    if "fx_rate" in out.columns:
        fx_rate_series = pd.to_numeric(out["fx_rate"], errors="coerce")
    else:
        fx_rate_series = pd.Series(np.nan, index=out.index, dtype="float64")

    out["fx_rate_used"] = fx_rate_series

    for col in ["open_native", "high_native", "low_native", "close_native"]:
        out[col.replace("_native", "_inr")] = pd.to_numeric(out[col], errors="coerce") * out["fx_rate_used"]

    if "fx_rate" in out.columns:
        out = out.drop(columns=["fx_rate"])

    return out

# ============================================================
# DERIVED FEATURES
# ============================================================

def add_daily_features(daily: pd.DataFrame, intraday_1m: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily

    df = daily.copy().sort_values("trade_date_ist").reset_index(drop=True)
    df["prior_trading_day_close_native"] = df["close_native"].shift(1)
    df["prior_trading_day_close_inr"] = df["close_inr"].shift(1)

    df["did_gap_up"] = df["open_native"] > df["prior_trading_day_close_native"]
    df["did_gap_down"] = df["open_native"] < df["prior_trading_day_close_native"]
    df["gap_abs_native"] = df["open_native"] - df["prior_trading_day_close_native"]
    df["gap_pct_native"] = pct(df["open_native"], df["prior_trading_day_close_native"])
    df["gap_abs_inr"] = df["open_inr"] - df["prior_trading_day_close_inr"]
    df["gap_pct_inr"] = pct(df["open_inr"], df["prior_trading_day_close_inr"])
    df["extreme_gap_flag"] = df["gap_pct_native"].abs() >= 2.0
    df["extreme_gap_threshold_method"] = "abs_gap_pct_native>=2.0"

    df["day_range_abs_native"] = df["high_native"] - df["low_native"]
    df["day_range_pct_native"] = pct(df["high_native"], df["open_native"]) - pct(df["low_native"], df["open_native"])
    df["day_range_abs_inr"] = df["high_inr"] - df["low_inr"]
    df["day_range_pct_inr"] = pct(df["high_inr"], df["open_inr"]) - pct(df["low_inr"], df["open_inr"])

    body = df["close_native"] - df["open_native"]
    df["body_abs_native"] = body.abs()
    df["body_pct_native"] = df["body_abs_native"] / df["open_native"] * 100.0
    df["body_direction"] = np.where(body > 0, "UP", np.where(body < 0, "DOWN", "FLAT"))

    df["upper_wick_abs_native"] = df["high_native"] - df[["open_native", "close_native"]].max(axis=1)
    df["lower_wick_abs_native"] = df[["open_native", "close_native"]].min(axis=1) - df["low_native"]
    rng = (df["high_native"] - df["low_native"]).replace(0, np.nan)
    df["close_location_in_range_pct"] = (df["close_native"] - df["low_native"]) / rng * 100.0
    df["closed_green"] = df["close_native"] > df["open_native"]
    df["closed_red"] = df["close_native"] < df["open_native"]

    df["prior_high"] = df["high_native"].shift(1)
    df["prior_low"] = df["low_native"].shift(1)
    df["inside_day_flag"] = (df["high_native"] <= df["prior_high"]) & (df["low_native"] >= df["prior_low"])
    df["outside_day_flag"] = (df["high_native"] >= df["prior_high"]) & (df["low_native"] <= df["prior_low"])
    df["doji_like_flag"] = df["body_abs_native"] <= (df["day_range_abs_native"] * 0.1)
    df["net_day_return_pct"] = pct(df["close_native"], df["open_native"])
    df["overnight_to_close_return_pct"] = pct(df["close_native"], df["prior_trading_day_close_native"])

    if not session_summary.empty:
        piv = session_summary.pivot(index="trade_date_ist", columns="session_window_ist", values="close_native")
        for c in ["europe_open", "us_open", "us_late"]:
            if c not in piv.columns:
                piv[c] = np.nan
        piv = piv.reset_index()
        df = df.merge(piv[["trade_date_ist", "europe_open", "us_open", "us_late"]], how="left", on="trade_date_ist")
        df["europe_to_us_return_pct"] = pct(df["us_open"], df["europe_open"])
        df["us_to_settlement_return_pct"] = pct(df["close_native"], df["us_open"])
    else:
        df["europe_to_us_return_pct"] = np.nan
        df["us_to_settlement_return_pct"] = np.nan

    if not intraday_1m.empty:
        idf = intraday_1m.copy()
        out_rows = []
        for d, g in idf.groupby("trade_date_ist"):
            g = g.sort_values("timestamp_ist")
            o = g["open_native"].iloc[0]
            h = g["high_native"].max()
            l = g["low_native"].min()
            c = g["close_native"].iloc[-1]
            oi = g["open_inr"].iloc[0] if "open_inr" in g.columns else np.nan
            hi = g["high_inr"].max() if "high_inr" in g.columns else np.nan
            li = g["low_inr"].min() if "low_inr" in g.columns else np.nan
            ci = g["close_inr"].iloc[-1] if "close_inr" in g.columns else np.nan

            eur = g[(g["timestamp_ist"].dt.hour == 15) & (g["timestamp_ist"].dt.minute < 60)]
            us = g[(g["timestamp_ist"].dt.hour == 21) & (g["timestamp_ist"].dt.minute < 60)]
            first_hour = g[(g["timestamp_ist"] >= g["timestamp_ist"].min()) & (g["timestamp_ist"] < g["timestamp_ist"].min() + pd.Timedelta(hours=1))]

            ret_1m = g["close_native"].pct_change().dropna()
            rv = ret_1m.std() * np.sqrt(len(ret_1m)) * 100.0 if len(ret_1m) > 1 else np.nan

            out_rows.append({
                "trade_date_ist": d,
                "intraday_reversal_flag": (c - o) * (g["close_native"].iloc[0] - o if len(g) > 1 else 0) < 0,
                "reversal_strength_score_1_to_5": np.nan,
                "follow_through_vs_gap_flag": np.nan,
                "max_favorable_excursion_pct": ((h - o) / o * 100.0) if pd.notna(o) and o != 0 else np.nan,
                "max_adverse_excursion_pct": ((l - o) / o * 100.0) if pd.notna(o) and o != 0 else np.nan,
                "realized_vol_proxy": rv,
                "day_efficiency_ratio": abs(c - o) / (h - l) if (h - l) != 0 else np.nan,
                "first_hour_range_inr": (first_hour["high_inr"].max() - first_hour["low_inr"].min()) if not first_hour.empty and "high_inr" in first_hour.columns else np.nan,
                "europe_open_hour_range_inr": (eur["high_inr"].max() - eur["low_inr"].min()) if not eur.empty and "high_inr" in eur.columns else np.nan,
                "us_open_hour_range_inr": (us["high_inr"].max() - us["low_inr"].min()) if not us.empty and "high_inr" in us.columns else np.nan,
                "full_day_range_inr": (hi - li) if pd.notna(hi) and pd.notna(li) else np.nan,
                "25pct_range_inr": ((hi - li) * 0.25) if pd.notna(hi) and pd.notna(li) else np.nan,
                "50pct_range_inr": ((hi - li) * 0.50) if pd.notna(hi) and pd.notna(li) else np.nan,
                "75pct_range_inr": ((hi - li) * 0.75) if pd.notna(hi) and pd.notna(li) else np.nan,
                "max_up_move_from_open_inr": (hi - oi) if pd.notna(hi) and pd.notna(oi) else np.nan,
                "max_down_move_from_open_inr": (li - oi) if pd.notna(li) and pd.notna(oi) else np.nan,
                "max_up_move_from_open_pct": ((h - o) / o * 100.0) if pd.notna(h) and pd.notna(o) and o != 0 else np.nan,
                "max_down_move_from_open_pct": ((l - o) / o * 100.0) if pd.notna(l) and pd.notna(o) and o != 0 else np.nan,
                "close_from_open_inr": (ci - oi) if pd.notna(ci) and pd.notna(oi) else np.nan,
                "close_from_open_pct": ((c - o) / o * 100.0) if pd.notna(c) and pd.notna(o) and o != 0 else np.nan,
                "mfe_inr": (hi - oi) if pd.notna(hi) and pd.notna(oi) else np.nan,
                "mae_inr": (li - oi) if pd.notna(li) and pd.notna(oi) else np.nan,
                "mfe_pct": ((h - o) / o * 100.0) if pd.notna(h) and pd.notna(o) and o != 0 else np.nan,
                "mae_pct": ((l - o) / o * 100.0) if pd.notna(l) and pd.notna(o) and o != 0 else np.nan,
            })
        extras = pd.DataFrame(out_rows)
        df = df.merge(extras, how="left", on="trade_date_ist")
    else:
        for c in [
            "intraday_reversal_flag","reversal_strength_score_1_to_5","follow_through_vs_gap_flag",
            "max_favorable_excursion_pct","max_adverse_excursion_pct","realized_vol_proxy","day_efficiency_ratio",
            "first_hour_range_inr","europe_open_hour_range_inr","us_open_hour_range_inr","full_day_range_inr",
            "25pct_range_inr","50pct_range_inr","75pct_range_inr","max_up_move_from_open_inr","max_down_move_from_open_inr",
            "max_up_move_from_open_pct","max_down_move_from_open_pct","close_from_open_inr","close_from_open_pct",
            "mfe_inr","mae_inr","mfe_pct","mae_pct"
        ]:
            df[c] = np.nan

    eff = df["day_efficiency_ratio"]
    df["trendiness_score_1_to_5"] = np.select([eff >= 0.75, eff >= 0.50, eff >= 0.25], [5, 4, 3], default=2)
    df["whipsaw_score_1_to_5"] = np.select([eff < 0.20, eff < 0.35, eff < 0.50], [5, 4, 3], default=2)

    invalid = (
        (df["high_native"] < df["open_native"]) |
        (df["high_native"] < df["close_native"]) |
        (df["low_native"] > df["open_native"]) |
        (df["low_native"] > df["close_native"]) |
        (df["high_native"] < df["low_native"])
    )
    df.loc[invalid, "data_quality_flags"] = "INVALID_OHLC"
    return df.drop(columns=[c for c in ["prior_high", "prior_low"] if c in df.columns])

def session_summary(intraday: pd.DataFrame, symbol: str, timeframe_used: str) -> pd.DataFrame:
    if intraday.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist","symbol","timeframe_used","session_window_ist","open_native","high_native","low_native","close_native",
            "open_inr","high_inr","low_inr","close_inr","session_return_pct","session_range_pct","session_body_direction",
            "session_close_location_pct","session_reversal_flag","session_breakout_flag","session_failed_breakout_flag",
            "session_trend_strength_score_1_to_5","session_whipsaw_score_1_to_5","session_notes_short","data_quality_flags"
        ])
    rows = []
    for (d, win), g in intraday.groupby(["trade_date_ist", "session_window_ist"]):
        g = g.sort_values("timestamp_ist")
        o, h, l, c = g["open_native"].iloc[0], g["high_native"].max(), g["low_native"].min(), g["close_native"].iloc[-1]
        oi = g["open_inr"].iloc[0] if "open_inr" in g.columns else np.nan
        hi = g["high_inr"].max() if "high_inr" in g.columns else np.nan
        li = g["low_inr"].min() if "low_inr" in g.columns else np.nan
        ci = g["close_inr"].iloc[-1] if "close_inr" in g.columns else np.nan
        rng = h - l
        eff = abs(c - o) / rng if rng else np.nan
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
            "session_return_pct": ((c - o) / o * 100.0) if o else np.nan,
            "session_range_pct": ((h - l) / o * 100.0) if o else np.nan,
            "session_body_direction": "UP" if c > o else ("DOWN" if c < o else "FLAT"),
            "session_close_location_pct": ((c - l) / rng * 100.0) if rng else np.nan,
            "session_reversal_flag": False,
            "session_breakout_flag": False,
            "session_failed_breakout_flag": False,
            "session_trend_strength_score_1_to_5": 5 if pd.notna(eff) and eff >= 0.75 else 3 if pd.notna(eff) and eff >= 0.4 else 2,
            "session_whipsaw_score_1_to_5": 5 if pd.notna(eff) and eff < 0.2 else 2,
            "session_notes_short": "",
            "data_quality_flags": ""
        })
    return pd.DataFrame(rows)

def day_master_summary(wti_daily: pd.DataFrame, brent_daily: pd.DataFrame) -> pd.DataFrame:
    if wti_daily is None or wti_daily.empty:
        a = pd.DataFrame(columns=["trade_date_ist"])
    else:
        a = wti_daily.add_prefix("wti_").rename(columns={"wti_trade_date_ist": "trade_date_ist"})

    if brent_daily is None or brent_daily.empty:
        b = pd.DataFrame(columns=["trade_date_ist"])
    else:
        b = brent_daily.add_prefix("brent_").rename(columns={"brent_trade_date_ist": "trade_date_ist"})

    df = pd.merge(a, b, how="outer", on="trade_date_ist").sort_values("trade_date_ist")

    for c in [
        "brent_close_native", "wti_close_native",
        "brent_close_inr", "wti_close_inr",
        "brent_gap_pct_native", "wti_gap_pct_native"
    ]:
        if c not in df.columns:
            df[c] = np.nan

    df["brent_minus_wti_close_spread_native"] = df["brent_close_native"] - df["wti_close_native"]
    df["brent_minus_wti_close_spread_inr"] = df["brent_close_inr"] - df["wti_close_inr"]
    df["brent_minus_wti_gap_spread_if_matchable"] = df["brent_gap_pct_native"] - df["wti_gap_pct_native"]
    df["lead_lag_hint_short"] = ""
    df["session_bias_observed_short"] = ""
    return df

def price_bucket(o, h, l, c):
    if pd.isna(o) or pd.isna(h) or pd.isna(l) or pd.isna(c):
        return ""
    rng = h - l
    if rng <= 0:
        return "range_chop"
    body = c - o
    cloc = (c - l) / rng
    if body > 0 and cloc > 0.75:
        return "all_day_trend_up"
    if body < 0 and cloc < 0.25:
        return "all_day_trend_down"
    if abs(body) <= rng * 0.1:
        return "range_chop"
    return "mixed_regime_day"

def build_day_type_labels(master: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in master.iterrows():
        rows.append({
            "trade_date_ist": r["trade_date_ist"],
            "symbol_focus": "combined",
            "geo_bucket_primary": "",
            "geo_bucket_secondary": "",
            "price_path_bucket_primary": price_bucket(r.get("wti_open_native"), r.get("wti_high_native"), r.get("wti_low_native"), r.get("wti_close_native")),
            "price_path_bucket_secondary": "",
            "bucket_confidence_1_to_5": 2,
            "why_this_bucket_short": "price_derived_only",
            "main_evidence_short": "daily_intraday_bar_features",
            "deviation_from_recent_pattern_flag": False,
            "deviation_type_short": ""
        })
    return pd.DataFrame(rows)

def build_deviation_labels(day_labels: pd.DataFrame) -> pd.DataFrame:
    if day_labels.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist","expected_pattern_based_on_prior_5_days","actual_pattern_observed","deviation_flag",
            "deviation_severity_1_to_5","likely_reason_for_deviation","related_news_event_id_if_any",
            "did_deviation_still_follow_an_alternate_repeatable_pattern","alternate_pattern_short"
        ])
    out = []
    vals = day_labels["price_path_bucket_primary"].tolist()
    for i, (_, r) in enumerate(day_labels.iterrows()):
        prior = vals[max(0, i-5):i]
        expected = pd.Series(prior).mode().iloc[0] if prior else ""
        actual = r["price_path_bucket_primary"]
        dev = expected != "" and actual != expected
        out.append({
            "trade_date_ist": r["trade_date_ist"],
            "expected_pattern_based_on_prior_5_days": expected,
            "actual_pattern_observed": actual,
            "deviation_flag": dev,
            "deviation_severity_1_to_5": 3 if dev else 1,
            "likely_reason_for_deviation": "",
            "related_news_event_id_if_any": "",
            "did_deviation_still_follow_an_alternate_repeatable_pattern": False,
            "alternate_pattern_short": ""
        })
    return pd.DataFrame(out)

def build_day_window_matrix(session_df: pd.DataFrame, day_labels: pd.DataFrame) -> pd.DataFrame:
    if session_df.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist","geo_bucket_primary","price_path_bucket_primary","europe_open_direction","europe_mid_direction",
            "us_open_direction","us_late_direction","did_europe_open_set_day_high_flag","did_europe_open_set_day_low_flag",
            "did_us_open_extend_europe_flag","did_us_open_reverse_europe_flag","strongest_window_of_day","weakest_window_of_day","window_sequence_short"
        ])
    rows = []
    for d, g in session_df.groupby("trade_date_ist"):
        label = day_labels[day_labels["trade_date_ist"].eq(d)]
        by = {r["session_window_ist"]: r for _, r in g.iterrows()}
        strongest = g.assign(absret=g["session_return_pct"].abs()).sort_values("absret", ascending=False)["session_window_ist"].iloc[0] if not g.empty else ""
        weakest = g.assign(absret=g["session_return_pct"].abs()).sort_values("absret", ascending=True)["session_window_ist"].iloc[0] if not g.empty else ""
        rows.append({
            "trade_date_ist": d,
            "geo_bucket_primary": label["geo_bucket_primary"].iloc[0] if not label.empty else "",
            "price_path_bucket_primary": label["price_path_bucket_primary"].iloc[0] if not label.empty else "",
            "europe_open_direction": by["europe_open"]["session_body_direction"] if "europe_open" in by else "",
            "europe_mid_direction": by["europe_mid"]["session_body_direction"] if "europe_mid" in by else "",
            "us_open_direction": by["us_open"]["session_body_direction"] if "us_open" in by else "",
            "us_late_direction": by["us_late"]["session_body_direction"] if "us_late" in by else "",
            "did_europe_open_set_day_high_flag": np.nan,
            "did_europe_open_set_day_low_flag": np.nan,
            "did_us_open_extend_europe_flag": np.nan,
            "did_us_open_reverse_europe_flag": np.nan,
            "strongest_window_of_day": strongest,
            "weakest_window_of_day": weakest,
            "window_sequence_short": " -> ".join([w for w in ["asia_early","europe_open","europe_mid","us_pre_open","us_open","us_late"] if w in set(g["session_window_ist"])])
        })
    return pd.DataFrame(rows)

def build_archetype_features(master: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date_ist": master["trade_date_ist"] if not master.empty else [],
        "wti_gap_pct": master.get("wti_gap_pct_native", pd.Series(dtype=float)),
        "wti_range_pct": master.get("wti_day_range_pct_native", pd.Series(dtype=float)),
        "wti_close_location_in_range_pct": master.get("wti_close_location_in_range_pct", pd.Series(dtype=float)),
        "brent_gap_pct": master.get("brent_gap_pct_native", pd.Series(dtype=float)),
        "brent_range_pct": master.get("brent_day_range_pct_native", pd.Series(dtype=float)),
        "brent_close_location_in_range_pct": master.get("brent_close_location_in_range_pct", pd.Series(dtype=float)),
        "europe_open_hour_range_inr": master.get("wti_europe_open_hour_range_inr", pd.Series(dtype=float)),
        "us_open_hour_range_inr": master.get("wti_us_open_hour_range_inr", pd.Series(dtype=float)),
        "trendiness_score": master.get("wti_trendiness_score_1_to_5", pd.Series(dtype=float)),
        "whipsaw_score": master.get("wti_whipsaw_score_1_to_5", pd.Series(dtype=float)),
        "rhetoric_intensity_score": np.nan,
        "shipping_risk_score": np.nan,
        "physical_supply_risk_score": np.nan,
        "day_type_vector_json": "{}"
    })

def build_scenario_backtest(intraday_1m: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if intraday_1m.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist","hypothetical_long_entry_at_first_major_window","hypothetical_short_entry_at_first_major_window",
            "max_profit_long_inr","max_loss_long_inr","max_profit_short_inr","max_loss_short_inr",
            "whether_1R_hit_long","whether_2R_hit_long","whether_3R_hit_long",
            "whether_1R_hit_short","whether_2R_hit_short","whether_3R_hit_short",
            "time_to_1R_long_minutes","time_to_2R_long_minutes","time_to_3R_long_minutes",
            "time_to_1R_short_minutes","time_to_2R_short_minutes","time_to_3R_short_minutes"
        ])
    rows = []
    for d, g in intraday_1m.groupby("trade_date_ist"):
        g = g.sort_values("timestamp_ist")
        entry = g["open_inr"].iloc[0] if "open_inr" in g.columns else np.nan
        hi = g["high_inr"].max() if "high_inr" in g.columns else np.nan
        lo = g["low_inr"].min() if "low_inr" in g.columns else np.nan
        r = (g["high_inr"].max() - g["low_inr"].min()) * 0.25 if "high_inr" in g.columns else np.nan
        rows.append({
            "trade_date_ist": d,
            "hypothetical_long_entry_at_first_major_window": entry,
            "hypothetical_short_entry_at_first_major_window": entry,
            "max_profit_long_inr": hi - entry if pd.notna(hi) and pd.notna(entry) else np.nan,
            "max_loss_long_inr": lo - entry if pd.notna(lo) and pd.notna(entry) else np.nan,
            "max_profit_short_inr": entry - lo if pd.notna(lo) and pd.notna(entry) else np.nan,
            "max_loss_short_inr": entry - hi if pd.notna(hi) and pd.notna(entry) else np.nan,
            "whether_1R_hit_long": (hi - entry) >= r if pd.notna(hi) and pd.notna(entry) and pd.notna(r) else np.nan,
            "whether_2R_hit_long": (hi - entry) >= 2*r if pd.notna(hi) and pd.notna(entry) and pd.notna(r) else np.nan,
            "whether_3R_hit_long": (hi - entry) >= 3*r if pd.notna(hi) and pd.notna(entry) and pd.notna(r) else np.nan,
            "whether_1R_hit_short": (entry - lo) >= r if pd.notna(lo) and pd.notna(entry) and pd.notna(r) else np.nan,
            "whether_2R_hit_short": (entry - lo) >= 2*r if pd.notna(lo) and pd.notna(entry) and pd.notna(r) else np.nan,
            "whether_3R_hit_short": (entry - lo) >= 3*r if pd.notna(lo) and pd.notna(entry) and pd.notna(r) else np.nan,
            "time_to_1R_long_minutes": np.nan,
            "time_to_2R_long_minutes": np.nan,
            "time_to_3R_long_minutes": np.nan,
            "time_to_1R_short_minutes": np.nan,
            "time_to_2R_short_minutes": np.nan,
            "time_to_3R_short_minutes": np.nan,
        })
    return pd.DataFrame(rows)

def build_intraday_excursions(intraday_1m: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if intraday_1m.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist","symbol","session_window_ist","direction_reference","max_favorable_excursion_inr",
            "max_adverse_excursion_inr","time_to_mfe_minutes","time_to_mae_minutes","close_vs_entry_inr","close_vs_entry_pct"
        ])
    tmp = intraday_1m.copy()
    tmp["session_window_ist"] = tmp["timestamp_ist"].apply(assign_session_window)
    rows = []
    for (d, w), g in tmp.groupby(["trade_date_ist", "session_window_ist"]):
        g = g.sort_values("timestamp_ist")
        entry = g["open_inr"].iloc[0] if "open_inr" in g.columns else np.nan
        close = g["close_inr"].iloc[-1] if "close_inr" in g.columns else np.nan
        hi = g["high_inr"].max() if "high_inr" in g.columns else np.nan
        lo = g["low_inr"].min() if "low_inr" in g.columns else np.nan
        rows.append({
            "trade_date_ist": d,
            "symbol": symbol,
            "session_window_ist": w,
            "direction_reference": "long",
            "max_favorable_excursion_inr": hi - entry if pd.notna(hi) and pd.notna(entry) else np.nan,
            "max_adverse_excursion_inr": lo - entry if pd.notna(lo) and pd.notna(entry) else np.nan,
            "time_to_mfe_minutes": np.nan,
            "time_to_mae_minutes": np.nan,
            "close_vs_entry_inr": close - entry if pd.notna(close) and pd.notna(entry) else np.nan,
            "close_vs_entry_pct": ((close - entry) / entry * 100.0) if pd.notna(close) and pd.notna(entry) and entry != 0 else np.nan
        })
    return pd.DataFrame(rows)

# ============================================================
# OUTPUT SCHEMA FINALIZERS
# ============================================================

def finalize_intraday(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "timestamp_original","timestamp_ist","trade_date_ist","symbol","instrument_name","market","timeframe", "source_resolution_used","source_resolution_minutes","coverage_method",
        "contract_logic","contract_symbol","source_name","source_url","source_timezone","open_native","high_native",
        "low_native","close_native","volume","currency_native","open_inr","high_inr","low_inr","close_inr","fx_rate_used",
        "session_window_ist","sub_window_label","notes_data_quality","data_quality_flags"
    ]
    if df.empty:
        return pd.DataFrame(columns=cols)
    out = df.copy()
    out["timestamp_original"] = out["timestamp_original"].astype(str)
    out["timestamp_ist"] = out["timestamp_ist"].astype(str)
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    return out[cols]

def finalize_daily(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "trade_date_ist","symbol","instrument_name","market","contract_logic","contract_symbol","contract_expiry_date",
        "rolled_flag","roll_reference","source_name","source_url","source_timezone", "source_resolution_used","source_resolution_minutes","coverage_method",
        "open_native","high_native","low_native",
        "close_native","volume","currency_native","open_inr","high_inr","low_inr","close_inr","fx_rate_used","open_time_original",
        "open_time_ist","close_time_original","close_time_ist","prior_trading_day_close_native","prior_trading_day_close_inr",
        "notes_data_quality","data_quality_flags","did_gap_up","did_gap_down","gap_abs_native","gap_pct_native","gap_abs_inr",
        "gap_pct_inr","extreme_gap_flag","extreme_gap_threshold_method","day_range_abs_native","day_range_pct_native",
        "day_range_abs_inr","day_range_pct_inr","body_abs_native","body_pct_native","body_direction","upper_wick_abs_native",
        "lower_wick_abs_native","close_location_in_range_pct","closed_green","closed_red","inside_day_flag","outside_day_flag",
        "doji_like_flag","intraday_reversal_flag","reversal_strength_score_1_to_5","follow_through_vs_gap_flag","net_day_return_pct",
        "overnight_to_close_return_pct","europe_to_us_return_pct","us_to_settlement_return_pct","max_favorable_excursion_pct",
        "max_adverse_excursion_pct","realized_vol_proxy","day_efficiency_ratio","trendiness_score_1_to_5","whipsaw_score_1_to_5",
        "first_hour_range_inr","europe_open_hour_range_inr","us_open_hour_range_inr","full_day_range_inr","25pct_range_inr",
        "50pct_range_inr","75pct_range_inr","max_up_move_from_open_inr","max_down_move_from_open_inr","max_up_move_from_open_pct",
        "max_down_move_from_open_pct","close_from_open_inr","close_from_open_pct","mfe_inr","mae_inr","mfe_pct","mae_pct"
    ]
    if df.empty:
        return pd.DataFrame(columns=cols)
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    for c in ["open_time_original","open_time_ist","close_time_original","close_time_ist"]:
        out[c] = out[c].astype(str)
    return out[cols]

# ============================================================
# METHODOLOGY + MAIN
# ============================================================

def write_methodology(file_rows: List[dict], coverage_notes: Dict[str, str]):
    lines = []
    lines.append("# methodology_and_sources")
    lines.append("")
    lines.append(f"- requested_date_range: {START_DATE} to {END_DATE}")
    lines.append("- instruments: WTI crude futures (CL root), Brent crude futures (BZ root)")
    lines.append("- market_bar_source: Yahoo Finance via yfinance")
    lines.append("- reference_sources: FRED, EIA")
    lines.append("- timezone_logic: all exported timestamps normalized to Asia/Kolkata")
    lines.append("- trade_date_logic: session day anchored at 03:30 IST so post-midnight IST bars remain on the prior session date")
    lines.append("- roll_logic: no verified contract-level roll metadata available from Yahoo fallback; front-symbol continuity only")
    lines.append("- bar_construction: best-available Yahoo bars used by target bucket in priority order 1m -> 5m -> 15m -> 60m, with Yahoo daily endpoint fallback only where " \
        "no intraday bucket coverage was available for the trade date; output rows carry source_resolution_used/source_resolution_minutes labels")
    lines.append("- missing_bar_policy: no synthetic fill rows")
    lines.append("- notes: news/rhetoric/event files require separate verified news ingestion")
    lines.append("")
    lines.append("## file_summary")
    for row in file_rows:
        lines.append(f"- {row['file_name']} | rows={row['row_count']} | coverage={row['coverage_start']} -> {row['coverage_end']} | note={row['note']}")
    lines.append("")
    lines.append("## coverage_notes")
    for k, v in coverage_notes.items():
        lines.append(f"- {k}: {v}")
    (OUTPUT_DIR / "methodology_and_sources.md").write_text("\n".join(lines), encoding="utf-8")

def file_row(filename: str, df: pd.DataFrame, note: str) -> dict:
    if df is None or df.empty:
        return {"file_name": filename, "row_count": 0, "coverage_start": "", "coverage_end": "", "note": note}
    dc = "trade_date_ist" if "trade_date_ist" in df.columns else ("timestamp_ist" if "timestamp_ist" in df.columns else None)
    if dc is None:
        return {"file_name": filename, "row_count": len(df), "coverage_start": "", "coverage_end": "", "note": note}
    return {"file_name": filename, "row_count": len(df), "coverage_start": str(df[dc].min()), "coverage_end": str(df[dc].max()), "note": note}

def main():
    file_rows = []
    coverage_notes = {}

    ensure_input_templates()

    # Reference layers
    wti_spot = fred_series(FRED_WTI_SERIES_ID).rename(columns={"value": "close_native"})
    if not wti_spot.empty:
        wti_spot["symbol"] = "WTI_SPOT"
        wti_spot["source_name"] = "FRED"
        wti_spot["source_url"] = "https://fred.stlouisfed.org"
        write_csv(wti_spot, "wti_spot_daily_reference_ist.csv")
    else:
        empty_csv(
            ["trade_date_ist", "close_native", "symbol", "source_name", "source_url"],
            "wti_spot_daily_reference_ist.csv"
        )
    file_rows.append(file_row("wti_spot_daily_reference_ist.csv", wti_spot, "FRED reference"))

    brent_spot_fred = (
        fred_series(FRED_BRENT_SERIES_ID).rename(columns={"value": "close_native"})
        if FRED_BRENT_SERIES_ID else pd.DataFrame()
    )
    if not brent_spot_fred.empty:
        brent_spot_fred["symbol"] = "BRENT_SPOT"
        brent_spot_fred["source_name"] = "FRED"
        brent_spot_fred["source_url"] = "https://fred.stlouisfed.org"

    brent_spot_eia = get_eia_brent_reference()

    brent_spot = (
        pd.concat(
            [x for x in [brent_spot_fred, brent_spot_eia] if x is not None and not x.empty],
            ignore_index=True,
            sort=False
        )
        if (not brent_spot_fred.empty or not brent_spot_eia.empty)
        else pd.DataFrame()
    )

    if not brent_spot.empty:
        brent_spot = (
            brent_spot
            .sort_values("trade_date_ist")
            .drop_duplicates(subset=["trade_date_ist"], keep="first")
        )
        write_csv(brent_spot, "brent_spot_daily_reference_ist.csv")
    else:
        empty_csv(
            ["trade_date_ist", "close_native", "symbol", "source_name", "source_url"],
            "brent_spot_daily_reference_ist.csv"
        )
    file_rows.append(
        file_row("brent_spot_daily_reference_ist.csv", brent_spot, "FRED/EIA Brent spot reference")
    )

    usdinr = get_usdinr_reference()
    if not usdinr.empty:
        write_csv(usdinr, "usdinr_daily_ist.csv")
    else:
        empty_csv(["trade_date_ist", "fx_rate"], "usdinr_daily_ist.csv")
    file_rows.append(file_row("usdinr_daily_ist.csv", usdinr, "Optional USDINR reference"))

    product_daily = {}
    product_session = {}
    product_intraday_1m = {}

    if (OUTPUT_DIR / "contract_roll_log.csv").exists():
        (OUTPUT_DIR / "contract_roll_log.csv").unlink()

    for product_key in ["WTI", "BRENT"]:
        defs = get_definitions(product_key)
        stats = get_stats(product_key)
        schedule = build_roll_schedule(defs, stats, product_key)

        candidates = get_intraday_candidates(product_key, schedule, usdinr)

        i5 = build_best_timeframe_bars(candidates, "5m")
        i15 = build_best_timeframe_bars(candidates, "15m")
        i60 = build_best_timeframe_bars(candidates, "60m")

        analysis_intraday = i15.copy() if not i15.empty else i60.copy()
        daily = merge_intraday_daily_with_fallback(i60, product_key, schedule, usdinr)

        sess = session_summary(analysis_intraday, product_key, "best_available_intraday")
        daily = add_daily_features(daily, analysis_intraday, sess)

        product_intraday_1m[product_key] = analysis_intraday
        product_daily[product_key] = finalize_daily(daily)
        product_session[product_key] = sess

        write_csv(finalize_intraday(i5), f"{product_key.lower()}_5m_ist.csv")
        write_csv(finalize_intraday(i15), f"{product_key.lower()}_15m_ist.csv")
        write_csv(finalize_intraday(i60), f"{product_key.lower()}_60m_ist.csv")
        write_csv(product_daily[product_key], f"{product_key.lower()}_daily_ist.csv")
        write_csv(sess, f"{product_key.lower()}_session_windows_summary.csv")

        file_rows.append(file_row(f"{product_key.lower()}_5m_ist.csv", i5, "Best-available bucket-level build for 5m"))
        file_rows.append(file_row(f"{product_key.lower()}_15m_ist.csv", i15, "Best-available bucket-level build for 15m"))
        file_rows.append(file_row(f"{product_key.lower()}_60m_ist.csv", i60, "Best-available bucket-level build for 60m"))
        file_rows.append(file_row(
            f"{product_key.lower()}_daily_ist.csv",
            product_daily[product_key],
            "Bucket-level intraday daily with 1d fallback only for uncovered dates"
        ))
        file_rows.append(file_row(
            f"{product_key.lower()}_session_windows_summary.csv",
            sess,
            "Derived from best-available intraday bars"
        ))

        candidate_mix = _concat_nonempty(list(candidates.values()))
        resolution_mix = (
            candidate_mix["source_resolution_used"].value_counts().to_dict()
            if not candidate_mix.empty and "source_resolution_used" in candidate_mix.columns
            else {}
        )

        coverage_notes[product_key] = (
            f"Yahoo symbol {PRODUCTS[product_key]['yahoo_symbol']} | "
            f"candidate_rows={len(candidate_mix)} | "
            f"resolution_mix={resolution_mix} | "
            f"bucket-level fallback active | "
            f"no verified exchange contract-roll metadata"
        )

    wti_daily = product_daily.get("WTI", pd.DataFrame())
    brent_daily = product_daily.get("BRENT", pd.DataFrame())

    daily_master = (
        day_master_summary(wti_daily, brent_daily)
        if not wti_daily.empty or not brent_daily.empty
        else pd.DataFrame()
    )
    write_csv(daily_master, "daily_master_summary.csv")
    file_rows.append(file_row("daily_master_summary.csv", daily_master, "Cross-market daily merge"))

    combined_session = (
        pd.concat([v for v in product_session.values() if not v.empty], ignore_index=True)
        if any(not v.empty for v in product_session.values())
        else pd.DataFrame()
    )

    day_labels_auto = build_day_type_labels(daily_master) if not daily_master.empty else pd.DataFrame()
    day_labels = apply_manual_day_label_overrides(day_labels_auto) if not day_labels_auto.empty else day_labels_auto
    write_csv(day_labels, "day_type_labels.csv")
    file_rows.append(file_row("day_type_labels.csv", day_labels, "Auto labels with optional manual overrides"))

    deviations = build_deviation_labels(day_labels)
    write_csv(deviations, "deviation_pattern_labels.csv")
    file_rows.append(file_row("deviation_pattern_labels.csv", deviations, "Prior-5-day deviation labels"))

    matrix = build_day_window_matrix(combined_session, day_labels)
    write_csv(matrix, "day_window_behavior_matrix.csv")
    file_rows.append(file_row("day_window_behavior_matrix.csv", matrix, "Window behavior summary"))

    arche = build_archetype_features(daily_master)
    write_csv(arche, "archetype_similarity_features.csv")
    file_rows.append(file_row("archetype_similarity_features.csv", arche, "Clustering feature layer"))

    scen_frames = []
    exc_frames = []
    for pk, df1m in product_intraday_1m.items():
        scen_frames.append(build_scenario_backtest(df1m, pk))
        exc_frames.append(build_intraday_excursions(df1m, pk))

    scen = pd.concat(scen_frames, ignore_index=True) if scen_frames else pd.DataFrame()
    exc = pd.concat(exc_frames, ignore_index=True) if exc_frames else pd.DataFrame()

    write_csv(scen, "scenario_backtest_features.csv")
    write_csv(exc, "intraday_excursions_combined.csv")
    file_rows.append(file_row("scenario_backtest_features.csv", scen, "Scenario metrics"))
    file_rows.append(file_row("intraday_excursions_combined.csv", exc, "Excursion metrics"))

    empty_csv([
        "symbol", "old_contract_symbol", "new_contract_symbol", "roll_date_ist", "roll_reason",
        "old_contract_last_trade_date", "days_to_expiry_at_roll", "price_difference_at_roll_native",
        "price_difference_at_roll_inr", "did_roll_create_artificial_gap_flag", "roll_notes"
    ], "contract_roll_log.csv")
    contract_roll_df = pd.read_csv(OUTPUT_DIR / "contract_roll_log.csv")
    file_rows.append(file_row(
        "contract_roll_log.csv",
        contract_roll_df,
        "Yahoo path: no verified contract-level roll metadata"
    ))

    news_path = Path(NEWS_EVENTS_INPUT_CSV)
    if NEWS_EVENTS_INPUT_CSV and news_path.exists():
        news_df = pd.read_csv(news_path)
        write_csv(news_df, "news_events_master.csv")
    else:
        empty_csv([
            "event_id", "trade_date_ist", "event_datetime_original", "event_datetime_ist", "source_name", "source_url", "headline",
            "summary_1_sentence", "event_type", "trump_statement_flag", "trump_post_flag", "trump_direct_quote_short",
            "iran_hormuz_flag", "shipping_disruption_flag", "sanctions_flag", "talks_negotiation_flag", "ceasefire_flag",
            "attack_threat_flag", "OPEC_supply_flag", "inventory_flag", "usd_macro_flag", "equity_risk_sentiment_flag",
            "market_interpretation_bucket", "expected_wti_bias", "expected_brent_bias", "confidence_1_to_5"
        ], "news_events_master.csv")
        news_df = pd.DataFrame()

    file_rows.append(file_row(
        "news_events_master.csv",
        news_df,
        "Header-only unless verified news input supplied"
    ))

    write_methodology(file_rows, coverage_notes)

    summary = pd.DataFrame(file_rows)
    print(summary.to_string(index=False))
    print(f"\nDone. Files written to {OUTPUT_DIR.resolve()}")

if __name__ == "__main__":
    main()