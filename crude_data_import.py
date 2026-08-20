#crcude_data_import.py
#phase1_analysis

from __future__ import annotations
import os
import re
import json
import math
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Mapping
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from pandas.errors import EmptyDataError
import pyotp
from SmartApi import SmartConnect

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ============================================================
# CONFIG
# ============================================================

START_DATE = os.getenv("START_DATE", "2026-06-02")
END_DATE = os.getenv("END_DATE", "2026-06-04")
TZ_NAME = os.getenv("TZ", "Asia/Kolkata")

SELECTIVE_REPAIR_MODE = os.getenv("SELECTIVE_REPAIR_MODE", "1").strip() == "1"

HISTORICAL_PATCH_START_DATE = os.getenv("START_DATE")
HISTORICAL_PATCH_END_DATE = os.getenv("END_DATE")

FORWARD_FULL_START_DATE = os.getenv("FORWARD_FULL_START_DATE", "2026-06-02").strip()
FORWARD_FULL_END_DATE = os.getenv("FORWARD_FULL_END_DATE", "2026-06-04").strip()

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output r"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INPUT_DIR = Path(os.getenv("INPUT_DIR", "input"))
INPUT_DIR.mkdir(parents=True, exist_ok=True)

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
EIA_API_KEY = os.getenv("EIA_API_KEY", "")

FRED_WTI_SERIES_ID = os.getenv("FRED_WTI_SERIES_ID", "DCOILWTICO")
FRED_BRENT_SERIES_ID = os.getenv("FRED_BRENT_SERIES_ID", "DCOILBRENTEU")
FRED_USD_INR_SERIES_ID = os.getenv("FRED_USD_INR_SERIES_ID", "DEXINUS")

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

# ANGEL_API_KEY = os.getenv("ANGEL_API_KEY", "").strip()
# ANGEL_CLIENT_CODE = os.getenv("ANGEL_CLIENT_CODE", "").strip()
# ANGEL_PIN = os.getenv("ANGEL_PIN", "").strip()
# ANGEL_TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET", "").strip()
# ANGEL_INSTRUMENT_MASTER_URL = os.getenv("ANGEL_INSTRUMENT_MASTER_URL", "").strip()
# MCX_AUTODISCOVER_INSTRUMENT = os.getenv("MCX_AUTODISCOVER_INSTRUMENT", "1").strip() == "1"
# ANGEL_MCX_EXCHANGE = os.getenv("ANGEL_MCX_EXCHANGE", "MCX").strip().upper()
# ANGEL_MCX_SEARCH_QUERY = os.getenv("ANGEL_MCX_SEARCH_QUERY", "CRUDEOILM").strip().upper()
# ANGEL_MCX_CRUDEOILM_TOKEN = os.getenv("ANGEL_MCX_CRUDEOILM_TOKEN", "").strip()
# ANGEL_USDINR_EXCHANGE = os.getenv("ANGEL_USDINR_EXCHANGE", "CDS").strip().upper()
# ANGEL_USDINR_TOKEN = os.getenv("ANGEL_USDINR_TOKEN", "").strip()
# ANGEL_USDINR_CONTRACT_SYMBOL = os.getenv("ANGEL_USDINR_CONTRACT_SYMBOL", "USDINR").strip().upper()

# ANGEL_INTERVAL_MAP = {
#     "1m": "ONE_MINUTE",
#     "5m": "FIVE_MINUTE",
#     "15m": "FIFTEEN_MINUTE",
#     "60m": "ONE_HOUR",
#     "1d": "ONE_DAY",
# }

# ANGEL_CLIENT_CACHE: Dict[str, Any] = {
#     "client": None,
#     "instrument_master": None,
# }

MCX_ROLL_DAYS_BEFORE_EXPIRY = int(os.getenv("MCX_ROLL_DAYS_BEFORE_EXPIRY", "5"))

SELECTIVE_REPAIR_MODE = os.getenv("SELECTIVE_REPAIR_MODE", "1").strip() == "1"

SELECTIVE_BLANK_REPAIR_COLS = {
    "usd_inr_daily_ist": [
        "fx_rate",
    ],

    "wti_5m_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
    ],
    "wti_15m_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
    ],
    "wti_60m_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
    ],
    "wti_daily_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
        "prior_trading_day_close_inr",
        "gap_abs_inr", "gap_pct_inr",
        "day_range_abs_inr", "day_range_pct_inr",
        "first_hour_range_inr", "europe_open_hour_range_inr", "us_open_hour_range_inr",
        "full_day_range_inr", "25pct_range_inr", "50pct_range_inr", "75pct_range_inr",
        "max_up_move_from_open_inr", "max_down_move_from_open_inr",
        "close_from_open_inr",
        "mfe_inr", "mae_inr",
    ],
    "wti_session_windows_summary": [
        "open_inr", "high_inr", "low_inr", "close_inr",
    ],

    "brent_5m_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
    ],
    "brent_15m_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
    ],
    "brent_60m_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
    ],
    "brent_daily_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
        "gap_abs_inr", "gap_pct_inr",
        "day_range_abs_inr", "day_range_pct_inr",
        "first_hour_range_inr", "europe_open_hour_range_inr", "us_open_hour_range_inr",
        "full_day_range_inr", "25pct_range_inr", "50pct_range_inr", "75pct_range_inr",
        "max_up_move_from_open_inr", "max_down_move_from_open_inr",
        "close_from_open_inr", "close_from_open_pct",
        "mfe_inr", "mae_inr",
    ],
    "brent_session_windows_summary": [
        "open_inr", "high_inr", "low_inr", "close_inr",
    ],

    "daily_master_summary": [
        "wti_open_inr", "wti_high_inr", "wti_low_inr", "wti_close_inr",
        "wti_fx_rate_used",
        "wti_gap_abs_inr", "wti_gap_pct_inr",
        "wti_day_range_abs_inr", "wti_day_range_pct_inr",
        "wti_first_hour_range_inr", "wti_europe_open_hour_range_inr", "wti_us_open_hour_range_inr",
        "wti_full_day_range_inr", "wti_25pct_range_inr", "wti_50pct_range_inr", "wti_75pct_range_inr",
        "wti_max_up_move_from_open_inr", "wti_max_down_move_from_open_inr",

        "brent_open_inr", "brent_high_inr", "brent_low_inr", "brent_close_inr",
        "brent_fx_rate_used",
        "brent_gap_abs_inr", "brent_gap_pct_inr",
        "brent_day_range_abs_inr", "brent_day_range_pct_inr",
        "brent_first_hour_range_inr", "brent_europe_open_hour_range_inr", "brent_us_open_hour_range_inr",
        "brent_full_day_range_inr", "brent_25pct_range_inr", "brent_50pct_range_inr", "brent_75pct_range_inr",
        "brent_max_up_move_from_open_inr", "brent_max_down_move_from_open_inr",
        "brent_minus_wti_close_spread_inr",
    ],

    "archetype_similarity_features": [
        "europe_open_hour_range_inr",
        "us_open_hour_range_inr",
    ],

    "intraday_excursions_combined": [
        "max_favorable_excursion_inr",
        "max_adverse_excursion_inr",
        "time_to_mfe_minutes",
        "time_to_mae_minutes",
        "close_vs_entry_inr",
        "close_vs_entry_pct",
    ],
        "mcx_crudeoilm_5m_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
    ],
    "mcx_crudeoilm_15m_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
    ],
    "mcx_crudeoilm_60m_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
    ],
    "mcx_crudeoilm_daily_ist": [
        "open_inr", "high_inr", "low_inr", "close_inr", "fx_rate_used",
        "prior_trading_day_close_inr",
        "gap_abs_inr", "gap_pct_inr",
        "day_range_abs_inr", "day_range_pct_inr",
        "first_hour_range_inr", "europe_open_hour_range_inr", "us_open_hour_range_inr",
        "full_day_range_inr", "25pct_range_inr", "50pct_range_inr", "75pct_range_inr",
        "max_up_move_from_open_inr", "max_down_move_from_open_inr",
        "close_from_open_inr",
        "mfe_inr", "mae_inr",
    ],
    "mcx_session_windows_summary": [
        "open_inr", "high_inr", "low_inr", "close_inr",
    ],
}

YF_INTERVAL_PLAN = [
    ("1m", 5, 30),
    ("5m", 20, 60),
    ("15m", 20, 60),
    ("60m", 60, 60),
]

UPSTOX_INTERVAL_MAP = {
    "1m": ("minutes", "1"),
    "5m": ("minutes", "5"),
    "15m": ("minutes", "15"),
    "60m": ("hours", "1"),
    "1d": ("days", "1"),
}

INTERVAL_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "60m": 60,
    "1d": 1440,
}

IST_ANCHOR_HOUR = 3
IST_ANCHOR_MINUTE = 30

PRODUCT_OUTPUT_STEMS = {
    "MCX": {
        "5m": "mcx_crudeoilm_5m_ist",
        "15m": "mcx_crudeoilm_15m_ist",
        "60m": "mcx_crudeoilm_60m_ist",
        "daily": "mcx_crudeoilm_daily_ist",
        "session": "mcx_session_windows_summary",
    },
    "WTI": {
        "5m": "wti_5m_ist",
        "15m": "wti_15m_ist",
        "60m": "wti_60m_ist",
        "daily": "wti_daily_ist",
        "session": "wti_session_windows_summary",
    },
    "BRENT": {
        "5m": "brent_5m_ist",
        "15m": "brent_15m_ist",
        "60m": "brent_60m_ist",
        "daily": "brent_daily_ist",
        "session": "brent_session_windows_summary",
    },
}

