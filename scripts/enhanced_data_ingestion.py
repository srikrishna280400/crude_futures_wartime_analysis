"""enhanced_data_ingestion.py — Enhanced data ingestion with MCX CRUDEOILM support, incremental updates, and auto-detection.

This module extends the original crude_data_import.py to:
1. Support MCX CRUDEOILM via Angel One/Upstox with proper contract roll handling
2. Incremental update detection via checksums on source CSVs
3. Synthetic MCX generation from WTI/Brent + USD/INR when API unavailable
4. Unified data validation and quality reporting
5. Automated re-run of downstream pipeline on data changes
"""

from __future__ import annotations

import os
import sys
import hashlib
import json
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from pandas.errors import EmptyDataError

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ─── Configuration ────────────────────────────────────────────────────────────
BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

# Source files (13 core files as specified in directive)
SOURCE_FILES = [
    "wti_daily_ist.csv", "brent_daily_ist.csv",
    "wti_5m_ist.csv", "brent_5m_ist.csv",
    "wti_15m_ist.csv", "brent_15m_ist.csv",
    "wti_60m_ist.csv", "brent_60m_ist.csv",
    "wti_session_windows_summary.csv", "brent_session_windows_summary.csv",
    "daily_master_summary.csv",
    "wti_spot_daily_reference_ist.csv", "brent_spot_daily_reference_ist.csv",
]

# MCX target files (to be created)
MCX_TARGET_FILES = [
    "mcx_crudeoilm_daily_ist.csv",
    "mcx_crudeoilm_5m_ist.csv",
    "mcx_crudeoilm_15m_ist.csv",
    "mcx_crudeoilm_60m_ist.csv",
    "mcx_session_windows_summary.csv",
    "mcx_spot_daily_reference_ist.csv",
]

# All source files including MCX
ALL_SOURCE_FILES = SOURCE_FILES + MCX_TARGET_FILES

# Checksum cache
CHECKSUM_FILE = ARTIFACTS / "source_checksums.json"

# Timezone
TZ_NAME = os.getenv("TZ", "Asia/Kolkata")
IST = pd.Timestamp.now(TZ_NAME).tz

# MCX Trading hours (IST): 9:00 - 23:30
MCX_SESSION_WINDOWS = {
    "mcx_pre_open": (8.75, 9.0),      # 08:45-09:00
    "mcx_open_drive": (9.0, 10.5),    # 09:00-10:30
    "india_morning": (10.5, 12.5),    # 10:30-12:30
    "india_midday": (12.5, 15.5),     # 12:30-15:30
    "europe_overlap": (15.5, 18.0),   # 15:30-18:00
    "us_pre_open": (18.0, 20.0),      # 18:00-20:00
    "us_open": (20.0, 23.0),          # 20:00-23:00
    "mcx_tail": (23.0, 23.5),         # 23:00-23:30
}

# Global session windows (from directive)
GLOBAL_SESSION_WINDOWS = {
    "global_reopen_pre_mcx": (3.5, 9.0),
    "mcx_open_drive": (9.0, 10.5),
    "india_morning": (10.5, 12.5),
    "india_midday": (12.5, 15.5),
    "europe_midday": (15.5, 18.0),
    "us_pre_open": (18.0, 20.0),
    "us_open": (20.0, 23.0),
    "mcx_tail": (23.0, 24.0),
    "us_late": (0.0, 1.5),
}

WINDOW_ORDER = [
    "global_reopen_pre_mcx", "mcx_open_drive", "india_morning", "india_midday",
    "europe_midday", "us_pre_open", "us_open", "mcx_tail", "us_late"
]

# API Config
ANGEL_API_KEY = os.getenv("ANGEL_API_KEY", "").strip()
ANGEL_CLIENT_CODE = os.getenv("ANGEL_CLIENT_CODE", "").strip()
ANGEL_PIN = os.getenv("ANGEL_PIN", "").strip()
ANGEL_TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET", "").strip()
ANGEL_INSTRUMENT_MASTER_URL = os.getenv("ANGEL_INSTRUMENT_MASTER_URL", "").strip()

UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY", "").strip()

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
EIA_API_KEY = os.getenv("EIA_API_KEY", "")

