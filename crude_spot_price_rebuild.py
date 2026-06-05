from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ============================================================
# CONFIG
# ============================================================
START_DATE = os.getenv("START_DATE", "2026-05-26").strip()
END_DATE = os.getenv("END_DATE", "2026-06-04").strip()
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output r"))

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
EIA_API_KEY = os.getenv("EIA_API_KEY", "")

FRED_WTI_SERIES_ID = os.getenv("FRED_WTI_SERIES_ID", "DCOILWTICO")
FRED_BRENT_SERIES_ID = os.getenv("FRED_BRENT_SERIES_ID", "DCOILBRENTEU")
FRED_USD_INR_SERIES_ID = os.getenv("FRED_USD_INR_SERIES_ID", "DEXINUS")

# Better EIA shape: route + facets, not just bare route strings
EIA_WTI_FACETS_JSON = os.getenv("EIA_WTI_FACETS_JSON", "").strip()
EIA_BRENT_FACETS_JSON = os.getenv("EIA_BRENT_FACETS_JSON", "").strip()

EIA_SPOT_ROUTE = os.getenv("EIA_SPOT_ROUTE", "petroleum/pri/spt/data").strip().strip("/")
EIA_INVENTORY_ROUTE = os.getenv("EIA_INVENTORY_ROUTE", "")
EIA_INVENTORY_FACETS_JSON = os.getenv("EIA_INVENTORY_FACETS_JSON", "")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# HTTP
# ============================================================
def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
        }
    )
    return session


SESSION = build_session()


# ============================================================
# HELPERS
# ============================================================

def trim_to_available_window(df: pd.DataFrame, start_ts: pd.Timestamp, requested_end_ts: pd.Timestamp) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "trade_date_ist",
            "close_native",
            "symbol",
            "source_name",
            "source_url",
            "source_detail",
            "source_priority",
            "quality_flag",
        ])

    out = df.copy()
    out["trade_date_ist"] = pd.to_datetime(out["trade_date_ist"], errors="coerce").dt.date
    out["close_native"] = pd.to_numeric(out["close_native"], errors="coerce")
    out = out.dropna(subset=["trade_date_ist", "close_native"]).copy()

    start_d = start_ts.date()
    out = out[out["trade_date_ist"] >= start_d].copy()
    if out.empty:
        return out

    latest_available = max(out["trade_date_ist"])
    effective_end = min(requested_end_ts.date(), latest_available)

    out = out[out["trade_date_ist"] <= effective_end].copy()
    return out.sort_values("trade_date_ist").reset_index(drop=True)


def parse_date(text: str) -> pd.Timestamp:
    ts = pd.Timestamp(text)
    if pd.isna(ts):
        raise ValueError(f"Invalid date: {text}")
    return ts.normalize()


START_TS = parse_date(START_DATE)
END_TS = parse_date(END_DATE)
if END_TS < START_TS:
    raise RuntimeError(f"END_DATE {END_DATE} cannot be earlier than START_DATE {START_DATE}")