PRODUCTS = {
    # "MCX": {
    # "data_source": "angelone",
    # "instrument_key": ANGEL_MCX_CRUDEOILM_TOKEN,
    # "exchange": ANGEL_MCX_EXCHANGE,
    # "market": "MCX",
    # "instrument_name": "MCX Crude Oil Mini Futures",
    # "currency_native": "INR",
    # "root": "CRUDEOILM",
    # "symbol": "MCX",
    # "tick_size": 1.0,
    # },
    "WTI": {
        "data_source": "yahoo",
        "yahoo_symbol": "CL=F",
        "market": "NYMEX",
        "instrument_name": "WTI Crude Futures",
        "currency_native": "USD",
        "root": "CL",
        "symbol": "WTI",
    },
    "BRENT": {
        "data_source": "yahoo",
        "yahoo_symbol": "BZ=F",
        "market": "ICE",
        "instrument_name": "Brent Crude Futures",
        "currency_native": "USD",
        "root": "BZ",
        "symbol": "BRENT",
    },
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

SUB_WINDOWS = {
    "first_15m_after_mcx_open": (9.0, 9.25),
    "first_30m_after_mcx_open": (9.0, 9.5),
    "first_hour_after_mcx_open": (9.0, 10.0),
    "first_30m_after_europe_open": (15.5, 16.0),
    "first_hour_after_europe_open": (15.5, 16.5),
    "first_30m_after_us_open": (21.0, 21.5),
    "first_hour_after_us_open": (21.0, 22.0),
    "final_hour_before_mcx_close": (22.5, 23.5),
    "final_30m_before_mcx_close": (23.0, 23.5),
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
    "mcx_crudeoilm_daily_ist.csv",
    "mcx_crudeoilm_60m_ist.csv",
    "mcx_crudeoilm_15m_ist.csv",
    "mcx_crudeoilm_5m_ist.csv",
    "wti_spot_daily_reference_ist.csv",
    "brent_spot_daily_reference_ist.csv",
    "mcx_spot_daily_reference_ist.csv",
    "usd_inr_daily_ist.csv",
    "wti_session_windows_summary.csv",
    "brent_session_windows_summary.csv",
    "mcx_session_windows_summary.csv",
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

# ============================================================
# HELPERS
# ============================================================

# def angel_chunk_days_for_interval(interval: str) -> int:
#     return {
#         "1m": 5,
#         "5m": 20,
#         "15m": 60,
#         "60m": 180,
#         "1d": 365,
#     }.get(interval, 30)


# def _normalize_instrument_search(payload: dict) -> pd.DataFrame:
#     data = payload.get("data", [])
#     if isinstance(data, dict):
#         for k in ["results", "instruments", "items"]:
#             if isinstance(data.get(k), list):
#                 data = data[k]
#                 break
#         else:
#             data = [data]
#     if not isinstance(data, list):
#         data = []

#     raw = pd.DataFrame(data)
#     if raw.empty:
#         return pd.DataFrame(columns=[
#             "instrument_key", "contract_symbol", "exchange", "segment", "expiry"
#         ])

#     def col(*names):
#         return choose_col(raw, list(names))

#     out = pd.DataFrame({
#         "instrument_key": raw[col("instrument_key", "instrument_Key", "is_instrument_key")] if col("instrument_key", "instrument_Key", "is_instrument_key") else np.nan,
#         "contract_symbol": raw[col("contract_symbol", "contract_symbol", "symbol", "name")] if col("contract_symbol", "contract_symbol", "symbol", "name") else np.nan,
#         "exchange": raw[col("exchange")] if col("exchange") else np.nan,
#         "segment": raw[col("segment")] if col("segment") else np.nan,
#         "expiry": raw[col("expiry", "expiry_date", "expiry_Date")] if col("expiry", "expiry_date", "expiry_Date") else np.nan,
#     }).copy()

#     out["expiry"] = pd.to_datetime(out["expiry"], errors="coerce")
#     out["contract_symbol"] = out["contract_symbol"].astype("string").fillna("")
#     out["exchange"] = out["exchange"].astype("string").fillna("")
#     out["segment"] = out["segment"].astype("string").fillna("")
#     out["instrument_key"] = out["instrument_key"].astype("string").fillna("")
#     return out

# def search_upstox_instruments(query: str, exchange: str = "", segment: str = "") -> pd.DataFrame:
#     params = {"query": query}
#     if exchange:
#         params["exchange"] = exchange
#     if segment:
#         params["segment"] = segment
#     payload = upstox_get_json(UPSTOX_INSTRUMENT_SEARCH_URL, params=params)
#     return _normalize_instrument_search(payload)

def _extract_root_symbol(contract_symbol: Any) -> str:
    s = str(contract_symbol or "").upper().strip()
    if not s:
        return ""

    for suffix in ("CE", "PE"):
        if s.endswith(suffix):
            s = s[:-2]
            break

    s = s.replace("-", "").replace(" ", "")

    m = re.match(r"^([A-Z]+)", s)
    return m.group(1) if m else ""


def is_option_like_symbol(contract_symbol: Any) -> bool:
    s = str(contract_symbol or "").upper().strip()
    return s.endswith("CE") or s.endswith("PE")


def is_monthly_future_like_symbol(contract_symbol: Any, root_symbol: str = "CRUDEOILM") -> bool:
    s = str(contract_symbol or "").upper().strip()
    if not s or is_option_like_symbol(s):
        return False
    if not s.startswith(str(root_symbol or "").upper()):
        return False
    return True

def _normalize_contract_month(contract_symbol: Any, expiry: Any) -> Any:
    s = str(contract_symbol or "").upper().strip()

    if is_option_like_symbol(s):
        return pd.NaT

    exp = pd.to_datetime(expiry, errors="coerce")
    if pd.notna(exp):
        return exp.to_period("M").to_timestamp()

    m = re.search(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2}|\d{4})", s)
    if not m:
        return pd.NaT

    month_map = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    mon = month_map[m.group(1)]
    yr_raw = m.group(2)
    yr = 2000 + int(yr_raw) if len(yr_raw) == 2 else int(yr_raw)
    return pd.Timestamp(year=yr, month=mon, day=1)


# def angel_client() -> SmartConnect:
#     cached = ANGEL_CLIENT_CACHE.get("client")
#     if cached is not None:
#         return cached

#     if not ANGEL_API_KEY or not ANGEL_CLIENT_CODE or not ANGEL_PIN:
#         raise RuntimeError("Missing Angel One login config")

#     client = SmartConnect(api_key=ANGEL_API_KEY)

#     totp_code = pyotp.TOTP(ANGEL_TOTP_SECRET).now() if ANGEL_TOTP_SECRET else None
#     session = client.generateSession(ANGEL_CLIENT_CODE, ANGEL_PIN, totp_code)

#     if not isinstance(session, dict) or not session.get("status", True):
#         raise RuntimeError(f"Angel One session failed: {session}")

#     ANGEL_CLIENT_CACHE["client"] = client
#     return client


# def normalize_angel_instrument_master(payload: Any) -> pd.DataFrame:
#     raw = pd.DataFrame(payload if isinstance(payload, list) else payload.get("data", []))
#     if raw.empty:
#         return pd.DataFrame(columns=[
#             "instrument_key", "contract_symbol", "exchange", "segment",
#             "expiry", "name", "root_symbol", "contract_month"
#         ])

#     token_col = choose_col(raw, ["token", "symbol_token", "symbol_token"])
#     ts_col = choose_col(raw, ["symbol", "contract_symbol", "contract_Symbol"])
#     exch_col = choose_col(raw, ["exch_seg", "exchange", "exchseg"])
#     seg_col = choose_col(raw, ["instrumenttype", "instrument_type", "segment"])
#     exp_col = choose_col(raw, ["expiry", "expiry_date", "expiry_date"])
#     name_col = choose_col(raw, ["name", "symbol_name", "display_name"])

#     out = pd.DataFrame({
#         "instrument_key": raw[token_col] if token_col else np.nan,
#         "contract_symbol": raw[ts_col] if ts_col else np.nan,
#         "exchange": raw[exch_col] if exch_col else np.nan,
#         "segment": raw[seg_col] if seg_col else np.nan,
#         "expiry": raw[exp_col] if exp_col else np.nan,
#         "name": raw[name_col] if name_col else np.nan,
#     }).copy()

#     out["instrument_key"] = out["instrument_key"].astype(str).fillna("").str.strip()
#     out["contract_symbol"] = out["contract_symbol"].astype(str).fillna("").str.upper().str.strip()
#     out["exchange"] = out["exchange"].astype(str).fillna("").str.upper().str.strip()
#     out["segment"] = out["segment"].astype(str).fillna("").str.upper().str.strip()
#     out["expiry"] = pd.to_datetime(out["expiry"], errors="coerce")
#     out["name"] = out["name"].astype(str).fillna("").str.strip()

#     out["root_symbol"] = out["contract_symbol"].apply(_extract_root_symbol)
#     out["contract_month"] = [
#         _normalize_contract_month(ts, ex)
#         for ts, ex in zip(out["contract_symbol"], out["expiry"])
#     ]

#     return out


# def read_angel_instrument_master() -> pd.DataFrame:
#     cached = ANGEL_CLIENT_CACHE.get("instrument_master")
#     if cached is not None:
#         return cached.copy()

#     if not ANGEL_INSTRUMENT_MASTER_URL:
#         raise RuntimeError("ANGEL_INSTRUMENT_MASTER_URL is required")

#     r = requests.get(ANGEL_INSTRUMENT_MASTER_URL, timeout=120)
#     r.raise_for_status()

#     master = normalize_angel_instrument_master(r.json())
#     ANGEL_CLIENT_CACHE["instrument_master"] = master.copy()
#     return master


# def resolve_mcx_contract_universe() -> pd.DataFrame:
#     if not MCX_AUTODISCOVER_INSTRUMENT and ANGEL_MCX_CRUDEOILM_TOKEN:
#         return pd.DataFrame(
#             [
#                 {
#                     "instrument_key": ANGEL_MCX_CRUDEOILM_TOKEN,
#                     "contract_symbol": "CRUDEOILM-MANUAL",
#                     "exchange": ANGEL_MCX_EXCHANGE,
#                     "segment": "FUTCOM",
#                     "expiry": pd.NaT,
#                     "root_symbol": "CRUDEOILM",
#                     "contract_month": pd.NaT,
#                     "name": "CRUDEOILM",
#                 }
#             ]
#         )

#     work = read_angel_instrument_master().copy()
#     if work.empty:
#         raise RuntimeError("Angel instrument master returned no rows")

#     work["instrument_key"] = work["instrument_key"].astype(str).fillna("").str.strip()
#     work["contract_symbol"] = work["contract_symbol"].astype(str).fillna("").str.upper().str.strip()
#     work["exchange"] = work["exchange"].astype(str).fillna("").str.upper().str.strip()
#     work["segment"] = work["segment"].astype(str).fillna("").str.upper().str.strip()
#     work["name"] = work["name"].astype(str).fillna("").str.upper().str.strip()
#     work["root_symbol"] = work["root_symbol"].astype(str).fillna("").str.upper().str.strip()
#     work["expiry"] = pd.to_datetime(work["expiry"], errors="coerce")
#     work["contract_month"] = pd.to_datetime(work["contract_month"], errors="coerce")

#     monthbackfill = work["contract_month"].isna() & work["expiry"].notna()
#     work.loc[monthbackfill, "contract_month"] = (
#         work.loc[monthbackfill, "expiry"].dt.to_period("M").dt.to_timestamp()
#     )

#     # STRICT MINI-FUTURES ONLY
#     pre = work.loc[
#         work["exchange"].eq(ANGEL_MCX_EXCHANGE)
#         & work["root_symbol"].eq("CRUDEOILM")
#         & work["contract_symbol"].str.startswith("CRUDEOILM", na=False)
#     ].copy()

#     print("\nMCX PRE-FILTER RAW CHAIN")
#     print(
#         pre.loc[
#             :,
#             ["instrument_key", "contract_symbol", "segment", "expiry", "name", "root_symbol", "contract_month"],
#         ]
#         .sort_values(["expiry", "contract_symbol"], na_position="last")
#         .to_string(index=False)
#     )

#     # KEEP ONLY MONTHLY MINI FUTURES, NOT OPTIONS
#     pre = pre.loc[
#         pre["segment"].eq("FUTCOM")
#         & pre["expiry"].notna()
#         & pre["instrument_key"].str.len().gt(0)
#         & ~pre["contract_symbol"].str.endswith(("CE", "PE"), na=False)
#     ].copy()

#     print("\nMCX MINI FUTURES ALL MONTHS")
#     print(
#     pre.loc[:, ["instrument_key", "contract_symbol", "expiry", "contract_month", "root_symbol"]]
#     .sort_values(["expiry", "contract_symbol"], na_position="last")
#     .to_string(index=False)
#     )

#     # keep earliest token per contract month
#     out = (
#         pre.sort_values(["expiry", "contract_symbol", "instrument_key"], na_position="last")
#         .drop_duplicates(subset=["contract_month"], keep="first")
#         .reset_index(drop=True)
#     )

#     print("\nMCX FILTERED CHAIN")
#     print(
#         out.loc[:, ["instrument_key", "contract_symbol", "expiry", "contract_month", "root_symbol"]]
#         .sort_values(["expiry", "contract_symbol"], na_position="last")
#         .to_string(index=False)
#     )

#     if out.empty:
#         raise RuntimeError("No usable Angel MCX CRUDEOILM monthly futures found")

#     return out


# def choose_mcx_contract_for_trade_date(contracts: pd.DataFrame, trade_date: Any) -> pd.Series:
#     td = pd.Timestamp(trade_date).normalize()

#     c = contracts.copy()
#     c["expiry"] = pd.to_datetime(c["expiry"], errors="coerce").dt.normalize()
#     c = c.loc[c["expiry"].notna()].copy()

#     if c.empty:
#         raise RuntimeError("No MCX contracts with valid expiry found")

#     c = c.sort_values(["expiry", "contract_symbol", "instrument_key"]).reset_index(drop=True)

#     # nearest non-expired contracts only
#     live = c.loc[c["expiry"] >= td].copy()
#     if live.empty:
#         raise RuntimeError(f"No live MCX contract available for {td.date()}")

#     front = live.iloc[0]
#     days_to_expiry = int((front["expiry"] - td).days)

#     # roll to next contract inside roll window
#     if days_to_expiry <= MCX_ROLL_DAYS_BEFORE_EXPIRY and len(live) > 1:
#         chosen = live.iloc[1]
#     else:
#         chosen = front

#     print(
#         f"ROLL PICK {td.date()} -> {chosen['contract_symbol']} "
#         f"(expiry={pd.Timestamp(chosen['expiry']).date()}, "
#         f"front={front['contract_symbol']}, dte={days_to_expiry})"
#     )

#     return chosen


# def build_roll_schedule(def_df: pd.DataFrame, stats_df: pd.DataFrame, product_key: str) -> pd.DataFrame:
#     dates = pd.Series(non_weekend_trade_dates(START_DATE, END_DATE).date, name="trade_date_ist")
#     cfg = PRODUCTS[product_key]

#     if product_key != "MCX":
#         return pd.DataFrame({
#             "trade_date_ist": dates,
#             "symbol": product_key,
#             "instrument_key": cfg.get("instrument_key", ""),
#             "contract_symbol": cfg.get("yahoo_symbol", cfg.get("root", product_key)),
#             "contract_expiry_date": pd.NaT,
#             "rolled_flag": False,
#             "roll_reference": "",
#             "days_to_expiry": np.nan,
#             "open_interest": np.nan,
#             "volume": np.nan,
#         })

#     contracts = resolve_mcx_contract_universe()
#     rows = []
#     prev_key = None

#     for d in dates.tolist():
#         chosen = choose_mcx_contract_for_trade_date(contracts, d)
        
#         cs = str(chosen.get("contract_symbol", "")).upper().strip()
#         if cs.endswith("CE") or cs.endswith("PE"):
#             raise RuntimeError(
#                 f"Option contract leaked into MCX monthly schedule for {d}: {cs}"
#         )
        
#         expiry_raw = chosen.get("expiry")
#         if expiry_raw is None or pd.isna(expiry_raw):
#             expiry = pd.NaT
#         else:
#             expiry = pd.to_datetime(pd.Series([expiry_raw]), errors="coerce").iloc[0]
#         rolled = prev_key is not None and str(chosen["instrument_key"]) != str(prev_key)

#         rows.append({
#             "trade_date_ist": d,
#             "symbol": "MCX",
#             "instrument_key": str(chosen["instrument_key"]),
#             "contract_symbol": str(chosen["contract_symbol"]),
#             "contract_expiry_date": expiry,
#             "rolled_flag": rolled,
#             "roll_reference": (
#                 f"auto_roll_{MCX_ROLL_DAYS_BEFORE_EXPIRY}d_before_expiry_to_{chosen['contract_symbol']}"
#                 if rolled else ""
#             ),
#             "days_to_expiry": (expiry.normalize() - pd.Timestamp(d).normalize()).days if pd.notna(expiry) else np.nan,
#             "open_interest": np.nan,
#             "volume": np.nan,
#         })
#         prev_key = str(chosen["instrument_key"])
        
#     out = pd.DataFrame(rows)
#     print("\nMCX ROLL SCHEDULE SAMPLE")
#     print(
#         out.loc[:, ["trade_date_ist", "instrument_key", "contract_symbol", "contract_expiry_date", "days_to_expiry"]]
#            .head(40)
#            .to_string(index=False)
#     )
#     return out


# def build_contract_roll_log_from_schedule(schedule: pd.DataFrame) -> pd.DataFrame:
#     cols = [
#         "symbol", "old_contract_symbol", "new_contract_symbol", "roll_date_ist", "roll_reason",
#         "old_contract_last_trade_date", "days_to_expiry_at_roll", "price_difference_at_roll_native",
#         "price_difference_at_roll_inr", "did_roll_create_artificial_gap_flag", "roll_notes"
#     ]
#     if schedule is None or schedule.empty:
#         return pd.DataFrame(columns=cols)

#     sch = schedule.sort_values("trade_date_ist").copy()
#     sch["prev_contract_symbol"] = sch["contract_symbol"].shift(1)
#     sch["prev_contract_expiry_date"] = sch["contract_expiry_date"].shift(1)
#     sch["prev_instrument_key"] = sch["instrument_key"].shift(1)

#     rolls = sch.loc[
#         sch["prev_instrument_key"].notna()
#         & sch["instrument_key"].astype(str).ne(sch["prev_instrument_key"].astype(str))
#     ].copy()

#     if rolls.empty:
#         return pd.DataFrame(columns=cols)

#     rolls["roll_date_ist"] = rolls["trade_date_ist"]
#     rolls["old_contract_last_trade_date"] = pd.to_datetime(rolls["roll_date_ist"]) - pd.Timedelta(days=1)
#     rolls["days_to_expiry_at_roll"] = (
#         pd.to_datetime(rolls["prev_contract_expiry_date"], errors="coerce")
#         - pd.to_datetime(rolls["roll_date_ist"], errors="coerce")
#     ).dt.days
#     rolls["roll_reason"] = f"expiry_within_{MCX_ROLL_DAYS_BEFORE_EXPIRY}_days_auto_roll"

#     out = pd.DataFrame({
#         "symbol": "MCX",
#         "old_contract_symbol": rolls["prev_contract_symbol"],
#         "new_contract_symbol": rolls["contract_symbol"],
#         "roll_date_ist": rolls["roll_date_ist"],
#         "roll_reason": rolls["roll_reason"],
#         "old_contract_last_trade_date": rolls["old_contract_last_trade_date"],
#         "days_to_expiry_at_roll": rolls["days_to_expiry_at_roll"],
#         "price_difference_at_roll_native": np.nan,
#         "price_difference_at_roll_inr": np.nan,
#         "did_roll_create_artificial_gap_flag": np.nan,
#         "roll_notes": rolls["roll_reference"].fillna(""),
#     })
#     return out[cols]


# def validate_phase1_inputs():
#     missing = []

#     if not ANGEL_API_KEY:
#         missing.append("ANGEL_API_KEY")
#     if not ANGEL_CLIENT_CODE:
#         missing.append("ANGEL_CLIENT_CODE")
#     if not ANGEL_PIN:
#         missing.append("ANGEL_PIN")
#     if not ANGEL_INSTRUMENT_MASTER_URL:
#         missing.append("ANGEL_INSTRUMENT_MASTER_URL")
#     if not ANGEL_USDINR_TOKEN:
#         missing.append("ANGEL_USDINR_TOKEN")

#     if MCX_AUTODISCOVER_INSTRUMENT:
#         if not ANGEL_INSTRUMENT_MASTER_URL:
#             missing.append("ANGEL_INSTRUMENT_MASTER_URL")
#     else:
#         if not ANGEL_MCX_CRUDEOILM_TOKEN:
#             missing.append("ANGEL_MCX_CRUDEOILM_TOKEN")

#     if missing:
#         raise RuntimeError(f"Missing required Angel config: {', '.join(missing)}")

# def build_upstox_url(template: str, instrument_key: str, interval_label: str, start: str, end: str) -> str:
#     unit, interval = UPSTOX_INTERVAL_MAP[interval_label]
#     return template.format(
#         instrument_key=instrument_key,
#         unit=unit,
#         interval=interval,
#         to_date=end,
#         from_date=start,
#     )

# def upstox_headers() -> Dict[str, str]:
#     token = UPSTOX_ACCESS_TOKEN or UPSTOX_API_KEY
#     return {
#         "Accept": "application/json",
#         "Authorization": f"Bearer {token}",
#     }

# def upstox_get_json(url: str, params: Optional[dict] = None) -> dict:
#     if not url:
#         return {}
#     r = requests.get(url, headers=upstox_headers(), params=params or {}, timeout=60)
#     if not r.ok:
#         print("UPSTOX STATUS:", r.status_code)
#         print("UPSTOX URL:", r.url)
#         print("UPSTOX BODY:", r.text)
#         r.raise_for_status()
#     return r.json()

# def coerce_angel_candles(payload: Any) -> pd.DataFrame:
#     data = payload.get("data", []) if isinstance(payload, dict) else []
#     if not data:
#         return pd.DataFrame()

#     rows = []
#     for row in data:
#         if isinstance(row, dict):
#             rows.append({
#                 "timestamp_raw": row.get("time") or row.get("timestamp") or row.get("datetime"),
#                 "open": row.get("open"),
#                 "high": row.get("high"),
#                 "low": row.get("low"),
#                 "close": row.get("close"),
#                 "volume": row.get("volume"),
#                 "openinterest": row.get("openinterest") or row.get("oi"),
#             })
#         else:
#             arr = list(row)
#             rows.append({
#                 "timestamp_raw": arr[0] if len(arr) > 0 else None,
#                 "open": arr[1] if len(arr) > 1 else None,
#                 "high": arr[2] if len(arr) > 2 else None,
#                 "low": arr[3] if len(arr) > 3 else None,
#                 "close": arr[4] if len(arr) > 4 else None,
#                 "volume": arr[5] if len(arr) > 5 else None,
#                 "openinterest": arr[6] if len(arr) > 6 else None,
#             })

#     return pd.DataFrame(rows)


# def normalize_angel_history(df: pd.DataFrame) -> pd.DataFrame:
#     if df is None or df.empty:
#         return pd.DataFrame()

#     out = df.copy()

#     ts_utc = pd.to_datetime(out["timestamp_raw"], errors="coerce", utc=True)

#     if ts_utc.isna().all():
#         ts_local = pd.to_datetime(out["timestamp_raw"], errors="coerce")
#         ts_local = ts_local.dt.tz_localize(TZ_NAME, nonexistent="shift_forward", ambiguous="NaT")
#         ts_utc = ts_local.dt.tz_convert("UTC")

#     out["timestamp_utc"] = ts_utc
#     out["timestamp_ist"] = out["timestamp_utc"].dt.tz_convert(TZ_NAME)
#     out["trade_date_ist"] = session_trade_date_ist(out["timestamp_ist"])

#     out["open_native"] = pd.to_numeric(out["open"], errors="coerce")
#     out["high_native"] = pd.to_numeric(out["high"], errors="coerce")
#     out["low_native"] = pd.to_numeric(out["low"], errors="coerce")
#     out["close_native"] = pd.to_numeric(out["close"], errors="coerce")
#     out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
#     out["openinterest"] = pd.to_numeric(out["openinterest"], errors="coerce")

#     return (
#         out[
#             [
#                 "timestamp_utc", "timestamp_ist", "trade_date_ist",
#                 "open_native", "high_native", "low_native", "close_native",
#                 "volume", "openinterest",
#             ]
#         ]
#         .dropna(subset=["timestamp_utc"])
#         .sort_values("timestamp_utc")
#         .reset_index(drop=True)
#     )


# def build_upstox_history_url(
#     template: str,
#     instrument_key: str,
#     intervallabel: str,
#     startdate: str,
#     enddate: str,
# ) -> str:
#     unit, interval = UPSTOX_INTERVAL_MAP[intervallabel]

#     start_s = pd.Timestamp(startdate).strftime("%Y-%m-%d")
#     end_s = pd.Timestamp(enddate).strftime("%Y-%m-%d")

#     if pd.Timestamp(start_s) > pd.Timestamp(end_s):
#         raise ValueError(f"startdate > enddate for Upstox history: {start_s} > {end_s}")

#     return template.format(
#         instrument_key=instrument_key,
#         unit=unit,
#         interval=interval,
#         from_date=start_s,
#         to_date=end_s,
#         start=start_s,
#         end=end_s,
#     )


# def fetch_angel_history(
#     product_key: str,
#     interval: str,
#     start_date: Optional[str] = None,
#     end_date: Optional[str] = None,
#     instrument_key: Optional[str] = None,
#     exchange: Optional[str] = None,
#     contract_symbol: Optional[str] = None,
#     contract_expiry: Optional[Any] = None,
# ) -> pd.DataFrame:
#     start_date = start_date or START_DATE
#     end_date = end_date or END_DATE

#     cfg = PRODUCTS.get(product_key, {})
#     symbol_token = instrument_key or cfg.get("instrument_key") or cfg.get("symbol_token") or cfg.get("symbol_token")
#     exch = exchange or cfg.get("exchange") or cfg.get("exchange_segment") or cfg.get("market")

#     if not symbol_token:
#         raise RuntimeError(f"Missing Angel symbol token for {product_key}")

#     if interval not in ANGEL_INTERVAL_MAP:
#         raise RuntimeError(f"Unsupported Angel interval mapping for {interval}")

#     client = angel_client()
#     params = {
#         "exchange": exch,
#         "symbol_token": str(symbol_token),
#         "interval": ANGEL_INTERVAL_MAP[interval],
#         "from_date": f"{pd.Timestamp(start_date).strftime('%Y-%m-%d')} 00:00",
#         "to_date": f"{pd.Timestamp(end_date).strftime('%Y-%m-%d')} 23:59",
#     }

#     try:
#         payload = client.getCandleData(params)
#     except Exception:
#         print("\nANGEL getCandleData FAILED")
#         print(
#             json.dumps(
#                 {
#                     "product_key": product_key,
#                     "interval": interval,
#                     "instrument_key": str(symbol_token),
#                     "exchange": exch,
#                     "contract_symbol": contract_symbol,
#                     "contract_expiry": str(contract_expiry),
#                     "start_date": start_date,
#                     "end_date": end_date,
#                     "params": params,
#                 },
#                 indent=2,
#                 default=str,
#             )
#         )
#         raise
#     raw = coerce_angel_candles(payload)
#     out = normalize_angel_history(raw)

#     if out.empty:
#         return out

#     expiry_raw = contract_expiry if contract_expiry is not None else cfg.get("contract_expiry_date")
#     expiry_val = pd.to_datetime(pd.Series([expiry_raw]), errors="coerce").iloc[0] if expiry_raw is not None else pd.NaT

#     out["contract_symbol"] = contract_symbol or cfg.get("contract_symbol") or cfg.get("root") or product_key
#     out["contract_expiry_date"] = expiry_val
#     out["instrument_id"] = str(symbol_token)
#     out["source_resolution_used"] = interval
#     out["source_resolution_minutes"] = INTERVAL_MINUTES.get(interval, np.nan)
#     out["coverage_method"] = "angelone_historical"
#     out["notes_data_quality"] = ""
#     out["data_quality_flags"] = ""
#     return out


# def fetch_angel_usd_inr_daily() -> pd.DataFrame:
#     if not ANGEL_USDINR_TOKEN:
#         return pd.DataFrame(columns=["trade_date_ist", "fx_rate"])

#     hist = fetch_angel_history(
#         product_key="USDINR",
#         interval="1d",
#         start_date=START_DATE,
#         end_date=END_DATE,
#         instrument_key=ANGEL_USDINR_TOKEN,
#         exchange=ANGEL_USDINR_EXCHANGE,
#         contract_symbol=ANGEL_USDINR_CONTRACT_SYMBOL,
#         contract_expiry=pd.NaT,
#     )

#     if hist.empty:
#         return pd.DataFrame(columns=["trade_date_ist", "fx_rate"])

#     fx = (
#         hist.sort_values("timestamp_ist")
#         .groupby("trade_date_ist", dropna=False)
#         .agg(fx_rate=("close_native", "last"))
#         .reset_index()
#     )
#     return fx

def read_output_table(filename: str, required: bool = False) -> pd.DataFrame:
    path = OUTPUT_DIR / filename

    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required output file not found: {path}")
        return pd.DataFrame()

    if path.stat().st_size == 0:
        return pd.DataFrame()

    try:
        if path.suffix.lower() == ".xlsx":
            return pd.read_excel(path)
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()

    raise ValueError(f"Unsupported file type: {path.suffix}")

def write_output_table(df: pd.DataFrame, filename: str) -> None:
    path = OUTPUT_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".xlsx":
        df.to_excel(path, index=False)
        return
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False)
        return
    raise ValueError(f"Unsupported file type: {path.suffix}")