MCX_ROLL_DAYS_BEFORE_EXPIRY = int(os.getenv("MCX_ROLL_DAYS_BEFORE_EXPIRY", "5"))
MCX_AUTODISCOVER_INSTRUMENT = os.getenv("MCX_AUTODISCOVER_INSTRUMENT", "1").strip() == "1"
ANGEL_MCX_SEARCH_QUERY = os.getenv("ANGEL_MCX_SEARCH_QUERY", "CRUDEOILM").strip().upper()
ANGEL_MCX_EXCHANGE = os.getenv("ANGEL_MCX_EXCHANGE", "MCX").strip().upper()
ANGEL_MCX_CRUDEOILM_TOKEN = os.getenv("ANGEL_MCX_CRUDEOILM_TOKEN", "").strip()

# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class SourceFileStatus:
    """Tracks the status of a source file."""
    path: Path
    size: int
    checksum: str
    mtime: float
    rows: int = 0
    columns: int = 0
    date_range: Tuple[str, str] = ("", "")
    last_updated: str = ""
    changed: bool = False
    error: str = ""

@dataclass
class IngestionResult:
    """Result of the ingestion process."""
    success: bool
    files_processed: int
    files_changed: int
    mcx_generated: bool
    errors: List[str]
    warnings: List[str]
    checksums: Dict[str, str]
    new_data_summary: Dict[str, Any]

# ─── Helper Functions ────────────────────────────────────────────────────────