def safe_json_dict(raw: str, env_name: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"{env_name} is not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise RuntimeError(f"{env_name} must decode to a JSON object/dict.")
    return obj


def normalize_dates(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_datetime(df[col], errors="coerce").dt.date


def normalize_numeric(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def business_days_in_range() -> List[pd.Timestamp]:
    return list(pd.date_range(START_TS, END_TS, freq="B"))


def choose_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for c in candidates:
        k = c.strip().lower()
        if k in lookup:
            return lookup[k]
    return None


def write_both(df: pd.DataFrame, stem: str) -> None:
    csv_path = OUTPUT_DIR / f"{stem}.csv"
    xlsx_path = OUTPUT_DIR / f"{stem}.xlsx"
    out = df.copy()
    out.to_csv(csv_path, index=False)
    out.to_excel(xlsx_path, index=False)


def finalize_reference(
    raw_df: pd.DataFrame,
    symbol: str,
    preferred_source_order: Optional[List[str]] = None,
) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(
            columns=[
                "trade_date_ist",
                "close_native",
                "symbol",
                "source_name",
                "source_url",
                "source_detail",
                "source_priority",
                "quality_flag",
            ]
        )

    out = raw_df.copy()

    if "trade_date_ist" not in out.columns:
        raise RuntimeError(f"{symbol}: trade_date_ist missing in candidate dataframe")
    if "close_native" not in out.columns:
        raise RuntimeError(f"{symbol}: close_native missing in candidate dataframe")

    out["trade_date_ist"] = pd.to_datetime(out["trade_date_ist"], errors="coerce").dt.date
    out["close_native"] = pd.to_numeric(out["close_native"], errors="coerce")

    out = out[out["trade_date_ist"].notna()].copy()
    out = out[out["close_native"].notna()].copy()

    if "symbol" not in out.columns:
        out["symbol"] = symbol
    else:
        out["symbol"] = out["symbol"].fillna(symbol)

    if "source_name" not in out.columns:
        out["source_name"] = ""
    if "source_url" not in out.columns:
        out["source_url"] = ""
    if "source_detail" not in out.columns:
        out["source_detail"] = ""
    if "source_priority" not in out.columns:
        out["source_priority"] = 999
    if "quality_flag" not in out.columns:
        out["quality_flag"] = ""

    if preferred_source_order:
        rank_map = {name.lower(): i for i, name in enumerate(preferred_source_order, start=1)}
        missing_rank = len(rank_map) + 100
        out["_source_rank"] = out["source_name"].astype(str).str.lower().map(rank_map).fillna(missing_rank)
    else:
        out["_source_rank"] = out["source_priority"]

    out = out.sort_values(
        ["trade_date_ist", "_source_rank", "source_priority", "source_name", "source_detail"],
        ascending=[True, True, True, True, True],
    ).drop_duplicates(subset=["trade_date_ist"], keep="first").copy()

    start_d = START_TS.date()
    out = out[out["trade_date_ist"] >= start_d].copy()
    if out.empty:
        return out

    latest_available = out["trade_date_ist"].max()
    effective_end = min(END_TS.date(), latest_available)
    out = out[out["trade_date_ist"] <= effective_end].copy()

    out["quality_flag"] = out["quality_flag"].fillna("").astype(str)
    out = out[
        [
            "trade_date_ist",
            "close_native",
            "symbol",
            "source_name",
            "source_url",
            "source_detail",
            "source_priority",
            "quality_flag",
        ]
    ].sort_values("trade_date_ist").reset_index(drop=True)

    return out

# def carry_forward_to_business_days(df: pd.DataFrame, label: str) -> pd.DataFrame:
#     expected_dates = pd.date_range(START_TS, END_TS, freq="B").date

#     base_cols = [
#         "trade_date_ist",
#         "close_native",
#         "symbol",
#         "source_name",
#         "source_url",
#         "source_detail",
#         "source_priority",
#         "quality_flag",
#     ]

#     if df is None or df.empty:
#         return pd.DataFrame(columns=base_cols)

#     out = df.copy()

#     for col in base_cols:
#         if col not in out.columns:
#             out[col] = pd.NA

#     out["trade_date_ist"] = pd.to_datetime(out["trade_date_ist"], errors="coerce").dt.date
#     out["close_native"] = pd.to_numeric(out["close_native"], errors="coerce")
#     out = out.dropna(subset=["trade_date_ist"]).sort_values("trade_date_ist").reset_index(drop=True)

#     cal = pd.DataFrame({"trade_date_ist": expected_dates})
#     merged = cal.merge(out, on="trade_date_ist", how="left")

#     carry_cols = [
#         "close_native",
#         "symbol",
#         "source_name",
#         "source_url",
#         "source_detail",
#         "source_priority",
#     ]
#     merged[carry_cols] = merged[carry_cols].ffill()

#     was_missing = merged["close_native"].isna()
#     merged["quality_flag"] = merged["quality_flag"].fillna("")

#     merged.loc[merged["trade_date_ist"].isin(set(out["trade_date_ist"])), "quality_flag"] = (
#         merged.loc[merged["trade_date_ist"].isin(set(out["trade_date_ist"])), "quality_flag"]
#         .astype(str)
#         .str.strip()
#     )

#     filled_mask = ~merged["trade_date_ist"].isin(set(out["trade_date_ist"]))
#     merged.loc[filled_mask, "quality_flag"] = merged.loc[filled_mask, "quality_flag"].astype(str).replace("", "CARRY_FORWARD_BUSINESS_DAY")
#     merged.loc[filled_mask & merged["source_name"].notna(), "source_name"] = (
#         merged.loc[filled_mask & merged["source_name"].notna(), "source_name"].astype(str) + "+CARRY_FORWARD"
#     )
#     merged.loc[filled_mask & merged["source_detail"].notna(), "source_detail"] = (
#         merged.loc[filled_mask & merged["source_detail"].notna(), "source_detail"].astype(str) + f"|{label}"
#     )

#     merged = merged.dropna(subset=["close_native"]).reset_index(drop=True)
#     return merged[base_cols]

# ============================================================
# FRED
# ============================================================
def fetch_fred_reference(series_id: str, symbol: str) -> pd.DataFrame:
    if not series_id:
        return pd.DataFrame()

    url = "https://api.stlouisfed.org/fred/series/observations"
    fred_start = (START_TS - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    fred_end = "9999-12-31"
    
    params = {
    "series_id": series_id,
    "file_type": "json",
    "observation_start": fred_start,
    "observation_end": fred_end,
    }
    
    if FRED_API_KEY:
        params["api_key"] = FRED_API_KEY

    resp = SESSION.get(url, params=params, timeout=45)
    resp.raise_for_status()
    payload = resp.json()

    print(f"DEBUG FRED payload keys for {series_id}:", list(payload.keys()))
    print(f"DEBUG FRED observations count for {series_id}:", len(payload.get("observations", [])))
    if payload.get("observations"):
        print("DEBUG FRED first obs:", payload["observations"][0])
        print("DEBUG FRED last obs:", payload["observations"][-1])

    if "error_code" in payload:
        raise RuntimeError(f"FRED error for {series_id}: {payload}")

    rows = payload.get("observations", [])
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame()

    date_col = choose_col(df, ["date"])
    value_col = choose_col(df, ["value"])
    if date_col is None or value_col is None:
        raise RuntimeError(f"FRED payload missing expected columns for {series_id}")

    out = pd.DataFrame(
        {
            "trade_date_ist": pd.to_datetime(df[date_col], errors="coerce").dt.date,
            "close_native": pd.to_numeric(df[value_col], errors="coerce"),
            "symbol": symbol,
            "source_name": "FRED",
            "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
            "source_detail": series_id,
            "source_priority": 1,
            "quality_flag": "",
        }
    )
    return out.dropna(subset=["trade_date_ist", "close_native"]).reset_index(drop=True)


# ============================================================
# EIA
# ============================================================
def fetch_eia_reference(facets: Optional[Dict[str, Any]], symbol: str, detail_name: str) -> pd.DataFrame:
    if not EIA_SPOT_ROUTE or not facets:
        return pd.DataFrame()

    url = f"https://api.eia.gov/v2/{EIA_SPOT_ROUTE}"
    params: Dict[str, Any] = {
        "frequency": "daily",
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "start": START_TS.strftime("%Y-%m-%d"),
        "end": END_TS.strftime("%Y-%m-%d"),
    }
    if EIA_API_KEY:
        params["api_key"] = EIA_API_KEY

    for facet_name, facet_values in facets.items():
        if facet_values is None:
            continue
        if not isinstance(facet_values, list):
            facet_values = [facet_values]
        for i, v in enumerate(facet_values):
            params[f"facets[{facet_name}][{i}]"] = v

    resp = SESSION.get(url, params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    print(f"DEBUG EIA url for {symbol}:", resp.url)
    print(f"DEBUG EIA top-level keys for {symbol}:", list(payload.keys()))
    print(f"DEBUG EIA row count for {symbol}:", len(payload.get("response", {}).get("data", [])))
    rows = payload.get("response", {}).get("data", [])
    if rows:
        print("DEBUG EIA first row:", rows[0])
        print("DEBUG EIA last row:", rows[-1])

    response_obj = payload.get("response", {})
    rows = response_obj.get("data", [])
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame()

    period_col = choose_col(df, ["period", "date"])
    value_col = choose_col(df, ["value"])
    if period_col is None or value_col is None:
        raise RuntimeError(f"EIA payload missing expected columns for {symbol}")

    out = pd.DataFrame(
        {
            "trade_date_ist": pd.to_datetime(df[period_col], errors="coerce").dt.date,
            "close_native": pd.to_numeric(df[value_col], errors="coerce"),
            "symbol": symbol,
            "source_name": "EIA",
            "source_url": url,
            "source_detail": detail_name,
            "source_priority": 2,
            "quality_flag": "",
        }
    )
    return out.dropna(subset=["trade_date_ist", "close_native"]).reset_index(drop=True)


# ============================================================
# BUILDERS
# ============================================================
def build_wti_reference() -> pd.DataFrame:
    candidates = []

    fred_df = fetch_fred_reference(FRED_WTI_SERIES_ID, "WTISPOT")
    if not fred_df.empty:
        candidates.append(fred_df)

    wti_facets = safe_json_dict(EIA_WTI_FACETS_JSON, "EIA_WTI_FACETS_JSON")
    eia_df = fetch_eia_reference(wti_facets, "WTISPOT", "WTI_EIA_SPOT")
    if not eia_df.empty:
        candidates.append(eia_df)

    if not candidates:
        raise RuntimeError("WTI spot reference: no rows returned from either FRED or EIA")

    return finalize_reference(
        pd.concat(candidates, ignore_index=True, sort=False),
        symbol="WTISPOT",
        preferred_source_order=["fred", "eia"],
    )


def build_brent_reference() -> pd.DataFrame:
    candidates = []

    print("DEBUG entering build_brent_reference with series:", repr(FRED_BRENT_SERIES_ID))

    fred_df = fetch_fred_reference(FRED_BRENT_SERIES_ID, "BRENTSPOT")
    print("DEBUG Brent FRED rows:", len(fred_df))
    if not fred_df.empty:
        print("DEBUG Brent FRED coverage:", fred_df["trade_date_ist"].min(), "->", fred_df["trade_date_ist"].max())
        candidates.append(fred_df)

    brent_facets = safe_json_dict(EIA_BRENT_FACETS_JSON, "EIA_BRENT_FACETS_JSON")
    print("DEBUG Brent EIA facets parsed:", brent_facets)
    eia_df = fetch_eia_reference(brent_facets, "BRENTSPOT", "BRENT_EIA_SPOT")
    print("DEBUG Brent EIA rows:", len(eia_df))
    if not eia_df.empty:
        candidates.append(eia_df)

    if not candidates:
        raise RuntimeError("Brent spot reference: no rows returned from either FRED or EIA")

    merged = finalize_reference(
        pd.concat(candidates, ignore_index=True, sort=False),
        symbol="BRENTSPOT",
        preferred_source_order=["fred", "eia"],
    )

    print("DEBUG Brent merged rows:", len(merged))
    return merged


# ============================================================
# DIAGNOSTICS
# ============================================================
def print_coverage_diag(name: str, df: pd.DataFrame) -> None:
    print(f"\n[{name}] rows={len(df)}")
    if df.empty:
        print(f"[{name}] EMPTY")
        return

    print(f"[{name}] coverage={df['trade_date_ist'].min()} -> {df['trade_date_ist'].max()}")
    print(f"[{name}] source_mix={df['source_name'].value_counts(dropna=False).to_dict()}")

    expected = set(pd.date_range(START_TS, END_TS, freq="B").date)
    actual = set(df["trade_date_ist"].dropna().tolist())
    missing = sorted(expected - actual)

    print(f"[{name}] expected_weekdays={len(expected)} actual_dates={len(actual)} missing_weekdays={len(missing)}")
    if missing:
        preview = missing[:15]
        suffix = " ..." if len(missing) > 15 else ""
        print(f"[{name}] missing_preview={preview}{suffix}")


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    print(f"Building spot references for {START_DATE} -> {END_DATE}")
    print(f"Output dir: {OUTPUT_DIR.resolve()}")

    print("DEBUG FRED_APIKEY set:", bool(FRED_API_KEY))
    print("DEBUG EIA_APIKEY set:", bool(EIA_API_KEY))
    print("DEBUG FRED_WTI_SERIES_ID:", repr(FRED_WTI_SERIES_ID))
    print("DEBUG EIA_SPOT_ROUTE:", repr(EIA_SPOT_ROUTE))
    print("DEBUG EIA_WTI_FACETS_JSON:", repr(EIA_WTI_FACETS_JSON))
    print("DEBUG EIA_BRENT_FACETS_JSON:", repr(EIA_BRENT_FACETS_JSON))
    wti = build_wti_reference()
    
    print("DEBUG FRED_BRENT_SERIES_ID:", repr(FRED_BRENT_SERIES_ID))
    print("DEBUG OUTPUT_DIR raw:", repr(str(OUTPUT_DIR)))
    brent = build_brent_reference()

    write_both(wti, "wti_spot_daily_reference_ist")
    write_both(brent, "brent_spot_daily_reference_ist")

    print_coverage_diag("WTI", wti)
    print_coverage_diag("BRENT", brent)

    print("\nDone.")
    print(f"Wrote: {OUTPUT_DIR / 'wti_spot_daily_reference_ist.csv'}")
    print(f"Wrote: {OUTPUT_DIR / 'wti_spot_daily_reference_ist.xlsx'}")
    print(f"Wrote: {OUTPUT_DIR / 'brent_spot_daily_reference_ist.csv'}")
    print(f"Wrote: {OUTPUT_DIR / 'brent_spot_daily_reference_ist.xlsx'}")


if __name__ == "__main__":
    main()