def _ensure_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    return out

def _row_key(df: pd.DataFrame, key_cols: List[str]) -> pd.Series:
    work = _ensure_cols(df, key_cols).copy()
    for c in key_cols:
        work[c] = work[c].astype(str).fillna("")
    return work[key_cols].agg("||".join, axis=1)

def upsert_table(existing: pd.DataFrame, incoming: pd.DataFrame, key_cols: List[str]) -> pd.DataFrame:
    if incoming is None or incoming.empty:
        return existing.copy() if existing is not None else pd.DataFrame()
    if existing is None or existing.empty:
        out = incoming.copy()
        return out.reset_index(drop=True)

    all_cols = list(dict.fromkeys(list(existing.columns) + list(incoming.columns)))
    left = _ensure_cols(existing, all_cols)
    right = _ensure_cols(incoming, all_cols)

    left_keys = _row_key(left, key_cols)
    right_keys = _row_key(right, key_cols)

    left = left.loc[~left_keys.isin(set(right_keys.tolist()))].copy()
    out = pd.concat([left, right], ignore_index=True, sort=False)
    return out[all_cols].reset_index(drop=True)

def _detect_window_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["trade_date_ist", "timestamp_ist", "roll_date_ist"]:
        if c in df.columns:
            return c
    return None


def _filter_to_window(
    df: pd.DataFrame,
    start_date: str,
    end_date: str,
    date_col: Optional[str] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()

    col = date_col or _detect_window_col(df)
    if not col or not start_date or not end_date:
        return df.copy()

    out = df.copy()
    parsed = pd.to_datetime(out[col], errors="coerce", utc=True)
    if parsed.isna().all():
        parsed = pd.to_datetime(out[col], errors="coerce")

    start_d = pd.Timestamp(start_date).date()
    end_d = pd.Timestamp(end_date).date()

    mask = parsed.dt.date.between(start_d, end_d, inclusive="both")
    return out.loc[mask.fillna(False)].copy()


def _blank_mask(series: pd.Series) -> pd.Series:
    s = pd.Series(series)
    text_mask = (
        s.astype("string")
         .str.strip()
         .str.lower()
         .isin(["", "nan", "none", "<na>"])
    )
    return s.isna() | text_mask


def repair_blank_fields_only(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    key_cols: List[str],
    cols_to_fill: List[str],
) -> pd.DataFrame:
    if existing is None or existing.empty:
        return existing.copy() if existing is not None else pd.DataFrame()
    if incoming is None or incoming.empty:
        return existing.copy()

    all_cols = list(dict.fromkeys(list(existing.columns) + list(incoming.columns)))
    left = _ensure_cols(existing, all_cols).copy()
    right = _ensure_cols(incoming, all_cols).copy()

    left["_row_key"] = _row_key(left, key_cols)
    right["_row_key"] = _row_key(right, key_cols)
    right = right.drop_duplicates("_row_key", keep="last").set_index("_row_key")

    for col in cols_to_fill:
        if col not in left.columns or col not in right.columns:
            continue

        fill_mask = _blank_mask(left[col]) & left["_row_key"].isin(right.index)
        if fill_mask.any():
            left.loc[fill_mask, col] = left.loc[fill_mask, "_row_key"].map(right[col])

    return left.drop(columns=["_row_key"])


def sync_csv_xlsx(df: pd.DataFrame, stem: str, key_cols: List[str]) -> pd.DataFrame:
    csv_name = f"{stem}.csv"
    xlsx_name = f"{stem}.xlsx"

    existing_xlsx = read_output_table(xlsx_name, required=False)
    existing_csv = read_output_table(csv_name, required=False)
    base = existing_xlsx if not existing_xlsx.empty else existing_csv

    if base is None or base.empty:
        base = pd.DataFrame()

    incoming_full = pd.DataFrame() if df is None else df.copy()

    if not SELECTIVE_REPAIR_MODE:
        merged = upsert_table(base, incoming_full, key_cols)
        write_output_table(merged, csv_name)
        write_output_table(merged, xlsx_name)
        return merged

    historical_incoming = _filter_to_window(
        incoming_full,
        START_DATE,
        END_DATE,
    )
    forward_incoming = _filter_to_window(
        incoming_full,
        FORWARD_FULL_START_DATE,
        FORWARD_FULL_END_DATE,
    )

    # CRITICAL:
    # If the output does not already exist, create it from the full generated dataset,
    # not just the forward window.
    if base.empty:
        merged = incoming_full.copy().reset_index(drop=True)
        write_output_table(merged, csv_name)
        write_output_table(merged, xlsx_name)
        return merged

    merged = base.copy()

    repair_cols = [
        c for c in SELECTIVE_BLANK_REPAIR_COLS.get(stem, [])
        if incoming_full is not None and c in incoming_full.columns
    ]

    if repair_cols and not historical_incoming.empty:
        merged = repair_blank_fields_only(
            merged,
            historical_incoming,
            key_cols,
            repair_cols,
        )

    if not forward_incoming.empty:
        merged = upsert_table(merged, forward_incoming, key_cols)

    write_output_table(merged, csv_name)
    write_output_table(merged, xlsx_name)
    return merged

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

def ensure_datetime_col(df: pd.DataFrame, candidates: List[str], utc: bool = True) -> pd.Series:
    c = choose_col(df, candidates)
    if c is None:
        return pd.Series([pd.NaT] * len(df))
    series = df[c]
    return pd.to_datetime(series, utc=utc, errors="coerce")

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

def filter_to_window(
    df: pd.DataFrame,
    startdate: str,
    enddate: str,
    datecol: Optional[str] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()

    col = datecol or _detect_window_col(df)
    if not col or not startdate or not enddate:
        return df.copy()

    out = df.copy()
    parsed = pd.to_datetime(out[col], errors="coerce", utc=True)
    if parsed.isna().all():
        parsed = pd.to_datetime(out[col], errors="coerce")

    startd = pd.Timestamp(startdate).date()
    endd = pd.Timestamp(enddate).date()
    mask = parsed.dt.date.between(startd, endd, inclusive="both")

    return out.loc[mask.fillna(False)].copy()
    
def eia_route(route: str, facets: Optional[dict] = None, frequency: str = "daily") -> pd.DataFrame:
    if not route or not EIA_API_KEY:
        return pd.DataFrame()

    params = {
    "api_key": EIA_API_KEY,
    "frequency": frequency,
    "data[0]": "value",
    "sort[0][column]": "period",
    "sort[0][direction]": "asc",
    "start": START_DATE,
    "end": END_DATE,
}

    if facets:
        for facet_name, facet_values in facets.items():
            for i, v in enumerate(facet_values):
                params[f"facets[{facet_name}][{i}]"] = v

    url = f"https://api.eia.gov/v2/{route}"
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("response", {}).get("data", [])
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["trade_date_ist", "value"])

    period_col = choose_col(df, ["period", "date"])
    value_col = choose_col(df, ["value"])
    df["trade_date_ist"] = pd.to_datetime(df[period_col], errors="coerce").dt.date
    df["value"] = pd.to_numeric(df[value_col], errors="coerce")
    df = df[["trade_date_ist", "value"]].dropna()
    return filter_to_window(df, START_DATE, END_DATE, "trade_date_ist")

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
        "raw_symbol": cfg.get(
            "yahoo_symbol",
            cfg.get("instrument_key", cfg.get("root", product_key)),
        ),
        "instrument_id": cfg.get(
            "instrument_key",
            cfg.get("yahoo_symbol", cfg.get("root", product_key)),
        ),
        "asset": cfg["root"],
        "instrument_class": "FUT",
        "contract_expiry_date": pd.NaT,
    }])