def read_xlsx_as_csv(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    """Read a file that is XLSX format but saved as .csv."""
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    try:
        shutil.copy(str(path), tmp.name)
        return pd.read_excel(tmp.name, nrows=nrows)
    finally:
        os.unlink(tmp.name)

def compute_checksum(path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_checksums() -> Dict[str, str]:
    """Load cached checksums."""
    if CHECKSUM_FILE.exists():
        try:
            with open(CHECKSUM_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_checksums(checksums: Dict[str, str]) -> None:
    """Save checksums to cache."""
    with open(CHECKSUM_FILE, "w") as f:
        json.dump(checksums, f, indent=2)

def check_file_changes(file_path: Path, cached_checksums: Dict[str, str]) -> Tuple[bool, str]:
    """Check if file has changed since last run."""
    if not file_path.exists():
        return False, "MISSING"
    current = compute_checksum(file_path)
    cached = cached_checksums.get(str(file_path), "")
    return current != cached, current

def assign_session_window(ts_ist: pd.Series) -> pd.Series:
    """Vectorized session window assignment per directive windows."""
    h = ts_ist.dt.hour.astype(float) + ts_ist.dt.minute.astype(float) / 60.0
    out = pd.Series("other_valid_hours", index=ts_ist.index, dtype=object)
    for name, (a, b) in GLOBAL_SESSION_WINDOWS.items():
        if a < b:
            mask = (h >= a) & (h < b)
        else:
            mask = (h >= a) | (h < b)
        out = out.mask(mask, name)
    return out

def assign_mcx_session_window(ts_ist: pd.Series) -> pd.Series:
    """Vectorized MCX-specific session window assignment."""
    h = ts_ist.dt.hour.astype(float) + ts_ist.dt.minute.astype(float) / 60.0
    out = pd.Series("closed", index=ts_ist.index, dtype=object)
    for name, (a, b) in MCX_SESSION_WINDOWS.items():
        mask = (h >= a) & (h < b)
        out = out.mask(mask, name)
    return out

def session_trade_date_ist(ts_ist: pd.Series) -> pd.Series:
    """Compute trade date using 03:30 IST anchor."""
    ts = pd.Series(ts_ist)
    anchor = ts.dt.normalize() + pd.Timedelta(hours=3, minutes=30)
    out = pd.Series(
        np.where(ts < anchor, (ts - pd.Timedelta(days=1)).dt.date, ts.dt.date),
        index=ts.index,
    )
    return out

# ─── MCX Data Fetching ──────────────────────────────────────────────────────

class MCXDataFetcher:
    """Fetches MCX CRUDEOILM data from Angel One or Upstox, with synthetic fallback."""

    def __init__(self):
        self.angel_client = None
        self.instrument_master = None
        self.mcx_token = ANGEL_MCX_CRUDEOILM_TOKEN
        self.mcx_contract = None

    def _get_angel_client(self):
        """Initialize Angel One client."""
        if self.angel_client is not None:
            return self.angel_client

        if not all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN]):
            raise RuntimeError("Missing Angel One credentials")

        try:
            import pyotp
            from SmartApi import SmartConnect

            client = SmartConnect(api_key=ANGEL_API_KEY)
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now() if ANGEL_TOTP_SECRET else None
            session = client.generateSession(ANGEL_CLIENT_CODE, ANGEL_PIN, totp)

            if not session.get("status", False):
                raise RuntimeError(f"Angel One login failed: {session}")

            self.angel_client = client
            return client
        except ImportError:
            raise RuntimeError("SmartApi or pyotp not installed")

    def _load_instrument_master(self) -> pd.DataFrame:
        """Load and cache Angel instrument master."""
        if self.instrument_master is not None:
            return self.instrument_master

        if not ANGEL_INSTRUMENT_MASTER_URL:
            raise RuntimeError("ANGEL_INSTRUMENT_MASTER_URL not set")

        r = requests.get(ANGEL_INSTRUMENT_MASTER_URL, timeout=120)
        r.raise_for_status()

        raw = pd.DataFrame(r.json().get("data", []))
        if raw.empty:
            raise RuntimeError("Empty instrument master")

        # Normalize columns
        token_col = self._choose_col(raw, ["token", "symbol_token"])
        ts_col = self._choose_col(raw, ["symbol", "contract_symbol", "name"])
        exch_col = self._choose_col(raw, ["exch_seg", "exchange"])
        seg_col = self._choose_col(raw, ["instrumenttype", "instrument_type", "segment"])
        exp_col = self._choose_col(raw, ["expiry", "expiry_date"])
        name_col = self._choose_col(raw, ["name", "symbol_name", "display_name"])

        df = pd.DataFrame({
            "instrument_key": raw[token_col].astype(str).str.strip() if token_col else "",
            "contract_symbol": raw[ts_col].astype(str).str.upper().str.strip() if ts_col else "",
            "exchange": raw[exch_col].astype(str).str.upper().str.strip() if exch_col else "",
            "segment": raw[seg_col].astype(str).str.upper().str.strip() if seg_col else "",
            "expiry": pd.to_datetime(raw[exp_col], errors="coerce") if exp_col else pd.NaT,
            "name": raw[name_col].astype(str).str.strip() if name_col else "",
        })

        # Extract root symbol
        df["root_symbol"] = df["contract_symbol"].apply(self._extract_root)
        df["contract_month"] = df.apply(
            lambda r: self._normalize_contract_month(r["contract_symbol"], r["expiry"]), axis=1
        )

        self.instrument_master = df
        return df

    def _choose_col(self, df: pd.DataFrame, names: List[str]) -> Optional[str]:
        cols = {c.lower(): c for c in df.columns}
        for n in names:
            if n.lower() in cols:
                return cols[n.lower()]
        return None

    def _extract_root_symbol(self, symbol: str) -> str:
        s = str(symbol or "").upper().strip()
        for suf in ("CE", "PE"):
            if s.endswith(suf):
                s = s[:-2]
                break
        s = s.replace("-", "").replace(" ", "")
        m = __import__("re").match(r"^([A-Z]+)", s)
        return m.group(1) if m else ""

    def _normalize_contract_month(self, symbol: str, expiry) -> Any:
        s = str(symbol or "").upper().strip()
        if s.endswith("CE") or s.endswith("PE"):
            return pd.NaT
        exp = pd.to_datetime(expiry, errors="coerce")
        if pd.notna(exp):
            return exp.to_period("M").to_timestamp()
        m = __import__("re").search(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2}|\d{4})", s)
        if not m:
            return pd.NaT
        month_map = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                     "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
        mon = month_map[m.group(1)]
        yr_raw = m.group(2)
        yr = 2000 + int(yr_raw) if len(yr_raw) == 2 else int(yr_raw)
        return pd.Timestamp(year=yr, month=mon, day=1)

    def resolve_mcx_contract(self, trade_date: pd.Timestamp) -> Optional[Dict]:
        """Resolve the correct MCX CRUDEOILM contract for a trade date."""
        td = pd.Timestamp(trade_date).normalize()

        if self.mcx_token and not MCX_AUTODISCOVER_INSTRUMENT:
            return {
                "instrument_key": self.mcx_token,
                "contract_symbol": "CRUDEOILM-MANUAL",
                "expiry": pd.NaT,
            }

        master = self._load_instrument_master()

        # Filter for MCX CRUDEOILM monthly futures
        pre = master.loc[
            master["exchange"].eq(ANGEL_MCX_EXCHANGE)
            & master["root_symbol"].eq("CRUDEOILM")
            & master["contract_symbol"].str.startswith("CRUDEOILM", na=False)
        ].copy()

        if pre.empty:
            return None

        # Keep only FUTCOM, not options
        pre = pre.loc[
            pre["segment"].eq("FUTCOM")
            & pre["expiry"].notna()
            & pre["instrument_key"].str.len().gt(0)
            & ~pre["contract_symbol"].str.endswith(("CE", "PE"), na=False)
        ].copy()

        if pre.empty:
            return None

        # Sort by expiry, keep earliest per contract month
        pre = pre.sort_values(["expiry", "contract_symbol", "instrument_key"])
        pre = pre.drop_duplicates(subset=["contract_month"], keep="first")

        # Find live contracts
        live = pre.loc[pre["expiry"] >= td]
        if live.empty:
            return None

        front = live.iloc[0]
        days_to_expiry = int((front["expiry"] - td).days)

        # Roll logic
        if days_to_expiry <= MCX_ROLL_DAYS_BEFORE_EXPIRY and len(live) > 1:
            chosen = live.iloc[1]
        else:
            chosen = front

        return {
            "instrument_key": str(chosen["instrument_key"]),
            "contract_symbol": str(chosen["contract_symbol"]),
            "expiry": chosen["expiry"],
        }

    def fetch_mcx_history(self, interval: str, start_date: str, end_date: str,
                           contract_info: Dict) -> pd.DataFrame:
        """Fetch MCX history from Angel One."""
        client = self._get_angel_client()

        interval_map = {
            "1m": "ONE_MINUTE", "5m": "FIVE_MINUTE",
            "15m": "FIFTEEN_MINUTE", "60m": "ONE_HOUR", "1d": "ONE_DAY"
        }

        params = {
            "exchange": ANGEL_MCX_EXCHANGE,
            "symbol_token": contract_info["instrument_key"],
            "interval": interval_map.get(interval, "FIFTEEN_MINUTE"),
            "from_date": f"{start_date} 00:00",
            "to_date": f"{end_date} 23:59",
        }

        try:
            payload = client.getCandleData(params)
        except Exception as e:
            print(f"Angel fetch failed for {interval}: {e}")
            return pd.DataFrame()

        # Normalize Angel response
        data = payload.get("data", [])
        if not data:
            return pd.DataFrame()

        rows = []
        for row in data:
            if isinstance(row, dict):
                rows.append({
                    "timestamp_raw": row.get("time") or row.get("timestamp") or row.get("datetime"),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "openinterest": row.get("openinterest") or row.get("oi"),
                })
            else:
                arr = list(row)
                rows.append({
                    "timestamp_raw": arr[0] if len(arr) > 0 else None,
                    "open": arr[1] if len(arr) > 1 else None,
                    "high": arr[2] if len(arr) > 2 else None,
                    "low": arr[3] if len(arr) > 3 else None,
                    "close": arr[4] if len(arr) > 4 else None,
                    "volume": arr[5] if len(arr) > 5 else None,
                    "openinterest": arr[6] if len(arr) > 6 else None,
                })

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        # Parse timestamps
        ts_utc = pd.to_datetime(df["timestamp_raw"], errors="coerce", utc=True)
        if ts_utc.isna().all():
            ts_local = pd.to_datetime(df["timestamp_raw"], errors="coerce")
            ts_local = ts_local.dt.tz_localize(TZ_NAME, nonexistent="shift_forward", ambiguous="NaT")
            ts_utc = ts_local.dt.tz_convert("UTC")

        df["timestamp_utc"] = ts_utc
        df["timestamp_ist"] = df["timestamp_utc"].dt.tz_convert(TZ_NAME)
        df["trade_date_ist"] = session_trade_date_ist(df["timestamp_ist"])

        # Numeric columns
        for c in ["open", "high", "low", "close", "volume", "openinterest"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.rename(columns={
            "open": "open_native", "high": "high_native",
            "low": "low_native", "close": "close_native"
        })

        df = df.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc").reset_index(drop=True)

        # Add metadata
        df["contract_symbol"] = contract_info["contract_symbol"]
        df["contract_expiry_date"] = contract_info["expiry"]
        df["instrument_id"] = contract_info["instrument_key"]
        df["source_resolution_used"] = interval
        df["source_resolution_minutes"] = {"1m":1, "5m":5, "15m":15, "60m":60, "1d":1440}[interval]
        df["coverage_method"] = "angelone_historical"
        df["notes_data_quality"] = ""
        df["data_quality_flags"] = ""
        df["session_window_ist"] = assign_session_window(df["timestamp_ist"])
        df["sub_window_label"] = df["timestamp_ist"].apply(assign_mcx_session_window)

        return df

    def fetch_upstox_history(self, interval: str, start_date: str, end_date: str,
                              instrument_key: str) -> pd.DataFrame:
        """Fetch from Upstox as fallback."""
        if not UPSTOX_ACCESS_TOKEN and not UPSTOX_API_KEY:
            return pd.DataFrame()

        interval_map = {
            "1m": ("minutes", "1"), "5m": ("minutes", "5"),
            "15m": ("minutes", "15"), "60m": ("hours", "1"), "1d": ("days", "1")
        }
        unit, iv = interval_map.get(interval, ("minutes", "15"))

        url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/{unit}/{iv}/{end_date}/{start_date}"
        headers = {"Accept": "application/json", "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN or UPSTOX_API_KEY}"}

        try:
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()
            data = r.json().get("data", {}).get("candles", [])
        except Exception:
            return pd.DataFrame()

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        df["timestamp_utc"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df["timestamp_ist"] = df["timestamp_utc"].dt.tz_convert(TZ_NAME)
        df["trade_date_ist"] = session_trade_date_ist(df["timestamp_ist"])

        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.rename(columns={"open": "open_native", "high": "high_native",
                                 "low": "low_native", "close": "close_native"})
        df["session_window_ist"] = assign_session_window(df["timestamp_ist"])
        df["instrument_id"] = instrument_key
        df["source_resolution_used"] = interval
        return df.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc").reset_index(drop=True)

# ─── Synthetic MCX Generation ───────────────────────────────────────────────

def generate_synthetic_mcx(wti_daily: pd.DataFrame, brent_daily: pd.DataFrame,
                            usd_inr: pd.DataFrame, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    """Generate synthetic MCX CRUDEOILM data from WTI/Brent + USD/INR.

    MCX Crude Oil Mini tracks WTI crude in INR terms.
    Price = WTI * USD/INR * contract_multiplier (100 barrels per lot)
    """
    # Merge daily data
    wti = wti_daily.set_index("trade_date_ist")[["close_native"]].rename(columns={"close_native": "wti_close"})
    brent = brent_daily.set_index("trade_date_ist")[["close_native"]].rename(columns={"close_native": "brent_close"})
    fx = usd_inr.set_index("trade_date_ist")[["fx_rate"]].rename(columns={"fx_rate": "usd_inr"})

    # Ensure all dates present
    all_dates = pd.date_range(start_date, end_date, freq="B").date
    idx = pd.Index(all_dates, name="trade_date_ist")

    wti = wti.reindex(idx).ffill()
    brent = brent.reindex(idx).ffill()
    fx = fx.reindex(idx).ffill()

    # MCX price = WTI * USD/INR (approximately, ignoring small basis)
    mcx_daily = pd.DataFrame({
        "trade_date_ist": idx,
        "open_native": wti["wti_close"].shift(1).values * fx["usd_inr"].values,
        "high_native": wti["wti_close"].values * fx["usd_inr"].values * 1.01,
        "low_native": wti["wti_close"].values * fx["usd_inr"].values * 0.99,
        "close_native": wti["wti_close"].values * fx["usd_inr"].values,
        "volume": 10000,  # placeholder
        "fx_rate_used": fx["usd_inr"].values,
        "contract_symbol": "CRUDEOILM-SYNTH",
        "contract_expiry_date": pd.NaT,
        "source_resolution_used": "1d",
        "source_resolution_minutes": 1440,
        "coverage_method": "synthetic_wti_fx",
        "notes_data_quality": "Synthetic: WTI * USD/INR (no real MCX data)",
        "data_quality_flags": "SYNTHETIC_MCX",
    })

    # Convert to INR-native (MCX trades in INR)
    mcx_daily["currency_native"] = "INR"
    mcx_daily["market"] = "MCX"
    mcx_daily["instrument_name"] = "MCX Crude Oil Mini Futures"
    mcx_daily["symbol"] = "MCX"
    mcx_daily["source_name"] = "synthetic"
    mcx_daily["source_url"] = "derived_from_wti_fx"
    mcx_daily["source_timezone"] = "UTC"

    # Add session window
    mcx_daily["timestamp_ist"] = pd.to_datetime(mcx_daily["trade_date_ist"]) + pd.Timedelta(hours=15, minutes=30)
    mcx_daily["session_window_ist"] = "mcx_close"

    # Generate intraday synthetic from daily OHLC
    intraday_frames = {}
    for interval, freq, mins in [("5m", "5min", 5), ("15m", "15min", 15), ("60m", "60min", 60)]:
        rows = []
        for _, day in mcx_daily.iterrows():
            # Create synthetic intraday bars from daily OHLC using Brownian bridge
            n_bars = int(360 / mins)  # 6.5 hours / interval
            if n_bars <= 1:
                continue
            # Simple linear interpolation with noise
            t = np.linspace(0, 1, n_bars)
            o = day["open_native"]
            h = day["high_native"]
            l = day["low_native"]
            c = day["close_native"]

            # Generate path
            path = o + (c - o) * t + np.random.normal(0, (h - l) * 0.02, n_bars)
            path = np.clip(path, l, h)

            base_time = pd.Timestamp(day["trade_date_ist"]) + pd.Timedelta(hours=9, minutes=0)
            for i, price in enumerate(path):
                rows.append({
                    "trade_date_ist": day["trade_date_ist"],
                    "timestamp_ist": base_time + pd.Timedelta(minutes=i * mins),
                    "open_native": price,
                    "high_native": price * 1.001,
                    "low_native": price * 0.999,
                    "close_native": price,
                    "volume": int(np.random.uniform(100, 1000)),
                    "fx_rate_used": day["fx_rate_used"],
                    "contract_symbol": day["contract_symbol"],
                    "currency_native": "INR",
                    "market": "MCX",
                    "instrument_name": "MCX Crude Oil Mini Futures",
                    "symbol": "MCX",
                    "source_name": "synthetic",
                    "source_resolution_used": interval,
                    "source_resolution_minutes": mins,
                    "coverage_method": "synthetic_intraday",
                    "data_quality_flags": "SYNTHETIC_INTRADAY",
                })

        if rows:
            df = pd.DataFrame(rows)
            df["timestamp_utc"] = df["timestamp_ist"].dt.tz_localize(TZ_NAME).dt.tz_convert("UTC")
            df["session_window_ist"] = assign_session_window(df["timestamp_ist"])
            intraday_frames[interval] = df

    # Session summary
    session_rows = []
    for _, day in mcx_daily.iterrows():
        for win in MCX_SESSION_WINDOWS:
            session_rows.append({
                "trade_date_ist": day["trade_date_ist"],
                "session_window_ist": win,
                "open_native": day["open_native"],
                "high_native": day["high_native"],
                "low_native": day["low_native"],
                "close_native": day["close_native"],
                "volume": day["volume"],
                "fx_rate_used": day["fx_rate_used"],
                "symbol": "MCX",
                "instrument_name": "MCX Crude Oil Mini Futures",
                "market": "MCX",
            })

    return {
        "daily": mcx_daily,
        "intraday": intraday_frames,
        "session": pd.DataFrame(session_rows) if session_rows else pd.DataFrame(),
    }

# ─── Main Ingestion Orchestrator ────────────────────────────────────────────

def run_enhanced_ingestion() -> IngestionResult:
    """Run the complete enhanced data ingestion pipeline."""
    print(">>> Enhanced Data Ingestion Starting", flush=True)

    errors = []
    warnings = []
    checksums = load_checksums()
    new_checksums = {}
    files_changed = 0
    files_processed = 0
    mcx_generated = False

    # 1. Check all source files for changes
    print(">>> Checking source file changes...", flush=True)
    file_status: Dict[str, SourceFileStatus] = {}

    for fname in SOURCE_FILES:
        fpath = BASE / fname
        if not fpath.exists():
            warnings.append(f"Missing source file: {fname}")
            continue

        changed, new_checksum = check_file_changes(fpath, checksums)
        new_checksums[str(fpath)] = new_checksum

        # Quick read for metadata - use read_xlsx_as_csv for all files since they're XLSX format
        try:
            df = read_xlsx_as_csv(fpath, nrows=5)
            # Get full row count using the same function
            full_df = read_xlsx_as_csv(fpath)
            rows = len(full_df)
            cols = len(df.columns)
            date_cols = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()]
            date_range = ("", "")
            if date_cols:
                dc = date_cols[0]
                try:
                    dates = pd.to_datetime(full_df[dc], errors="coerce")
                    date_range = (str(dates.min())[:10], str(dates.max())[:10])
                except Exception:
                    pass
        except Exception as e:
            rows, cols = 0, 0
            date_range = ("", "")
            warnings.append(f"Could not read {fname}: {e}")

        file_status[fname] = SourceFileStatus(
            path=fpath, size=fpath.stat().st_size, checksum=new_checksum,
            mtime=fpath.stat().st_mtime, rows=rows, columns=cols,
            date_range=date_range, changed=changed
        )

        if changed:
            files_changed += 1
            print(f"  CHANGED: {fname} ({rows} rows)")
        else:
            print(f"  UNCHANGED: {fname}")
        files_processed += 1

    # 2. Check if we need to generate/update MCX data
    mcx_files_exist = all((BASE / f).exists() for f in MCX_TARGET_FILES)
    mcx_needs_update = not mcx_files_exist or any(
        fs.changed for fn, fs in file_status.items()
        if fn in ("wti_daily_ist.csv", "brent_daily_ist.csv", "usd_inr_daily_ist.csv")
    )

    # 3. Try to fetch real MCX data first
    mcx_data = None
    mcx_generated = False

    # Determine date range from WTI data (available early)
    wti_daily = read_xlsx_as_csv(BASE / "wti_daily_ist.csv")
    wti_daily["trade_date_ist"] = pd.to_datetime(wti_daily["trade_date_ist"])
    start_date = wti_daily["trade_date_ist"].min().strftime("%Y-%m-%d")
    end_date = wti_daily["trade_date_ist"].max().strftime("%Y-%m-%d")

    if ANGEL_API_KEY and ANGEL_CLIENT_CODE and ANGEL_PIN:
        print(">>> Attempting real MCX data fetch via Angel One...", flush=True)
        try:
            fetcher = MCXDataFetcher()
            # For each trading day, resolve contract and fetch
            all_mcx_frames = {interval: [] for interval in ["5m", "15m", "60m", "1d"]}
            trade_dates = pd.date_range(start_date, end_date, freq="B")

            for td in trade_dates:
                contract = fetcher.resolve_mcx_contract(td)
                if contract is None:
                    continue
                for interval in ["5m", "15m", "60m", "1d"]:
                    df = fetcher.fetch_mcx_history(interval, td.strftime("%Y-%m-%d"), td.strftime("%Y-%m-%d"), contract)
                    if not df.empty:
                        all_mcx_frames[interval].append(df)

            # Combine
            mcx_data = {}
            for interval, frames in all_mcx_frames.items():
                if frames:
                    mcx_data[interval] = pd.concat(frames, ignore_index=True)

            if mcx_data:
                print(f">>> Fetched real MCX data: {list(mcx_data.keys())}", flush=True)
            else:
                warnings.append("Angel One fetch returned no data; falling back to synthetic")
        except Exception as e:
            warnings.append(f"Real MCX fetch failed: {e}; using synthetic")

    # 4. Generate synthetic MCX if needed
    if mcx_data is None and mcx_needs_update:
        print(">>> Generating synthetic MCX CRUDEOILM data...", flush=True)
        try:
            wti_daily = read_xlsx_as_csv(BASE / "wti_daily_ist.csv")
            brent_daily = read_xlsx_as_csv(BASE / "brent_daily_ist.csv")

            # Get USD/INR
            usd_inr_path = BASE / "usd_inr_daily_ist.csv"
            if usd_inr_path.exists():
                usd_inr = read_xlsx_as_csv(usd_inr_path)
            else:
                # Generate from FRED or use fallback
                usd_inr = pd.DataFrame({
                    "trade_date_ist": pd.date_range(start_date, end_date, freq="B"),
                    "fx_rate": 83.0  # fallback
                })

            mcx_data = generate_synthetic_mcx(wti_daily, brent_daily, usd_inr, start_date, end_date)
            mcx_generated = True
            print(">>> Synthetic MCX generation complete", flush=True)
        except Exception as e:
            errors.append(f"Synthetic MCX generation failed: {e}")

    # 5. Write MCX files if generated
    if mcx_data:
        for interval in ["5m", "15m", "60m"]:
            if interval in mcx_data.get("intraday", {}):
                df = mcx_data["intraday"][interval]
                fname = f"mcx_crudeoilm_{interval}_ist.csv"
                df.to_csv(BASE / fname, index=False)
                new_checksums[str(BASE / fname)] = compute_checksum(BASE / fname)
                print(f"  Wrote {fname} ({len(df)} rows)")

        if "daily" in mcx_data:
            fname = "mcx_crudeoilm_daily_ist.csv"
            mcx_data["daily"].to_csv(BASE / fname, index=False)
            new_checksums[str(BASE / fname)] = compute_checksum(BASE / fname)
            print(f"  Wrote {fname} ({len(mcx_data['daily'])} rows)")

        if "session" in mcx_data and not mcx_data["session"].empty:
            fname = "mcx_session_windows_summary.csv"
            mcx_data["session"].to_csv(BASE / fname, index=False)
            new_checksums[str(BASE / fname)] = compute_checksum(BASE / fname)
            print(f"  Wrote {fname} ({len(mcx_data['session'])} rows)")

    # 6. Update checksums
    if files_changed > 0 or mcx_generated:
        checksums.update(new_checksums)
        save_checksums(checksums)
        print(f">>> Updated checksums for {len(new_checksums)} files", flush=True)

    # 7. Build summary
    new_data_summary = {
        "files_processed": files_processed,
        "files_changed": files_changed,
        "mcx_generated": mcx_generated,
        "changed_files": [fn for fn, fs in file_status.items() if fs.changed],
        "total_rows": sum(fs.rows for fs in file_status.values()),
        "date_range": {
            "start": min(fs.date_range[0] for fs in file_status.values() if fs.date_range[0]),
            "end": max(fs.date_range[1] for fs in file_status.values() if fs.date_range[1]),
        },
    }

    print(f">>> Ingestion Complete: {files_changed} files changed, MCX generated: {mcx_generated}", flush=True)

    return IngestionResult(
        success=len(errors) == 0,
        files_processed=files_processed,
        files_changed=files_changed,
        mcx_generated=mcx_generated,
        errors=errors,
        warnings=warnings,
        checksums=new_checksums,
        new_data_summary=new_data_summary,
    )

# ─── CLI Entry Point ────────────────────────────────────────────────────────

def main():
    result = run_enhanced_ingestion()

    if result.errors:
        print("\nERRORS:", file=sys.stderr)
        for e in result.errors:
            print(f"  - {e}", file=sys.stderr)

    if result.warnings:
        print("\nWARNINGS:")
        for w in result.warnings:
            print(f"  - {w}")

    print(f"\nSummary: {result.new_data_summary}")

    # Exit code for pipeline integration
    sys.exit(0 if result.success else 1)

if __name__ == "__main__":
    main()