def get_stats(product_key: str) -> pd.DataFrame:
    return pd.DataFrame(columns=["trade_date_ist", "instrument_id", "volume", "open_interest"])


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


# ============================================================
# BAR FETCH + RESAMPLING
# ============================================================

# def fetch_angel_history_by_schedule(product_key: str, interval: str, schedule: pd.DataFrame) -> pd.DataFrame:
#     if schedule is None or schedule.empty:
#         return pd.DataFrame()

#     sch = schedule.copy()
#     sch["trade_date_ist"] = pd.to_datetime(sch["trade_date_ist"], errors="coerce")
#     sch["instrument_key"] = sch["instrument_key"].astype(str).fillna("").str.strip()

#     frames = []
#     for instrument_key, grp in sch.groupby("instrument_key", dropna=False):
#         instrument_key = str(instrument_key).strip()
#         if not instrument_key:
#             continue
        
#         d0 = grp["trade_date_ist"].min()
#         d1 = grp["trade_date_ist"].max()
#         if pd.isna(d0) or pd.isna(d1):
#             continue
        
#         contract_symbol = (
#             grp["contract_symbol"].dropna().astype(str).iloc[0]
#             if grp["contract_symbol"].notna().any()
#             else product_key
#     )
#         contract_expiry = (
#             grp["contract_expiry_date"].dropna().iloc[0]
#             if "contract_expiry_date" in grp.columns and grp["contract_expiry_date"].notna().any()
#             else pd.NaT
#     )
#         print(
#             "FETCH BLOCK",
#     {
#         "interval": interval,
#         "instrument_key": instrument_key,
#         "exchange": PRODUCTS[product_key].get("exchange"),
#         "contract_symbol": contract_symbol,
#         "contract_expiry": str(contract_expiry),
#         "start_date": d0.strftime("%Y-%m-%d"),
#         "end_date": d1.strftime("%Y-%m-%d"),
#     },
# )
#         part = fetch_angel_history(
#         product_key=product_key,
#         interval=interval,
#         start_date=d0.strftime("%Y-%m-%d"),
#         end_date=d1.strftime("%Y-%m-%d"),
#         instrument_key=instrument_key,
#         exchange=PRODUCTS[product_key].get("exchange"),
#         contract_symbol=contract_symbol,
#         contract_expiry=contract_expiry,
#     )
#         if not part.empty:
#             frames.append(part)

#     if not frames:
#         return pd.DataFrame()

#     out = pd.concat(frames, ignore_index=True, sort=False)
#     out = (
#         out.drop_duplicates(subset=["timestamp_utc", "instrument_id"], keep="last")
#         .sort_values("timestamp_utc")
#         .reset_index(drop=True)
#     )
#     return out


def apply_schedule_to_1m(base_1m: pd.DataFrame, schedule: pd.DataFrame, product_key: str) -> pd.DataFrame:
    if base_1m.empty:
        return pd.DataFrame()

    cfg = PRODUCTS[product_key]
    df = base_1m.copy()
    df["symbol"] = product_key
    df["instrument_name"] = cfg["instrument_name"]
    df["market"] = cfg["market"]
    df["currency_native"] = cfg["currency_native"]

    if product_key == "MCX" and schedule is not None and not schedule.empty:
        sched = schedule[[
            "trade_date_ist", "instrument_key", "contract_symbol",
            "contract_expiry_date", "rolled_flag", "roll_reference"
        ]].copy()
        sched["trade_date_ist"] = sched["trade_date_ist"].astype(str)
        df["trade_date_ist"] = df["trade_date_ist"].astype(str)

        for c in ["contract_symbol", "contract_expiry_date", "rolled_flag", "roll_reference"]:
            if c in df.columns:
                df = df.drop(columns=[c])

        df = df.merge(sched, how="left", on="trade_date_ist")
        df["instrument_id"] = df.get("instrument_id", pd.Series(index=df.index, dtype="object"))
        df["instrument_id"] = df["instrument_id"].fillna(df["instrument_key"])
        df["contract_logic"] = f"auto_roll_{MCX_ROLL_DAYS_BEFORE_EXPIRY}d_before_expiry"
        df["contract_expiry_date"] = pd.to_datetime(df["contract_expiry_date"], errors="coerce")
        df["rolled_flag"] = df["rolled_flag"].fillna(False)
        df["roll_reference"] = df["roll_reference"].fillna("")
        df = df.drop(columns=["instrument_key"], errors="ignore")
        return df.sort_values("timestamp_ist").reset_index(drop=True)

    df["contract_logic"] = "upstox_direct_history" if cfg.get("data_source") == "upstox" else "yahoo_front_symbol_no_verified_roll_metadata"
    df["contract_expiry_date"] = pd.NaT
    df["rolled_flag"] = False
    df["roll_reference"] = ""
    return df.sort_values("timestamp_ist").reset_index(drop=True)

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
    if FRED_USD_INR_SERIES_ID:
        fred = fred_series(FRED_USD_INR_SERIES_ID).rename(columns={"value": "fx_rate"})
        if not fred.empty:
            return fred[["trade_date_ist", "fx_rate"]]
    return pd.DataFrame(columns=["trade_date_ist", "fx_rate"])


def apply_fx(df: pd.DataFrame, fx_df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()

    if "currency_native" not in out.columns:
        out["currency_native"] = np.nan
    if "notes_data_quality" not in out.columns:
        out["notes_data_quality"] = ""
    if "data_quality_flags" not in out.columns:
        out["data_quality_flags"] = ""

    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    is_inr_native = out["currency_native"].astype(str).str.upper().eq("INR")

    # INR-native instruments like MCX
    out.loc[is_inr_native, "fx_rate_used"] = 1.0
    for col in ["open_native", "high_native", "low_native", "close_native"]:
        out.loc[is_inr_native, col.replace("_native", "_inr")] = pd.to_numeric(
            out.loc[is_inr_native, col], errors="coerce"
        )

    # USD-native instruments like WTI / Brent
    usd_mask = ~is_inr_native
    if usd_mask.any():
        fx = fx_df.copy()
        if "fxrate" in fx.columns and "fx_rate" not in fx.columns:
            fx = fx.rename(columns={"fxrate": "fx_rate"})
        fx["trade_date_ist"] = fx["trade_date_ist"].astype(str)

        usd_part = out.loc[usd_mask].merge(
            fx[["trade_date_ist", "fx_rate"]],
            how="left",
            on="trade_date_ist",
        )

        usd_part["fx_rate_used"] = pd.to_numeric(usd_part["fx_rate"], errors="coerce")
        missing_fx = usd_part["fx_rate_used"].isna()

        for col in ["open_native", "high_native", "low_native", "close_native"]:
            usd_part[col.replace("_native", "_inr")] = (
                pd.to_numeric(usd_part[col], errors="coerce") * usd_part["fx_rate_used"]
            )

        usd_part["notes_data_quality"] = np.where(
            missing_fx,
            _append_text_series(usd_part["notes_data_quality"], "Missing FX for INR conversion"),
            usd_part["notes_data_quality"],
        )
        usd_part["data_quality_flags"] = np.where(
            missing_fx,
            _append_text_series(usd_part["data_quality_flags"], "MISSING_DAILY_FX"),
            usd_part["data_quality_flags"],
        )

        usd_part = usd_part.drop(columns=["fx_rate"], errors="ignore")
        out = pd.concat([out.loc[is_inr_native], usd_part], ignore_index=True, sort=False)

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
        for c in ["europe_open", "us_open", "mcx_tail"]:
            if c not in piv.columns:
                piv[c] = np.nan
        piv = piv.reset_index()
        df = df.merge(piv[["trade_date_ist", "europe_open", "us_open", "mcx_tail"]], how="left", on="trade_date_ist")
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
    return _sort_session_rows(pd.DataFrame(rows))

def day_master_summary(
    mcx_daily: pd.DataFrame,
    wti_daily: pd.DataFrame,
    brent_daily: pd.DataFrame,
) -> pd.DataFrame:
    frames = []

    for prefix, df in [
        ("mcx", mcx_daily),
        ("wti", wti_daily),
        ("brent", brent_daily),
    ]:
        if df is None or df.empty:
            frames.append(pd.DataFrame(columns=["trade_date_ist"]))
            continue

        tmp = df.add_prefix(f"{prefix}_").rename(
            columns={f"{prefix}_trade_date_ist": "trade_date_ist"}
        )
        frames.append(tmp)

    out = frames[0]
    for next_df in frames[1:]:
        out = pd.merge(out, next_df, how="outer", on="trade_date_ist")

    for col in [
        "mcx_close_native",
        "mcx_close_inr",
        "mcx_gap_pct_native",
        "wti_close_native",
        "wti_close_inr",
        "wti_gap_pct_native",
        "brent_close_native",
        "brent_close_inr",
        "brent_gap_pct_native",
    ]:
        if col not in out.columns:
            out[col] = np.nan

    out["mcx_close_inr_alias"] = out["mcx_close_inr"]
    out["wti_close_native_alias"] = out["wti_close_native"]
    out["brent_close_native_alias"] = out["brent_close_native"]
    out["wti_close_inr_alias"] = out["wti_close_inr"]
    out["brent_close_inr_alias"] = out["brent_close_inr"]

    out["brent_minus_wti_close_spread_native"] = (
        out["brent_close_native"] - out["wti_close_native"]
    )
    out["brent_minus_wti_close_spread_inr"] = (
        out["brent_close_inr"] - out["wti_close_inr"]
    )
    out["mcx_vs_wti_close_diff_inr"] = (
        out["mcx_close_inr"] - out["wti_close_inr"]
    )
    out["mcx_vs_brent_close_diff_inr"] = (
        out["mcx_close_inr"] - out["brent_close_inr"]
    )

    out["mcx_gap_pct"] = out["mcx_gap_pct_native"]
    out["wti_gap_pct"] = out["wti_gap_pct_native"]
    out["brent_gap_pct"] = out["brent_gap_pct_native"]

    out["lead_lag_hint_short"] = np.where(
        out["mcx_gap_pct_native"].notna() & out["wti_gap_pct_native"].notna(),
        np.where(
            (out["mcx_gap_pct_native"] - out["wti_gap_pct_native"]).abs() > 0.75,
            "mcx_diverged_from_wti",
            "mcx_tracked_wti",
        ),
        "",
    )

    return out.sort_values("trade_date_ist").reset_index(drop=True)

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
    for _, row in master.iterrows():
        symbol_focus, o, h, l, c = _pick_focus_ohlc(row)
        rows.append({
            "trade_date_ist": row["trade_date_ist"],
            "symbol_focus": symbol_focus or "MCX",
            "geo_bucket_primary": "",
            "geo_bucket_secondary": "",
            "price_path_bucket_primary": price_bucket(o, h, l, c),
            "price_path_bucket_secondary": "",
            "bucket_confidence_1_to_5": 2,
            "why_this_bucket_short": f"{symbol_focus.lower() if symbol_focus else 'no_symbol'}_price_derived_only",
            "main_evidence_short": f"{symbol_focus.lower() if symbol_focus else 'no_symbol'}_daily_intraday_bar_features",
            "deviation_from_recent_pattern_flag": False,
            "deviation_type_short": "",
        })
    return pd.DataFrame(rows)

def build_deviation_labels(day_labels: pd.DataFrame) -> pd.DataFrame:
    if day_labels.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist",
            "expected_pattern_based_on_prior_5_days",
            "actual_pattern_observed",
            "deviation_flag",
            "deviation_severity_1_to_5",
            "likely_reason_for_deviation",
            "related_news_event_id_if_any",
            "did_deviation_still_follow_an_alternate_repeatable_pattern",
            "alternate_pattern_short",
        ])

    df = day_labels.sort_values("trade_date_ist").reset_index(drop=True).copy()
    vals = df["price_path_bucket_primary"].astype("string").fillna("").tolist()
    out = []

    for i, (_, r) in enumerate(df.iterrows()):
        prior = [x for x in vals[max(0, i - 5):i] if str(x).strip() and str(x).lower() != "nan"]
        expected = pd.Series(prior, dtype="string").mode().iloc[0] if prior else ""
        actual = str(r.get("price_path_bucket_primary") or "").strip()
        dev = bool(expected and actual and expected != actual)

        out.append({
            "trade_date_ist": r["trade_date_ist"],
            "expected_pattern_based_on_prior_5_days": expected,
            "actual_pattern_observed": actual,
            "deviation_flag": dev,
            "deviation_severity_1_to_5": 3 if dev else 1,
            "likely_reason_for_deviation": "",
            "related_news_event_id_if_any": "",
            "did_deviation_still_follow_an_alternate_repeatable_pattern": False,
            "alternate_pattern_short": "",
        })

    return pd.DataFrame(out)

def build_day_window_matrix(session_df: pd.DataFrame, day_labels: pd.DataFrame) -> pd.DataFrame:
    if session_df.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist",
            "geo_bucket_primary",
            "price_path_bucket_primary",
            "global_reopen_pre_mcx_direction",
            "mcx_open_drive_direction",
            "india_morning_direction",
            "india_midday_direction",
            "europe_open_direction",
            "europe_mid_direction",
            "us_pre_open_direction",
            "us_open_direction",
            "mcx_tail_direction",
            "strongest_window_of_day",
            "weakest_window_of_day",
            "window_sequence_short",
        ])

    session_df = _sort_session_rows(session_df)
    rows = []

    for d, g in session_df.groupby("trade_date_ist", sort=False):
        g = _sort_session_rows(g)
        label = day_labels[day_labels["trade_date_ist"].eq(d)]
        by = {r["session_window_ist"]: r for _, r in g.iterrows()}

        strongest = (
            g.assign(_absret=g["session_return_pct"].abs())
             .sort_values("_absret", ascending=False)["session_window_ist"].iloc[0]
            if not g.empty else ""
        )
        weakest = (
            g.assign(_absret=g["session_return_pct"].abs())
             .sort_values("_absret", ascending=True)["session_window_ist"].iloc[0]
            if not g.empty else ""
        )

        rows.append({
            "trade_date_ist": d,
            "geo_bucket_primary": label["geo_bucket_primary"].iloc[0] if not label.empty else "",
            "price_path_bucket_primary": label["price_path_bucket_primary"].iloc[0] if not label.empty else "",
            "global_reopen_pre_mcx_direction": by["global_reopen_pre_mcx"]["session_body_direction"] if "global_reopen_pre_mcx" in by else "",
            "mcx_open_drive_direction": by["mcx_open_drive"]["session_body_direction"] if "mcx_open_drive" in by else "",
            "india_morning_direction": by["india_morning"]["session_body_direction"] if "india_morning" in by else "",
            "india_midday_direction": by["india_midday"]["session_body_direction"] if "india_midday" in by else "",
            "europe_open_direction": by["europe_open"]["session_body_direction"] if "europe_open" in by else "",
            "europe_mid_direction": by["europe_mid"]["session_body_direction"] if "europe_mid" in by else "",
            "us_pre_open_direction": by["us_pre_open"]["session_body_direction"] if "us_pre_open" in by else "",
            "us_open_direction": by["us_open"]["session_body_direction"] if "us_open" in by else "",
            "mcx_tail_direction": by["mcx_tail"]["session_body_direction"] if "mcx_tail" in by else "",
            "strongest_window_of_day": strongest,
            "weakest_window_of_day": weakest,
            "window_sequence_short": " -> ".join(
                w for w in SESSION_WINDOW_ORDER if w in set(g["session_window_ist"])
            ),
        })

    return pd.DataFrame(rows)

def build_archetype_features(master: pd.DataFrame) -> pd.DataFrame:
    if master.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist",
            "mcx_gap_pct",
            "mcx_range_pct",
            "mcx_close_location_in_range_pct",
            "wti_gap_pct",
            "brent_gap_pct",
            "first_hour_range_inr",
            "europe_open_hour_range_inr",
            "us_open_hour_range_inr",
            "trendiness_score",
            "whipsaw_score",
            "rhetoric_intensity_score",
            "shipping_risk_score",
            "physical_supply_risk_score",
            "day_type_vector_json",
        ])

    return pd.DataFrame({
        "trade_date_ist": master["trade_date_ist"],
        "mcx_gap_pct": master.get("mcx_gap_pct_native", pd.Series(dtype=float)),
        "mcx_range_pct": master.get("mcx_day_range_pct_native", pd.Series(dtype=float)),
        "mcx_close_location_in_range_pct": master.get(
            "mcx_close_location_in_range_pct",
            pd.Series(dtype=float),
        ),
        "wti_gap_pct": master.get("wti_gap_pct_native", pd.Series(dtype=float)),
        "brent_gap_pct": master.get("brent_gap_pct_native", pd.Series(dtype=float)),
        "first_hour_range_inr": master.get(
            "mcx_first_hour_range_inr",
            pd.Series(dtype=float),
        ),
        "europe_open_hour_range_inr": master.get(
            "mcx_europe_open_hour_range_inr",
            pd.Series(dtype=float),
        ),
        "us_open_hour_range_inr": master.get(
            "mcx_us_open_hour_range_inr",
            pd.Series(dtype=float),
        ),
        "trendiness_score": master.get(
            "mcx_trendiness_score_1_to_5",
            pd.Series(dtype=float),
        ),
        "whipsaw_score": master.get(
            "mcx_whipsaw_score_1_to_5",
            pd.Series(dtype=float),
        ),
        "rhetoric_intensity_score": np.nan,
        "shipping_risk_score": np.nan,
        "physical_supply_risk_score": np.nan,
        "day_type_vector_json": "",
    })

def build_scenario_backtest(
    intraday_1m: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    if intraday_1m.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist",
            "symbol",
            "hypothetical_long_entry_at_first_major_window",
            "hypothetical_short_entry_at_first_major_window",
            "max_profit_long_inr",
            "max_loss_long_inr",
            "max_profit_short_inr",
            "max_loss_short_inr",
            "whether_1r_hit_long",
            "whether_2r_hit_long",
            "whether_3r_hit_long",
            "whether_1r_hit_short",
            "whether_2r_hit_short",
            "whether_3r_hit_short",
            "time_to_1r_long_minutes",
            "time_to_2r_long_minutes",
            "time_to_3r_long_minutes",
            "time_to_1r_short_minutes",
            "time_to_2r_short_minutes",
            "time_to_3r_short_minutes",
        ])

    rows = []

    for trade_date_ist, group in intraday_1m.groupby("trade_date_ist"):
        group = group.sort_values("timestamp_ist")

        entry = group["open_inr"].iloc[0] if "open_inr" in group.columns else np.nan
        high_inr = group["high_inr"].max() if "high_inr" in group.columns else np.nan
        low_inr = group["low_inr"].min() if "low_inr" in group.columns else np.nan
        one_r = (
            (high_inr - low_inr) * 0.25
            if pd.notna(high_inr) and pd.notna(low_inr)
            else np.nan
        )

        rows.append({
            "trade_date_ist": trade_date_ist,
            "symbol": symbol,
            "hypothetical_long_entry_at_first_major_window": entry,
            "hypothetical_short_entry_at_first_major_window": entry,
            "max_profit_long_inr": (
                high_inr - entry
                if pd.notna(high_inr) and pd.notna(entry)
                else np.nan
            ),
            "max_loss_long_inr": (
                low_inr - entry
                if pd.notna(low_inr) and pd.notna(entry)
                else np.nan
            ),
            "max_profit_short_inr": (
                entry - low_inr
                if pd.notna(low_inr) and pd.notna(entry)
                else np.nan
            ),
            "max_loss_short_inr": (
                entry - high_inr
                if pd.notna(high_inr) and pd.notna(entry)
                else np.nan
            ),
            "whether_1r_hit_long": (
                (high_inr - entry) >= one_r
                if pd.notna(high_inr) and pd.notna(entry) and pd.notna(one_r)
                else np.nan
            ),
            "whether_2r_hit_long": (
                (high_inr - entry) >= 2 * one_r
                if pd.notna(high_inr) and pd.notna(entry) and pd.notna(one_r)
                else np.nan
            ),
            "whether_3r_hit_long": (
                (high_inr - entry) >= 3 * one_r
                if pd.notna(high_inr) and pd.notna(entry) and pd.notna(one_r)
                else np.nan
            ),
            "whether_1r_hit_short": (
                (entry - low_inr) >= one_r
                if pd.notna(low_inr) and pd.notna(entry) and pd.notna(one_r)
                else np.nan
            ),
            "whether_2r_hit_short": (
                (entry - low_inr) >= 2 * one_r
                if pd.notna(low_inr) and pd.notna(entry) and pd.notna(one_r)
                else np.nan
            ),
            "whether_3r_hit_short": (
                (entry - low_inr) >= 3 * one_r
                if pd.notna(low_inr) and pd.notna(entry) and pd.notna(one_r)
                else np.nan
            ),
            "time_to_1r_long_minutes": np.nan,
            "time_to_2r_long_minutes": np.nan,
            "time_to_3r_long_minutes": np.nan,
            "time_to_1r_short_minutes": np.nan,
            "time_to_2r_short_minutes": np.nan,
            "time_to_3r_short_minutes": np.nan,
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
    return _sort_session_rows(pd.DataFrame(rows))

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

def _pick_focus_ohlc(row) -> tuple[str, float, float, float, float]:
    for prefix, symbol in [("mcx", "MCX"), ("wti", "WTI"), ("brent", "BRENT")]:
        o = row.get(f"{prefix}_open_native")
        h = row.get(f"{prefix}_high_native")
        l = row.get(f"{prefix}_low_native")
        c = row.get(f"{prefix}_close_native")
        if pd.notna(o) and pd.notna(h) and pd.notna(l) and pd.notna(c):
            return symbol, o, h, l, c
    return "", np.nan, np.nan, np.nan, np.nan


def main():
    file_rows = []
    coverage_notes = {}

    ensure_input_templates()
    if pd.Timestamp(FORWARD_FULL_END_DATE) > pd.Timestamp(END_DATE):
        raise RuntimeError(
            f"FORWARD_FULL_END_DATE ({FORWARD_FULL_END_DATE}) cannot be greater than END_DATE ({END_DATE})"
        )

    # Reference layers
    wti_spot = fred_series(FRED_WTI_SERIES_ID).rename(columns={"value": "closenative"})
    
    if not wti_spot.empty:
        wti_spot["symbol"] = "WTI_SPOT"
        wti_spot["source_name"] = "FRED"
        wti_spot["source_url"] = "https://fred.stlouisfed.org"
    else:
        wti_spot = pd.DataFrame(columns=[
        "trade_date_ist", "close_native", "symbol", "source_name", "source_url"
    ])
        
    wti_spot = filter_to_window(wti_spot, START_DATE, END_DATE, "trade_date_ist")
    
    write_output_table(wti_spot, "wti_spot_daily_reference_ist.csv")
    write_output_table(wti_spot, "wti_spot_daily_reference_ist.xlsx")
    
    file_rows.append(file_row("wti_spot_daily_reference_ist.csv", wti_spot, "FRED WTI spot reference"))

    brentspotfred = fred_series(FRED_BRENT_SERIES_ID).rename(columns={"value": "closenative"}) if FRED_BRENT_SERIES_ID else pd.DataFrame()
    
    if not brentspotfred.empty:
        brentspotfred["symbol"] = "BRENTSPOT"
        brentspotfred["source_name"] = "FRED"
        brentspotfred["source_url"] = "https://fred.stlouisfed.org"
        
    brentspoteia = get_eia_brent_reference()
    
    brentspot = pd.concat(
    [x for x in [brentspotfred, brentspoteia] if x is not None and not x.empty],
    ignore_index=True,
    sort=False,
    ) if (not brentspotfred.empty or not brentspoteia.empty) else pd.DataFrame()
    
    if brentspot.empty:
        brentspot = pd.DataFrame(columns=[
        "trade_date_ist", "close_native", "symbol", "source_name", "source_url"
    ])
    else:
        brentspot = filter_to_window(brentspot, START_DATE, END_DATE, "trade_date_ist")
        brentspot = brentspot.sort_values("trade_date_ist").drop_duplicates(
        subset=["trade_date_ist"], keep="first"
    ).reset_index(drop=True)
        
    write_output_table(brentspot, "brent_spot_daily_reference_ist.csv")
    write_output_table(brentspot, "brent_spot_daily_reference_ist.xlsx")
    
    file_rows.append(file_row("brent_spot_daily_reference_ist.csv", brentspot, "FRED/EIA Brent spot reference"))

    mcx_spot = pd.DataFrame(columns=[
        "trade_date_ist", "close_native", "symbol", "source_name", "source_url"
    ])
    sync_csv_xlsx(mcx_spot, "mcx_spot_daily_reference_ist", ["trade_date_ist"])
    file_rows.append(file_row(
        "mcx_spot_daily_reference_ist.csv",
        mcx_spot,
        "Placeholder MCX spot daily reference",
    ))

    usd_inr = get_usdinr_reference()
    if usd_inr.empty:
        usd_inr = pd.DataFrame(columns=["trade_date_ist", "fx_rate"])

    sync_csv_xlsx(usd_inr, "usd_inr_daily_ist", ["trade_date_ist"])
    file_rows.append(file_row(
        "usd_inr_daily_ist.csv",
        usd_inr,
        "Optional USD/INR reference",
    ))

    product_daily = {}
    product_session = {}
    product_intraday_analysis = {}
    contract_roll_frames = []
    
    if not SELECTIVE_REPAIR_MODE:
        if (OUTPUT_DIR / "contract_roll_log.csv").exists():
            (OUTPUT_DIR / "contract_roll_log.csv").unlink()
        if (OUTPUT_DIR / "contract_roll_log.xlsx").exists():
            (OUTPUT_DIR / "contract_roll_log.xlsx").unlink()

    for product_key in ("WTI", "BRENT"):
        schedule = pd.DataFrame()
        
        roll_rows = pd.DataFrame()
        
        if not roll_rows.empty:
            roll_rows = roll_rows.rename(columns={
        "trade_date_ist": "roll_date_ist",
        "contract_symbol": "new_contract_symbol",
        "roll_reference": "roll_reason",
        "days_to_expiry": "days_to_expiry_at_roll",
    })
            
            roll_rows["old_contract_symbol"] = np.nan
            roll_rows["old_contract_last_trade_date"] = np.nan
            roll_rows["price_difference_at_roll_native"] = np.nan
            roll_rows["price_difference_at_roll_inr"] = np.nan
            roll_rows["did_roll_create_artificial_gap_flag"] = np.nan
            roll_rows["roll_notes"] = ""
            
            contract_roll_frames.append(
                roll_rows[[
            "symbol",
            "old_contract_symbol",
            "new_contract_symbol",
            "roll_date_ist",
            "roll_reason",
            "old_contract_last_trade_date",
            "days_to_expiry_at_roll",
            "price_difference_at_roll_native",
            "price_difference_at_roll_inr",
            "did_roll_create_artificial_gap_flag",
            "roll_notes",
        ]]
    )

        candidates = get_intraday_candidates(product_key, schedule, usd_inr)

        intraday_5m = build_best_timeframe_bars(candidates, "5m")
        intraday_15m = build_best_timeframe_bars(candidates, "15m")
        intraday_60m = build_best_timeframe_bars(candidates, "60m")
        
        analysis_intraday = (
            intraday_5m.copy()
            if not intraday_5m.empty
            else intraday_15m.copy()
            if not intraday_15m.empty
            else intraday_60m.copy()
            )
        
        best_intraday_for_daily = (
            intraday_5m.copy()
            if not intraday_5m.empty
            else intraday_15m.copy()
            if not intraday_15m.empty
            else intraday_60m.copy()
            )
        
        daily = merge_intraday_daily_with_fallback(
            best_intraday_for_daily,
            product_key,
            schedule,
            usd_inr,
            )

        session_df = session_summary(
            analysis_intraday,
            product_key,
            "best_available_intraday",
        )
        daily = add_daily_features(daily, analysis_intraday, session_df)

        product_intraday_analysis[product_key] = analysis_intraday
        product_daily[product_key] = finalize_daily(daily)
        product_session[product_key] = session_df

        stems = PRODUCT_OUTPUT_STEMS[product_key]

        sync_csv_xlsx(
            finalize_intraday(intraday_5m),
            stems["5m"],
            ["timestamp_ist", "symbol", "timeframe"],
        )
        sync_csv_xlsx(
            finalize_intraday(intraday_15m),
            stems["15m"],
            ["timestamp_ist", "symbol", "timeframe"],
        )
        sync_csv_xlsx(
            finalize_intraday(intraday_60m),
            stems["60m"],
            ["timestamp_ist", "symbol", "timeframe"],
        )
        sync_csv_xlsx(
            product_daily[product_key],
            stems["daily"],
            ["trade_date_ist", "symbol"],
        )
        sync_csv_xlsx(
            session_df,
            stems["session"],
            ["trade_date_ist", "symbol", "session_window_ist"],
        )

        file_rows.append(file_row(
            f"{stems['5m']}.csv",
            intraday_5m,
            "Best-available bucket-level build for 5m",
        ))
        file_rows.append(file_row(
            f"{stems['15m']}.csv",
            intraday_15m,
            "Best-available bucket-level build for 15m",
        ))
        file_rows.append(file_row(
            f"{stems['60m']}.csv",
            intraday_60m,
            "Best-available bucket-level build for 60m",
        ))
        file_rows.append(file_row(
            f"{stems['daily']}.csv",
            product_daily[product_key],
            "Bucket-level intraday daily with 1d fallback only for uncovered dates",
        ))
        file_rows.append(file_row(
            f"{stems['session']}.csv",
            session_df,
            "Derived from best-available intraday bars",
        ))

        candidate_mix = _concat_nonempty(list(candidates.values()))
        resolution_mix = (
            candidate_mix["source_resolution_used"].value_counts().to_dict()
            if not candidate_mix.empty and "source_resolution_used" in candidate_mix.columns
            else {}
        )

        coverage_notes[product_key] = (
            f"source={PRODUCTS[product_key].get('data_source', 'yahoo')} | "
            f"candidate_rows={len(candidate_mix)} | "
            f"resolution_mix={resolution_mix}"
        )

    mcx_daily = product_daily.get("MCX", pd.DataFrame())
    wti_daily = product_daily.get("WTI", pd.DataFrame())
    brent_daily = product_daily.get("BRENT", pd.DataFrame())

    daily_master = day_master_summary(mcx_daily, wti_daily, brent_daily)
    sync_csv_xlsx(daily_master, "daily_master_summary", ["trade_date_ist"])
    file_rows.append(file_row(
        "daily_master_summary.csv",
        daily_master,
        "Cross-market daily merge",
    ))

    day_labels_auto = (
        build_day_type_labels(daily_master)
        if not daily_master.empty
        else pd.DataFrame()
    )
    day_labels = (
        apply_manual_day_label_overrides(day_labels_auto)
        if not day_labels_auto.empty
        else day_labels_auto
    )
    sync_csv_xlsx(day_labels, "day_type_labels", ["trade_date_ist", "symbol_focus"])
    file_rows.append(file_row(
        "day_type_labels.csv",
        day_labels,
        "Auto labels with optional manual overrides",
    ))

    deviations = build_deviation_labels(day_labels)
    sync_csv_xlsx(deviations, "deviation_pattern_labels", ["trade_date_ist"])
    file_rows.append(file_row(
        "deviation_pattern_labels.csv",
        deviations,
        "Prior-5-day deviation labels",
    ))

    matrix_source = product_session.get("MCX", pd.DataFrame())
    if matrix_source.empty:
        matrix_source = product_session.get("WTI", pd.DataFrame())
    if matrix_source.empty:
        matrix_source = product_session.get("BRENT", pd.DataFrame())
        
    matrix = build_day_window_matrix(matrix_source, day_labels)
    sync_csv_xlsx(matrix, "day_window_behavior_matrix", ["trade_date_ist"])
    file_rows.append(file_row(
        "day_window_behavior_matrix.csv",
        matrix,
        "Window behavior summary",
    ))

    archetype_features = build_archetype_features(daily_master)
    sync_csv_xlsx(
        archetype_features,
        "archetype_similarity_features",
        ["trade_date_ist"],
    )
    file_rows.append(file_row(
        "archetype_similarity_features.csv",
        archetype_features,
        "Clustering feature layer",
    ))

    scenario_frames = []
    excursion_frames = []

    for product_key, intraday_df in product_intraday_analysis.items():
        scenario_frames.append(build_scenario_backtest(intraday_df, product_key))
        excursion_frames.append(build_intraday_excursions(intraday_df, product_key))

    scenario_backtest = (
        pd.concat(scenario_frames, ignore_index=True)
        if scenario_frames
        else pd.DataFrame()
    )
    intraday_excursions = (
        pd.concat(excursion_frames, ignore_index=True)
        if excursion_frames
        else pd.DataFrame()
    )

    sync_csv_xlsx(
        scenario_backtest,
        "scenario_backtest_features",
        ["trade_date_ist", "symbol"],
    )
    sync_csv_xlsx(
        intraday_excursions,
        "intraday_excursions_combined",
        ["trade_date_ist", "symbol", "session_window_ist", "direction_reference"],
    )
    file_rows.append(file_row(
        "scenario_backtest_features.csv",
        scenario_backtest,
        "Scenario metrics",
    ))
    file_rows.append(file_row(
        "intraday_excursions_combined.csv",
        intraday_excursions,
        "Excursion metrics",
    ))

    contract_roll_df = (
    pd.concat(contract_roll_frames, ignore_index=True, sort=False)
    if contract_roll_frames
    else pd.DataFrame(columns=[
        "symbol",
        "old_contract_symbol",
        "new_contract_symbol",
        "roll_date_ist",
        "roll_reason",
        "old_contract_last_trade_date",
        "days_to_expiry_at_roll",
        "price_difference_at_roll_native",
        "price_difference_at_roll_inr",
        "did_roll_create_artificial_gap_flag",
        "roll_notes",
    ]))
    
    sync_csv_xlsx(contract_roll_df, "contract_roll_log", ["symbol", "roll_date_ist"])
    file_rows.append(file_row(
        "contract_roll_log.csv",
        contract_roll_df,
        "Yahoo/Upstox path: no verified contract-level roll metadata",
    ))

    news_path = Path(NEWS_EVENTS_INPUT_CSV)
    if NEWS_EVENTS_INPUT_CSV and news_path.exists():
        news_df = pd.read_csv(news_path)
    else:
        news_df = pd.DataFrame(columns=[
            "event_id",
            "trade_date_ist",
            "event_datetime_original",
            "event_datetime_ist",
            "source_name",
            "source_url",
            "headline",
            "summary_1_sentence",
            "event_type",
            "trump_statement_flag",
            "trump_post_flag",
            "trump_direct_quote_short",
            "iran_hormuz_flag",
            "shipping_disruption_flag",
            "sanctions_flag",
            "talks_negotiation_flag",
            "ceasefire_flag",
            "attack_threat_flag",
            "OPEC_supply_flag",
            "inventory_flag",
            "usd_macro_flag",
            "equity_risk_sentiment_flag",
            "market_interpretation_bucket",
            "expected_wti_bias",
            "expected_brent_bias",
            "confidence_1_to_5",
        ])

    sync_csv_xlsx(news_df, "news_events_master", ["trade_date_ist", "event_id"])
    file_rows.append(file_row(
        "news_events_master.csv",
        news_df,
        "Header-only unless verified news input supplied",
    ))

    write_methodology(file_rows, coverage_notes)

    summary = pd.DataFrame(file_rows)
    print(summary.to_string(index=False))
    print(f"\nDone. Files written to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()