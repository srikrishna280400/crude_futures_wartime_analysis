#phase2_analysis.py

from __future__ import annotations
import os
import re
import json
from pathlib import Path
from sys import flags
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from pandas._libs.tslibs.nattype import NaTType
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import xml.etree.ElementTree as ET 
from email.utils import parsedate_to_datetime
import hashlib
from dotenv import load_dotenv
import gzip
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import random
from collections import defaultdict
load_dotenv()

START_DATE = os.getenv("START_DATE", "2026-03-01")
END_DATE = os.getenv("END_DATE", "2026-06-04")
TZ_NAME = os.getenv("TZ", "Asia/Kolkata")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output r"))
RAW_NEWS_INPUT_CSV = os.getenv("RAW_NEWS_INPUT_CSV", "")
TOP_HEADLINES_PER_DAY = int(os.getenv("TOP_HEADLINES_PER_DAY", "3"))
RAW_NEWS_CANDIDATES_FILENAME = os.getenv("RAW_NEWS_CANDIDATES_FILENAME", "news_raw_candidates.csv")
REBUILD_RAW_NEWS_EACH_RUN = int(os.getenv("REBUILD_RAW_NEWS_EACH_RUN", "1"))

LIVE_NEWS_TIMEOUT_SEC = int(os.getenv("LIVE_NEWS_TIMEOUT_SEC", "20"))
SHOCK_BAR_THRESHOLD_PCT = float(os.getenv("SHOCK_BAR_THRESHOLD_PCT", "0.45"))
EVENT_SHOCK_WINDOW_MIN = int(os.getenv("EVENT_SHOCK_WINDOW_MIN", "120"))
CAUSAL_NEWS_MIN_SCORE = float(os.getenv("CAUSAL_NEWS_MIN_SCORE", "10"))

CNN_RSS_URL = os.getenv("CNN_RSS_URL", "http://rss.cnn.com/rss/cnn_topstories.rss")
ALJAZEERA_RSS_URL = os.getenv("ALJAZEERA_RSS_URL", "https://www.aljazeera.com/xml/rss/all.xml")

NEWS_SOURCES = ["al jazeera", "cnn"]
HIST_NEWS_CACHE_DIR = OUTPUT_DIR / "news_cache"
HIST_NEWS_URL_CACHE = OUTPUT_DIR / "news_url_cache.csv"
HIST_NEWS_ARTICLE_CACHE = OUTPUT_DIR / "news_article_cache.csv"
HIST_NEWS_MAX_URLS_PER_DAY = int(os.getenv("HIST_NEWS_MAX_URLS_PER_DAY", "20"))
HIST_NEWS_MAX_ARTICLES_PER_DAY = int(os.getenv("HIST_NEWS_MAX_ARTICLES_PER_DAY", "8"))
HIST_NEWS_REQUEST_TIMEOUT_SEC = int(os.getenv("HIST_NEWS_REQUEST_TIMEOUT_SEC", "20"))
HIST_NEWS_RETRY_COUNT = int(os.getenv("HIST_NEWS_RETRY_COUNT", "2"))
HIST_NEWS_REQUEST_TIMEOUT_SEC = int(os.getenv("HIST_NEWS_REQUEST_TIMEOUT_SEC", "25"))
HIST_NEWS_MAX_SITEMAPS_PER_SOURCE = int(os.getenv("HIST_NEWS_MAX_SITEMAPS_PER_SOURCE", "40"))
HIST_NEWS_MAX_URLS_PER_SOURCE = int(os.getenv("HIST_NEWS_MAX_URLS_PER_SOURCE", "1200"))
HIST_NEWS_MIN_CANDIDATE_SCORE = int(os.getenv("HIST_NEWS_MIN_CANDIDATE_SCORE", "4"))
HIST_NEWS_PER_HOST_DELAY_SEC = float(os.getenv("HIST_NEWS_PER_HOST_DELAY_SEC", "1.25"))
HIST_NEWS_PER_HOST_BACKOFF_403_SEC = float(os.getenv("HIST_NEWS_PER_HOST_BACKOFF_403_SEC", "8.0"))
HIST_NEWS_PER_HOST_BACKOFF_429_SEC = float(os.getenv("HIST_NEWS_PER_HOST_BACKOFF_429_SEC", "12.0"))
HIST_NEWS_FETCH_RETRIES = int(os.getenv("HIST_NEWS_FETCH_RETRIES", "4"))
HIST_NEWS_ALLOW_RSS_PARTIAL_PROMOTION = int(os.getenv("HIST_NEWS_ALLOW_RSS_PARTIAL_PROMOTION", "1"))
HIST_NEWS_CACHE_DIR = OUTPUT_DIR / "news_cache"
HIST_NEWS_DISCOVERY_CACHE = OUTPUT_DIR / "news_discovery_cache.csv"
HIST_NEWS_ARTICLE_CACHE = OUTPUT_DIR / "news_article_cache.csv"
HIST_NEWS_DISCOVERY_DIAG = OUTPUT_DIR / "news_discovery_diagnostics.csv"
HIST_NEWS_ARTICLE_DIAG = OUTPUT_DIR / "news_article_diagnostics.csv"
HIST_NEWS_RAW_CSV = OUTPUT_DIR / "news_raw_candidates.csv"
HIST_NEWS_RAW_XLSX = OUTPUT_DIR / "news_raw_candidates.xlsx"
HIST_NEWS_CONCURRENCY = int(os.getenv("HIST_NEWS_CONCURRENCY", "8"))
HIST_NEWS_MAX_SITEMAP_DEPTH = int(os.getenv("HIST_NEWS_MAX_SITEMAP_DEPTH", "3"))
HIST_NEWS_MIN_TEXT_SCORE = int(os.getenv("HIST_NEWS_MIN_TEXT_SCORE", "2"))

LIVE_NEWS_SOURCE_CONFIG = [
    {
        "source_key": "al_jazeera",
        "source_name": "Al Jazeera",
        "kind": "historical",
        "base_url": "https://www.aljazeera.com",
        "rss_url": ALJAZEERA_RSS_URL,
        "sitemap_urls": [
            "https://www.aljazeera.com/sitemap.xml",
            "https://www.aljazeera.com/sitemap_index.xml",
            "https://www.aljazeera.com/wp-sitemap.xml",
            "https://www.aljazeera.com/news-sitemap.xml",
            "https://www.aljazeera.com/sitemaps/post-sitemap.xml",
            "https://www.aljazeera.com/sitemaps/post-sitemap1.xml",
            "https://www.aljazeera.com/sitemaps/post-sitemap2.xml",
            "https://www.aljazeera.com/sitemaps/news-sitemap.xml",
            "https://www.aljazeera.com/sitemaps/google-news-sitemap.xml",
        ],
        "allow_url_regex": r"^https?://www\.aljazeera\.com/news/\d{4}/\d{1,2}/\d{1,2}/",
        "deny_url_regexes": [
            r"/opinions?/",
            r"/features?/",
            r"/analysis/",
            r"/video/",
            r"/videos/",
            r"/audio/",
            r"/podcasts?/",
            r"/gallery/",
            r"/photos?/",
            r"/interactive/",
            r"/liveblog/",
            r"/live-news/",
            r"/sports?/",
        ],
    },
    {
        "source_key": "cnn",
        "source_name": "CNN",
        "kind": "historical",
        "base_url": "https://www.cnn.com",
        "rss_url": CNN_RSS_URL,
        "sitemap_urls": [
            "https://www.cnn.com/sitemaps/sitemap-index.xml",   # most likely root
            "https://www.cnn.com/sitemap.xml",
            "https://www.cnn.com/sitemap/article.xml",           # note: no 's' on sitemap
            "https://www.cnn.com/sitemaps/cnn/index.xml",
            "https://www.cnn.com/sitemaps/article.xml",
        ],
        "allow_url_regex": r"^https?://(www|edition)\.cnn\.com/\d{4}/\d{2}/\d{2}/",
        "deny_url_regexes": [
            r"/opinions?/",
            r"/analysis/",
            r"/videos?/",
            r"/audio/",
            r"/podcasts?/",
            r"/gallery/",
            r"/photos?/",
            r"/live-news/",
            r"/live-updates/",
            r"/style/",
            r"/travel/",
            r"/entertainment/",
            r"/underscored/",
            r"/sports?/",
        ],
    },
]

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

SESSION_WINDOW_RANK = {
    name: i for i, name in enumerate(SESSION_WINDOW_ORDER)
}

PREFERRED_LIVE_SOURCE_ORDER = [
    "al jazeera", "cnn", "reuters", "bbc", "bloomberg",
    "associated press", "ap ", "wsj", "wall street journal", "financial times",
]
PREFERRED_LIVE_SOURCE_SCORES = {
    "al jazeera": 1.00,
    "cnn": 0.90,
    "reuters": 0.95,
    "bbc": 0.85,
    "bloomberg": 0.92,
    "associated press": 0.93,
    "ap ": 0.93,
    "wsj": 0.88,
    "wall street journal": 0.88,
    "financial times": 0.87,
}

EVENT_CLUSTER_MINUTES = 90
MIN_EVENT_RELEVANCE_SCORE = 2.5
MIN_TRAIN_DAYS_WALK_FORWARD = 20
MIN_SETUP_OBS_WALK_FORWARD = 5
REACTION_HORIZONS_MINUTES = [30, 60, 120, 240]

STRICT_NEWS_MODE = int(os.getenv("STRICT_NEWS_MODE", "1"))
MAX_SYNTHETIC_DAY_SHARE = float(os.getenv("MAX_SYNTHETIC_DAY_SHARE", "0.35"))
MIN_PREFERRED_SOURCE_DAY_SHARE = float(os.getenv("MIN_PREFERRED_SOURCE_DAY_SHARE", "0.45"))
MIN_DATED_EVENT_DAY_SHARE = float(os.getenv("MIN_DATED_EVENT_DAY_SHARE", "0.60"))
MIN_VERIFIED_URL_DAY_SHARE = float(os.getenv("MIN_VERIFIED_URL_DAY_SHARE", "0.50"))

EIA_API_KEY = os.getenv("EIA_API_KEY", os.getenv("EIAAPIKEY", "")).strip()
EIA_CRUDE_INV_ROUTE = os.getenv("EIA_CRUDE_INV_ROUTE", "").strip().strip("/")
EIA_CRUDE_INV_EXPECTATIONS_CSV = os.getenv("EIA_CRUDE_INV_EXPECTATIONS_CSV", "").strip()
EIA_CRUDE_INV_SOURCE_URL = os.getenv("EIA_CRUDE_INV_SOURCE_URL", "https://www.eia.gov/petroleum/supply/weekly/")
EIA_CRUDE_INV_RELEASE_TZ = "America/New_York"
EIA_CRUDE_INV_RELEASE_HOUR_ET = int(os.getenv("EIA_CRUDE_INV_RELEASE_HOUR_ET", "10"))
EIA_CRUDE_INV_RELEASE_MINUTE_ET = int(os.getenv("EIA_CRUDE_INV_RELEASE_MINUTE_ET", "30"))
INVENTORY_EVENT_WINDOW_MIN = int(os.getenv("INVENTORY_EVENT_WINDOW_MIN", "60"))

# ============================================================
# HELPERS
# ============================================================

def add_inventory_overlap_flags(
    news_master: pd.DataFrame,
    window_min: int = INVENTORY_EVENT_WINDOW_MIN,
) -> pd.DataFrame:
    if news_master.empty:
        return news_master.copy()

    out = news_master.copy()
    out["trade_date_ist"] = parse_date_series(out["trade_date_ist"])
    out["event_datetime_ist"] = parse_dt_series(out["event_datetime_ist"])

    out["inventory_other_news_overlap_count"] = 0
    out["inventory_other_news_overlap_flag"] = False
    out["inventory_clean_signal_flag"] = True

    inv_idx = out.index[
        out.get("event_type", pd.Series("", index=out.index)).eq("eia_crude_inventory")
    ].tolist()

    for i in inv_idx:
        td = out["trade_date_ist"].iloc[i]
        ts = out["event_datetime_ist"].iloc[i]

        if pd.isna(ts):
            out.at[i, "inventory_clean_signal_flag"] = False
            continue

        try:
            ts = ts.tz_convert(TZ_NAME)
        except Exception:
            pass

        time_diff = (out["event_datetime_ist"] - ts).abs()

        g = out[
            (out["trade_date_ist"].eq(td)) &
            (out.index != i) &
            (out["event_datetime_ist"].notna()) &
            (time_diff <= pd.Timedelta(minutes=window_min))
        ].copy()

        cnt = len(g)
        out.at[i, "inventory_other_news_overlap_count"] = cnt
        out.at[i, "inventory_other_news_overlap_flag"] = cnt > 0
        out.at[i, "inventory_clean_signal_flag"] = cnt == 0

    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


def fetch_json(url: str, params: dict, timeout: int = 30) -> dict:
    resp = get_http_session().get(url, params=params, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.json()

def fetch_eia_crude_inventory_actuals(start_date: str, end_date: str) -> pd.DataFrame:
    if not EIA_CRUDE_INV_ROUTE:
        return pd.DataFrame(columns=["release_date", "actual_change_mmbbl"])

    url = f"https://api.eia.gov/v2/{EIA_CRUDE_INV_ROUTE}"
    params = {
        "api_key": EIA_API_KEY,
        "start": start_date,
        "end": end_date,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
    }
    payload = fetch_json(url, params=params)
    df = normalize_cols(pd.DataFrame(((payload.get("response") or {}).get("data") or [])))
    if df.empty:
        return pd.DataFrame(columns=["release_date", "actual_change_mmbbl"])

    date_col = choose_col(df, ["period", "date", "release_date", "week_ending"])
    change_col = choose_col(df, ["value", "weekly_change", "stocks_change", "crude_oil_stocks_change"])
    level_col = choose_col(df, ["stocks", "ending_stocks", "crude_stocks"])

    if not date_col:
        raise RuntimeError("EIA crude inventory payload missing date column")

    out = pd.DataFrame()
    out["release_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date

    if change_col:
        out["actual_change_mmbbl"] = pd.to_numeric(df[change_col], errors="coerce")
    elif level_col:
        tmp = pd.to_numeric(df[level_col], errors="coerce")
        out["actual_change_mmbbl"] = tmp.diff()
    else:
        raise RuntimeError("EIA crude inventory payload missing change/level column")

    out = out.dropna(subset=["release_date", "actual_change_mmbbl"]).copy()
    return out.sort_values("release_date").reset_index(drop=True)

def load_eia_crude_inventory_expectations() -> pd.DataFrame:
    if not EIA_CRUDE_INV_EXPECTATIONS_CSV or not Path(EIA_CRUDE_INV_EXPECTATIONS_CSV).exists():
        return pd.DataFrame(columns=["release_date", "expected_change_mmbbl"])

    df = normalize_cols(pd.read_csv(EIA_CRUDE_INV_EXPECTATIONS_CSV))
    date_col = choose_col(df, ["release_date", "date", "week_ending"])
    exp_col = choose_col(df, ["expected_change_mmbbl", "consensus_change_mmbbl", "projected_change_mmbbl"])

    if not date_col or not exp_col:
        raise RuntimeError("Inventory expectations CSV missing release_date / expected_change_mmbbl")

    out = pd.DataFrame()
    out["release_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    out["expected_change_mmbbl"] = pd.to_numeric(df[exp_col], errors="coerce")
    return out.dropna(subset=["release_date"]).sort_values("release_date").reset_index(drop=True)

def build_eia_inventory_event_rows(trade_dates: List) -> pd.DataFrame:
    actual = fetch_eia_crude_inventory_actuals(START_DATE, END_DATE)
    if actual.empty:
        return pd.DataFrame()

    exp = load_eia_crude_inventory_expectations()
    inv = actual.merge(exp, on="release_date", how="left")

    release_et = (
        pd.to_datetime(inv["release_date"], errors="coerce")
        .dt.tz_localize(EIA_CRUDE_INV_RELEASE_TZ)
        + pd.Timedelta(hours=EIA_CRUDE_INV_RELEASE_HOUR_ET, minutes=EIA_CRUDE_INV_RELEASE_MINUTE_ET)
    )
    inv["event_datetime_ist"] = release_et.dt.tz_convert(TZ_NAME)
    inv["trade_date_ist"] = inv["event_datetime_ist"].dt.date
    inv = inv[inv["trade_date_ist"].isin(set(trade_dates))].copy()

    inv["inventory_release_flag"] = True
    inv["inventory_release_type"] = "eia_crude_inventory"
    inv["inventory_release_source"] = "EIA"
    inv["inventory_actual_change_mmbbl"] = pd.to_numeric(inv["actual_change_mmbbl"], errors="coerce")
    inv["inventory_expected_change_mmbbl"] = pd.to_numeric(inv["expected_change_mmbbl"], errors="coerce")
    inv["inventory_surprise_mmbbl"] = inv["inventory_actual_change_mmbbl"] - inv["inventory_expected_change_mmbbl"]
    inv["inventory_surprise_abs_mmbbl"] = inv["inventory_surprise_mmbbl"].abs()
    inv["inventory_consensus_available_flag"] = inv["inventory_expected_change_mmbbl"].notna()

    inv["inventory_surprise_bias"] = np.select(
        [
            inv["inventory_surprise_mmbbl"] < 0,   # more draw / less build than expected
            inv["inventory_surprise_mmbbl"] > 0,   # more build / less draw than expected
        ],
        ["bullish", "bearish"],
        default="neutral",
    )

    inv["headline"] = inv.apply(
        lambda r: (
            f"EIA crude inventories: actual {r['inventory_actual_change_mmbbl']:.2f} "
            f"vs expected {r['inventory_expected_change_mmbbl']:.2f} mmbbl"
            if pd.notna(r["inventory_expected_change_mmbbl"])
            else f"EIA crude inventories: actual {r['inventory_actual_change_mmbbl']:.2f} mmbbl"
        ),
        axis=1,
    )

    inv["summary_1_sentence"] = inv.apply(
        lambda r: (
            f"Structured EIA inventory event. Surprise={r['inventory_surprise_mmbbl']:.2f} mmbbl, "
            f"bias={r['inventory_surprise_bias']}."
            if pd.notna(r["inventory_surprise_mmbbl"])
            else "Structured EIA inventory event with no consensus surprise available."
        ),
        axis=1,
    )

    inv["body_text"] = inv["summary_1_sentence"]
    inv["source_name"] = "EIA"
    inv["source_url"] = EIA_CRUDE_INV_SOURCE_URL
    inv["event_datetime_original"] = inv["event_datetime_ist"].astype(str)
    inv["keyword_relevance_score"] = 10
    inv["discovery_method"] = "structured_eia_api"
    inv["coverage_verified_flag"] = True
    inv["news_row_quality"] = "structured_eia_inventory"

    inv["event_type"] = "eia_crude_inventory"
    inv["market_interpretation_bucket"] = np.select(
        [inv["inventory_surprise_bias"].eq("bullish"), inv["inventory_surprise_bias"].eq("bearish")],
        ["inventory_draw_bullish", "inventory_build_bearish"],
        default="inventory_neutral",
    )
    inv["expected_wti_bias"] = np.select(
        [inv["inventory_surprise_bias"].eq("bullish"), inv["inventory_surprise_bias"].eq("bearish")],
        ["positive", "negative"],
        default="neutral",
    )
    inv["expected_brent_bias"] = inv["expected_wti_bias"]
    inv["inventory_flag"] = True

    cols = [
        "trade_date_ist", "event_datetime_original", "event_datetime_ist",
        "source_name", "source_url", "headline", "summary_1_sentence", "body_text",
        "keyword_relevance_score", "discovery_method", "coverage_verified_flag",
        "news_row_quality", "event_type", "market_interpretation_bucket",
        "expected_wti_bias", "expected_brent_bias", "inventory_flag",
        "inventory_release_flag", "inventory_release_type", "inventory_release_source",
        "inventory_actual_change_mmbbl", "inventory_expected_change_mmbbl",
        "inventory_surprise_mmbbl", "inventory_surprise_abs_mmbbl",
        "inventory_surprise_bias", "inventory_consensus_available_flag",
    ]
    return inv[cols].reset_index(drop=True)


def get_source_adapter(source_name: str) -> dict:
    s = str(source_name or "").strip().lower()
    if s == "cnn":
        return {
            "name": "CNN",
            "allowed_hosts": {"www.cnn.com", "edition.cnn.com", "cnn.com"},
            "high_conf_patterns": [
                r"^https?://(www|edition)\.cnn\.com/\d{4}/\d{2}/\d{2}/.+",
            ],
            "medium_conf_patterns": [
                r"^https?://(www|edition)\.cnn\.com/.+/.+",
            ],
            "non_article_patterns": [
                r"/videos?/",
                r"/video$",
                r"/live-news/",
                r"/live-updates/",
                r"/travel/",
                r"/style/",
                r"/cnn-underscored/",
                r"/underscored/",
                r"/weather/",
                r"/sports/",
                r"/audio/",
                r"/interactive/",
                r"/gallery/",
                r"/profiles?/",
                r"/search/",
                r"/politics/live-news/",
                r"/markets/live-news/",
            ],
            "preferred_jsonld_types": {"newsarticle", "article"},
        }
    if s == "al jazeera":
        return {
            "name": "Al Jazeera",
            "allowed_hosts": {"www.aljazeera.com", "aljazeera.com"},
            "high_conf_patterns": [
                r"^https?://www\.aljazeera\.com/.+/\d{4}/\d{1,2}/\d{1,2}/.+",
            ],
            "medium_conf_patterns": [
                r"^https?://www\.aljazeera\.com/(news|economy|features|middle-east|asia|africa|americas|politics)/.+",
            ],
            "non_article_patterns": [
                r"/program/",
                r"/video/",
                r"/videos/",
                r"/podcasts?/",
                r"/author/",
                r"/tag/",
                r"/tags/",
                r"/liveblog/",
                r"/live/",
                r"/sports/",
                r"/opinion/",
                r"/documentaries/",
                r"/weather/",
            ],
            "preferred_jsonld_types": {"newsarticle", "article"},
        }
    return {
        "name": source_name,
        "allowed_hosts": set(),
        "high_conf_patterns": [],
        "medium_conf_patterns": [],
        "non_article_patterns": [],
        "preferred_jsonld_types": {"newsarticle", "article"},
    }


def detect_block_or_interstitial(text: str, meta: dict) -> Tuple[bool, str]:
    body = str(text or "")
    low = body.lower()
    ctype = str(meta.get("content_type", "")).lower()

    if not body.strip():
        return True, "blank_body"

    patterns = {
        "access_denied": r"access denied",
        "just_a_moment": r"just a moment",
        "captcha": r"captcha",
        "verify_human": r"verify you are human|verify you'?re human|human verification",
        "bot_check": r"bot check|automated access|unusual traffic",
        "request_blocked": r"request blocked|forbidden",
        "enable_javascript": r"enable javascript|javascript required",
        "challenge": r"cf-browser-verification|cloudflare|akamai|perimeterx|px-captcha",
    }
    for name, pat in patterns.items():
        if re.search(pat, low, flags=re.I):
            return True, name

    if "text/html" not in ctype and "application/xhtml+xml" not in ctype and "xml" not in ctype:
        return True, "non_html_or_unsupported"

    return False, ""


def extract_date_from_url(url: str):
    s = str(url or "")
    m = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)", s)
    if not m:
        return pd.NaT
    try:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3))).date()
    except Exception:
        return pd.NaT

def score_news_candidate_url(url: str, cfg: dict, url_date_hint, lastmod_date_hint) -> dict:
    u = canonicalize_url(url)
    adapter = get_source_adapter(cfg.get("source_name", ""))
    score = 0
    reasons = []
    matched_regex = ""

    if pd.notna(url_date_hint):
        score += 5
        reasons.append("url_has_date")

    if any(re.search(p, u, flags=re.I) for p in adapter.get("non_article_patterns", [])):
        score -= 3
        reasons.append("non_article_pattern")

    for p in adapter.get("high_conf_patterns", []):
        if re.search(p, u, flags=re.I):
            score += 3
            matched_regex = p
            reasons.append("high_conf_pattern")
            break

    if not matched_regex:
        for p in adapter.get("medium_conf_patterns", []):
            if re.search(p, u, flags=re.I):
                score += 2
                matched_regex = p
                reasons.append("medium_conf_pattern")
                break

    if re.search(r"/(news|world|business|economy|middle-east|asia|africa|americas|politics)/", u, flags=re.I):
        score += 2
        reasons.append("article_section_token")

    keep_flag = score >= HIST_NEWS_MIN_CANDIDATE_SCORE
    reject_reason = "" if keep_flag else "candidate_score_below_threshold"

    return {
        "candidate_score": int(score),
        "candidate_reason": "|".join(reasons),
        "matched_regex": matched_regex,
        "keep_candidate_flag": bool(keep_flag),
        "reject_reason": reject_reason,
    }

def classify_sitemap_url_priority(sitemap_url: str, cfg: dict) -> int:
    s = str(sitemap_url or "").lower()
    score = 0
    if any(k in s for k in ["article", "news", "post", "story"]):
        score += 3
    if re.search(r"20\d{2}", s):
        score += 2
    if any(k in s for k in ["tag", "topic", "author", "video", "shopping", "underscored"]):
        score -= 3
    return score


def should_expand_sitemap_url(sitemap_url: str, cfg: dict) -> bool:
    return classify_sitemap_url_priority(sitemap_url, cfg) >= 0

def discover_sitemaps_from_robots_txt(base_url: str) -> List[str]:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return []
    robots_url = f"{base}/robots.txt"
    text, meta = fetch_url_payload(robots_url)
    if not meta.get("ok") or not text:
        return []
    urls = []
    for line in str(text).splitlines():
        if ":" not in line:
            continue
        left, right = line.split(":", 1)
        if left.strip().lower() == "sitemap":
            u = canonicalize_url(right.strip())
            if u and u not in urls:
                urls.append(u)
    return urls

def parse_article_datetime(
    text: str,
    source_url: str = "",
    fallback_date: Any = None,
) -> tuple[pd.Timestamp | NaTType, str]:
    if not text or not str(text).strip():
        if fallback_date is not None and pd.notna(fallback_date):
            try:
                base = pd.Timestamp(fallback_date)
                if base.tzinfo is None:
                    base = base.tz_localize(TZ_NAME)
                else:
                    base = base.tz_convert(TZ_NAME)
                return base, "fallback_date"
            except Exception:
                pass
        return pd.NaT, ""

    s = str(text).strip()

    try:
        ts = pd.to_datetime(s, utc=True, errors="coerce")
        if pd.notna(ts):
            return ts.tz_convert(TZ_NAME), "parsed_direct"
    except Exception:
        pass

    try:
        dt = parsedate_to_datetime(s)
        ts = pd.Timestamp(dt)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert(TZ_NAME), "parsed_rfc2822"
    except Exception:
        pass

    if fallback_date is not None and pd.notna(fallback_date):
        try:
            base = pd.Timestamp(fallback_date)
            if base.tzinfo is None:
                base = base.tz_localize(TZ_NAME)
            else:
                base = base.tz_convert(TZ_NAME)
            return base, "fallback_date"
        except Exception:
            pass

    return pd.NaT, ""


def is_hard_news_url(url: str, cfg: dict) -> bool:
    u = canonicalize_url(url)
    if not u:
        return False
    allow = cfg.get("allow_url_regex", "")
    if allow and not re.search(allow, u, flags=re.I):
        return False
    for pat in cfg.get("deny_url_regexes", []):
        if re.search(pat, u, flags=re.I):
            return False
    return True


def is_hard_news_headline(headline: str) -> bool:
    h = str(headline or "").strip().lower()
    if not h:
        return False
    bad_starts = [
        "opinion:", "analysis:", "explainer:", "watch:", "listen:",
        "photos:", "gallery:", "podcast:", "video:"
    ]
    if any(h.startswith(x) for x in bad_starts):
        return False
    return True


def extract_links_from_html(html: str, base_url: str) -> List[str]:
    hrefs = []
    for m in re.finditer(r'(?is)<a[^>]+href=["\\\'](.*?)["\\\']', html or ""):
        href = (m.group(1) or "").strip()
        if not href:
            continue
        href = urljoin(base_url, href)
        hrefs.append(canonicalize_url(href))
    return hrefs


def parse_xml_root(xml_text: str):
    try:
        return ET.fromstring(xml_text.encode("utf-8", errors="ignore"))
    except Exception:
        try:
            return ET.fromstring(xml_text)
        except Exception:
            return None


def localname(tag: str) -> str:
    return str(tag).split("}", 1)[-1].lower()


def parse_sitemap_document(xml_text: str) -> Tuple[str, List[dict]]:
    root = parse_xml_root(xml_text)
    if root is None:
        return "", []

    root_name = localname(root.tag)
    items = []

    if root_name == "sitemapindex":
        current: dict = {}
        for elem in root.iter():
            name = localname(elem.tag)
            txt = (elem.text or "").strip()
            if name == "sitemap":
                # flush the completed entry before starting a new one
                if current.get("loc"):
                    items.append(current.copy())
                current = {}
            elif name == "loc":
                current["loc"] = txt
            elif name == "lastmod":
                current["lastmod"] = txt
        # flush the last entry (may have no following <sitemap> tag)
        if current.get("loc"):
            items.append(current.copy())
        return "sitemapindex", items

    if root_name == "urlset":
        current = {}
        in_url = False
        for elem in root.iter():
            name = localname(elem.tag)
            txt = (elem.text or "").strip()
            if name == "url":
                # flush the completed URL entry before starting a new one
                if in_url and current.get("loc"):
                    items.append(current.copy())
                current = {}
                in_url = True
            elif in_url and name == "loc":
                current["loc"] = txt
            elif in_url and name == "lastmod":
                current["lastmod"] = txt
        # flush the last URL entry
        if in_url and current.get("loc"):
            items.append(current.copy())
        for item in items:
            item["loc"] = canonicalize_url(item.get("loc", ""))
        return "urlset", items

    return "", []


def fetch_rss_feed(source_name: str, feed_url: str) -> pd.DataFrame:
    rows = []
    text, meta = fetch_url_payload(feed_url)
    if not meta.get("ok") or not text:
        return pd.DataFrame()

    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except Exception:
        try:
            root = ET.fromstring(text)
        except Exception:
            return pd.DataFrame()

    items = root.findall(".//item")
    for item in items:
        title = clean_headline_text(item.findtext("title") or "")
        link = canonicalize_url(item.findtext("link") or "")
        summary = re.sub(r"\s+", " ", strip_tags_basic(item.findtext("description") or "")).strip()
        pub = (item.findtext("pubDate") or item.findtext("published") or "").strip()
        ts = parse_rss_datetime(pub)

        rows.append({
            "source_name": source_name,
            "source_url": link,
            "headline": title,
            "summary_1_sentence": summary,
            "event_datetime_original": pub,
            "event_datetime_ist": ts,
            "trade_date_ist": pd.to_datetime(ts, errors="coerce").date() if pd.notna(ts) else pd.NaT,
            "discovery_method": "rss",
            "rss_guid": (item.findtext("guid") or "").strip(),
            "rss_pubdate_present": bool(pub),
            "rss_confidence_score": int(3 + (1 if title else 0) + (2 if pd.notna(ts) else 0) + (1 if link else 0)),
            "candidate_keep_flag": True,
            "extraction_keep_flag": True,
            "event_promote_flag": True,
            "coverage_verified_flag": False,
            "news_row_quality": "rss_only_partial",
            "normalized_canonical_key": normalize_canonical_story_key(link, source_name),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.drop_duplicates(subset=["source_name", "normalized_canonical_key"]).reset_index(drop=True)


def discover_urls_from_sitemaps(cfg: dict, min_date, max_date) -> Tuple[pd.DataFrame, pd.DataFrame]:
    discovered = []
    diag = []

    _robots_found = discover_sitemaps_from_robots_txt(cfg.get("base_url", ""))
    _hardcoded = list(cfg.get("sitemap_urls", []))

    _seen_seed = {}
    for _u in _robots_found + _hardcoded:
        cu = canonicalize_url(_u)
        if cu and cu not in _seen_seed:
            _seen_seed[cu] = None
    _all_seeds = list(_seen_seed.keys())

    print(f"[DISCOVERY] {cfg['source_name']} sitemap seeds: robots_txt={len(_robots_found)} hardcoded={len(_hardcoded)} total={len(_all_seeds)}")

    queue = [(_u, 0, _u) for _u in _all_seeds]
    seen = set()
    sitemap_fetch_count = 0

    while queue:
        sitemap_url, depth, seed_url = queue.pop(0)
        sitemap_url = canonicalize_url(sitemap_url)
        if not sitemap_url or sitemap_url in seen or depth > HIST_NEWS_MAX_SITEMAP_DEPTH:
            continue
        if sitemap_fetch_count >= HIST_NEWS_MAX_SITEMAPS_PER_SOURCE:
            break
        if depth > 0 and not should_expand_sitemap_url(sitemap_url, cfg):
            diag.append({
                "record_type": "sitemap_fetch",
                "source_name": cfg["source_name"],
                "seed_url": seed_url,
                "sitemap_url": sitemap_url,
                "depth": depth,
                "ok": False,
                "status_code": np.nan,
                "doc_type": "",
                "item_count": 0,
                "keep_sitemap_flag": False,
                "sitemap_priority_score": classify_sitemap_url_priority(sitemap_url, cfg),
                "reject_reason": "low_priority_sitemap_branch",
                "error": "",
            })
            continue

        seen.add(sitemap_url)
        sitemap_fetch_count += 1

        text, meta = fetch_url_payload(sitemap_url)
        doc_type, items = parse_sitemap_document(text) if meta.get("ok") else ("", [])

        diag.append({
            "record_type": "sitemap_fetch",
            "source_name": cfg["source_name"],
            "seed_url": seed_url,
            "sitemap_url": sitemap_url,
            "depth": depth,
            "ok": meta.get("ok", False),
            "status_code": meta.get("status_code", np.nan),
            "doc_type": doc_type,
            "item_count": len(items),
            "keep_sitemap_flag": bool(meta.get("ok") and bool(doc_type)),
            "sitemap_priority_score": classify_sitemap_url_priority(sitemap_url, cfg),
            "reject_reason": "" if meta.get("ok") and doc_type else (meta.get("error", "") or "bad_sitemap"),
            "error": meta.get("error", ""),
        })

        if not meta.get("ok") or not doc_type:
            continue

        if doc_type == "sitemapindex":
            child_rows = []
            for item in items:
                loc = canonicalize_url(item.get("loc", ""))
                if not loc or loc in seen:
                    continue
                child_rows.append((classify_sitemap_url_priority(loc, cfg), loc))
            child_rows = sorted(child_rows, key=lambda x: (-x[0], x[1]))
            for _, loc in child_rows:
                queue.append((loc, depth + 1, seed_url))
            continue

        if doc_type == "urlset":
            for item in items:
                loc = canonicalize_url(item.get("loc", ""))
                if not loc:
                    continue

                lastmod_raw = item.get("lastmod", "")
                try:
                    _lts = pd.to_datetime(str(lastmod_raw).strip(), errors="coerce") if str(lastmod_raw).strip() else pd.NaT
                    lastmod_date = _lts.date() if pd.notna(_lts) else pd.NaT
                except Exception:
                    lastmod_date = pd.NaT

                url_date = extract_date_from_url(loc)
                score_info = score_news_candidate_url(loc, cfg, url_date, lastmod_date)

                if pd.notna(url_date):
                    in_range = min_date <= url_date <= max_date
                else:
                    in_range = True

                keep_flag = bool(score_info["keep_candidate_flag"] and in_range)
                reject_reason = "" if keep_flag else (score_info["reject_reason"] or ("out_of_range" if not in_range else "candidate_rejected"))

                diag.append({
                    "record_type": "url_candidate",
                    "source_name": cfg["source_name"],
                    "source_key": cfg["source_key"],
                    "seed_url": seed_url,
                    "sitemap_url": sitemap_url,
                    "sitemap_depth": depth,
                    "source_url": loc,
                    "url_date_hint": url_date,
                    "lastmod_date_hint": lastmod_date,
                    "candidate_score": score_info["candidate_score"],
                    "candidate_reason": score_info["candidate_reason"],
                    "matched_regex": score_info["matched_regex"],
                    "keep_candidate_flag": keep_flag,
                    "reject_stage": "" if keep_flag else "candidate",
                    "reject_reason": reject_reason,
                    "discovered_at_utc": pd.Timestamp.now("UTC"),
                })

                if not keep_flag:
                    continue

                discovered.append({
                    "source_name": cfg["source_name"],
                    "source_key": cfg["source_key"],
                    "source_url": loc,
                    "final_candidate_url": loc,
                    "seed_url": seed_url,
                    "sitemap_url": sitemap_url,
                    "sitemap_depth": depth,
                    "url_date_hint": url_date,
                    "lastmod_date_hint": lastmod_date,
                    "candidate_score": score_info["candidate_score"],
                    "candidate_reason": score_info["candidate_reason"],
                    "matched_regex": score_info["matched_regex"],
                    "discovery_method": "sitemap",
                    "candidate_keep_flag": True,
                    "discovered_at_utc": pd.Timestamp.now("UTC"),
                })

                if len(discovered) >= HIST_NEWS_MAX_URLS_PER_SOURCE:
                    break

    url_df = pd.DataFrame(discovered)
    diag_df = pd.DataFrame(diag)

    if url_df.empty:
        return url_df, diag_df

    url_df["source_url"] = url_df["source_url"].map(canonicalize_url)
    url_df["normalized_canonical_key"] = url_df.apply(
        lambda r: normalize_canonical_story_key(r.get("source_url", ""), r.get("source_name", "")), axis=1
    )
    url_df = url_df.drop_duplicates(subset=["source_name", "normalized_canonical_key"]).reset_index(drop=True)
    return url_df, diag_df


def extract_article_row(url: str, source_name: str, discovery_method: str = "sitemap", rss_row: Optional[dict] = None, candidate_score: Optional[int] = None, matched_regex: str = "") -> Tuple[Optional[dict], dict]:
    html, meta = fetch_url_payload(url)

    diag = {
        "source_name": source_name,
        "source_url": canonicalize_url(url),
        "original_url": canonicalize_url(url),
        "final_url": canonicalize_url(meta.get("final_url") or url),
        "canonical_url": "",
        "normalized_canonical_key": "",
        "discovery_method": discovery_method,
        "candidate_score": candidate_score if candidate_score is not None else np.nan,
        "matched_regex": matched_regex,
        "article_type_signal": "",
        "title_source": "",
        "datetime_source": "",
        "description_source": "",
        "ok": meta.get("ok", False),
        "status_code": meta.get("status_code", np.nan),
        "error": meta.get("error", ""),
        "blocked_flag": meta.get("blocked_flag", False),
        "headline": "",
        "headline_preview": "",
        "event_datetime_original": "",
        "event_datetime_ist": "",
        "trade_date_ist": "",
        "keyword_relevance_score": 0,
        "extraction_quality": "",
        "kept": False,
        "reject_stage": "",
        "reject_reason": "",
    }

    if not meta.get("ok"):
        diag["reject_stage"] = "fetch"
        diag["reject_reason"] = meta.get("error", "fetch_failed")
        if rss_row and HIST_NEWS_ALLOW_RSS_PARTIAL_PROMOTION:
            rss_head = clean_headline_text(rss_row.get("headline", ""))
            rss_ts = rss_row.get("event_datetime_ist", pd.NaT)
            if rss_head and pd.notna(rss_ts):
                row = {
                    "source_name": source_name,
                    "source_url": canonicalize_url(url),
                    "headline": rss_head,
                    "summary_1_sentence": str(rss_row.get("summary_1_sentence", "") or "").strip(),
                    "body_text": "",
                    "event_datetime_original": str(rss_row.get("event_datetime_original", "") or "").strip(),
                    "event_datetime_ist": rss_ts,
                    "trade_date_ist": pd.to_datetime(rss_ts, errors="coerce").date(),
                    "keyword_relevance_score": int(keyword_score(" ".join([rss_head, str(rss_row.get('summary_1_sentence', ''))]))),
                    "discovery_method": discovery_method,
                    "coverage_verified_flag": False,
                    "news_row_quality": "rss_only_partial",
                    "extraction_keep_flag": True,
                    "event_promote_flag": True,
                }
                diag["headline"] = rss_head
                diag["headline_preview"] = rss_head[:180]
                diag["event_datetime_ist"] = str(rss_ts)
                diag["trade_date_ist"] = str(pd.to_datetime(rss_ts, errors="coerce").date())
                diag["datetime_source"] = "rss_pubdate"
                diag["extraction_quality"] = "rss_only_partial"
                diag["kept"] = True
                return row, diag
        return None, diag

    canonical = find_link_href(html, "canonical")
    canonical = canonicalize_url(canonical or meta.get("final_url") or url)
    diag["canonical_url"] = canonical
    diag["normalized_canonical_key"] = normalize_canonical_story_key(canonical, source_name)

    headline, title_source = extract_title_from_html(html)
    description, description_source = extract_description_from_html(html)

    diag["title_source"] = title_source
    diag["description_source"] = description_source
    diag["headline"] = headline
    diag["headline_preview"] = headline[:180]

    if not headline:
        diag["reject_stage"] = "extract"
        diag["reject_reason"] = "missing_headline"
        return None, diag

    json_ld_blobs = extract_json_ld_blobs(html)
    article_type_signal = "low"
    jsonld_types = set()
    for blob in json_ld_blobs:
        vals = [str(x).strip().lower() for x in deep_find_values(blob, "@type") if str(x).strip()]
        jsonld_types.update(vals)

    adapter = get_source_adapter(source_name)
    if jsonld_types & adapter.get("preferred_jsonld_types", set()):
        article_type_signal = "high"
    elif canonical and headline:
        article_type_signal = "medium"

    diag["article_type_signal"] = article_type_signal

    pub_candidates = [
        (find_meta_content(html, "property", "article:published_time"), "article:published_time"),
        (find_meta_content(html, "name", "parsely-pub-date"), "parsely-pub-date"),
        (find_meta_content(html, "name", "publish-date"), "publish-date"),
        (find_meta_content(html, "name", "date"), "meta:date"),
        (find_meta_content(html, "itemprop", "datePublished"), "itemprop:datePublished"),
    ]

    time_match = re.search(r'(?is)<time[^>]+datetime=["\'](.*?)["\']', html or "")
    if time_match:
        pub_candidates.append((time_match.group(1).strip(), "time:datetime"))

    for blob in json_ld_blobs:
        for v in deep_find_values(blob, "datePublished"):
            pub_candidates.append((str(v).strip(), "jsonld:datePublished"))

    if rss_row is not None:
        pub_candidates.append((str(rss_row.get("event_datetime_original", "") or "").strip(), "rss_pubdate"))

    event_ts = pd.NaT
    event_raw = ""
    datetime_source = ""

    fallback_url_date = extract_date_from_url(canonical)
    for raw_val, src in pub_candidates:
        ts, raw = parse_article_datetime(raw_val, source_url=canonical)
        if pd.notna(ts):
            event_ts = ts
            event_raw = raw
            datetime_source = src
            break

    if pd.isna(event_ts) and pd.notna(fallback_url_date):
        event_ts, event_raw = parse_article_datetime("", source_url=canonical, fallback_date=fallback_url_date)
        datetime_source = "url_date_hint"

    diag["event_datetime_original"] = event_raw
    diag["event_datetime_ist"] = str(event_ts)
    diag["trade_date_ist"] = str(pd.to_datetime(event_ts, errors="coerce").date()) if pd.notna(event_ts) else ""
    diag["datetime_source"] = datetime_source

    article_html_match = re.search(r"(?is)<article\b.*?</article>", html or "")
    article_html = article_html_match.group(0) if article_html_match else html
    body_text = strip_tags_basic(article_html)
    body_text = re.sub(r"\s+", " ", body_text).strip()

    text_blob = " ".join([headline, description, body_text[:4000]]).strip()
    kscore = int(keyword_score(text_blob))
    diag["keyword_relevance_score"] = kscore

    if meta.get("blocked_flag"):
        diag["reject_stage"] = "fetch"
        diag["reject_reason"] = "bot_block_or_non_article"
        return None, diag

    if article_type_signal == "low" and any(re.search(p, canonical, flags=re.I) for p in adapter.get("non_article_patterns", [])):
        diag["reject_stage"] = "extract"
        diag["reject_reason"] = "definite_non_article"
        return None, diag

    if pd.isna(event_ts):
        diag["extraction_quality"] = "extracted_missing_ts"
        diag["reject_stage"] = "event_acceptance"
        diag["reject_reason"] = "missing_event_ts"
        return None, diag

    extraction_quality = "extracted_verified"
    event_promote_flag = True
    if kscore < HIST_NEWS_MIN_TEXT_SCORE:
        extraction_quality = "extracted_low_relevance"
        event_promote_flag = False

    row = {
        "source_name": source_name,
        "source_url": canonical,
        "headline": headline,
        "summary_1_sentence": description,
        "body_text": body_text[:12000],
        "event_datetime_original": event_raw,
        "event_datetime_ist": event_ts,
        "trade_date_ist": pd.to_datetime(event_ts, errors="coerce").date(),
        "keyword_relevance_score": kscore,
        "discovery_method": discovery_method,
        "coverage_verified_flag": bool(canonical and pd.notna(event_ts)),
        "news_row_quality": extraction_quality,
        "candidate_keep_flag": True,
        "extraction_keep_flag": True,
        "event_promote_flag": bool(event_promote_flag),
        "title_source": title_source,
        "description_source": description_source,
        "datetime_source": datetime_source,
        "canonical_url": canonical,
        "normalized_canonical_key": normalize_canonical_story_key(canonical, source_name),
    }

    diag["extraction_quality"] = extraction_quality
    diag["kept"] = True
    if not event_promote_flag:
        diag["reject_stage"] = "event_acceptance"
        diag["reject_reason"] = "low_keyword_score"
    return row, diag


def fetch_feed_as_dataframe(feed_url: str, source_name: str = "") -> pd.DataFrame:
    return pd.DataFrame(fetch_rss_feed(source_name, feed_url))

def classify_headline_flags(headline: str, summary: str = "", overrides: Optional[dict] = None) -> dict:
    return classify_event(headline, summary, overrides)

def infer_event_type(headline: str, flags: dict) -> str:
    return str((flags or {}).get("event_type", "other"))

def infer_expected_bias(flags: dict, product: str = "WTI") -> str:
    key = "expected_wti_bias" if str(product).upper() == "WTI" else "expected_brent_bias"
    return str((flags or {}).get(key, "neutral"))

def infer_market_interpretation_bucket(flags: dict) -> str:
    return str((flags or {}).get("market_interpretation_bucket", "cross_currents"))

def compute_keyword_relevance_score(
    flags: dict,
    headline: str,
    summary: str = "",
    body_text: str = "",
) -> float:
    text = " ".join([
        str(headline or ""),
        str(summary or ""),
        str(body_text or "")[:4000],
    ]).strip()
    return float(keyword_score(text))

def compute_shock_proximity_score(trade_date, event_dt_ist: Optional[pd.Timestamp], shock_windows: pd.DataFrame) -> float:
    _, score, _ = shock_proximity_stats(shock_windows, trade_date, event_dt_ist)
    return float(score)

def is_synthetic_source(source_name: str) -> bool:
    s = str(source_name).strip().lower()
    return s in {"synthetic_absence_marker", "synthetic", "no_event", "no_event"}


def build_news_quality_diagnostics(news_master: pd.DataFrame, trade_dates) -> pd.DataFrame:
    if news_master.empty:
        return pd.DataFrame([
            {"metric": "fatal_nonewsmaster", "value": 1.0, "status": "FAIL", "detail": "newsmaster is empty"}
        ])

    nm = news_master.copy()
    nm["trade_date_ist"] = parse_date_series(nm["trade_date_ist"]) if "trade_date_ist" in nm.columns else pd.Series(dtype="object")

    event_type = nm.get("event_type", pd.Series("", index=nm.index)).fillna("").astype(str).str.strip().str.lower()
    source_name = nm.get("source_name", pd.Series("", index=nm.index)).fillna("").astype(str).str.strip().str.lower()
    row_quality = nm.get("news_row_quality", pd.Series("", index=nm.index)).fillna("").astype(str).str.strip().str.lower()

    synthetic_mask = (
        event_type.isin({"synthetic_absence_marker", "no_major_catalyst", "nomajorcatalyst"}) |
        source_name.eq("synthetic_absence_marker") |
        row_quality.eq("synthetic_absence_marker")
    )
    nm["is_real_event"] = ~synthetic_mask

    nm["has_ts"] = nm.get("event_datetime_ist", pd.Series(pd.NaT, index=nm.index)).notna()
    nm["has_url"] = nm.get("source_url", pd.Series("", index=nm.index)).fillna("").astype(str).str.len().gt(0)
    nm["is_partial"] = row_quality.isin({
        "rss_only_partial", "extracted_low_relevance",
        "extracted_missing_ts", "extracted_partial",
        "gdelt_title_only",
    })
    nm["is_preferred_source"] = source_name.apply(lambda s: any(k in s for k in PREFERRED_LIVE_SOURCE_ORDER))

    day_rows = []
    for d in trade_dates:
        g = nm[nm["trade_date_ist"].eq(d)].copy()
        if g.empty:
            day_rows.append({
                "trade_date_ist": d,
                "has_real_event": False,
                "has_preferred_source_event": False,
                "has_dated_real_event": False,
                "has_verified_url_event": False,
                "has_partial_evidence": False,
                "has_promoted_real_event": False,
            })
            continue

        real = g[g["is_real_event"]].copy()
        promoted = real[~real["is_partial"]].copy()
        day_rows.append({
            "trade_date_ist": d,
            "has_real_event": not real.empty,
            "has_preferred_source_event": bool(real["is_preferred_source"].any()) if not real.empty else False,
            "has_dated_real_event": bool(real["has_ts"].any()) if not real.empty else False,
            "has_verified_url_event": bool(real["has_url"].any()) if not real.empty else False,
            "has_partial_evidence": bool(g["is_partial"].any()),
            "has_promoted_real_event": not promoted.empty,
        })

    day_diag = pd.DataFrame(day_rows)
    total_days = max(len(day_diag), 1)

    synthetic_day_share = 1.0 - (day_diag["has_real_event"].sum() / total_days)
    preferred_source_day_share = day_diag["has_preferred_source_event"].sum() / total_days
    dated_event_day_share = day_diag["has_dated_real_event"].sum() / total_days
    verified_url_day_share = day_diag["has_verified_url_event"].sum() / total_days
    partial_evidence_day_share = day_diag["has_partial_evidence"].sum() / total_days
    promoted_real_event_day_share = day_diag["has_promoted_real_event"].sum() / total_days

    diag_rows = [
        {
            "metric": "synthetic_day_share",
            "value": synthetic_day_share,
            "threshold": MAX_SYNTHETIC_DAY_SHARE,
            "status": "PASS" if synthetic_day_share <= MAX_SYNTHETIC_DAY_SHARE else "FAIL",
            "detail": "share_of_days_without_real_event_rows"
        },
        {
            "metric": "preferred_source_day_share",
            "value": preferred_source_day_share,
            "threshold": MIN_PREFERRED_SOURCE_DAY_SHARE,
            "status": "PASS" if preferred_source_day_share >= MIN_PREFERRED_SOURCE_DAY_SHARE else "FAIL",
            "detail": "share_of_days_with_preferred_source_real_event"
        },
        {
            "metric": "dated_event_day_share",
            "value": dated_event_day_share,
            "threshold": MIN_DATED_EVENT_DAY_SHARE,
            "status": "PASS" if dated_event_day_share >= MIN_DATED_EVENT_DAY_SHARE else "FAIL",
            "detail": "share_of_days_with_real_event_and_timestamp"
        },
        {
            "metric": "verified_url_day_share",
            "value": verified_url_day_share,
            "threshold": MIN_VERIFIED_URL_DAY_SHARE,
            "status": "PASS" if verified_url_day_share >= MIN_VERIFIED_URL_DAY_SHARE else "FAIL",
            "detail": "share_of_days_with_real_event_and_source_url"
        },
        {
            "metric": "partial_evidence_day_share",
            "value": partial_evidence_day_share,
            "threshold": np.nan,
            "status": "INFO",
            "detail": "share_of_days_with_partial_raw_evidence"
        },
        {
            "metric": "promoted_real_event_day_share",
            "value": promoted_real_event_day_share,
            "threshold": np.nan,
            "status": "INFO",
            "detail": "share_of_days_with_promoted_real_event_rows"
        },
    ]
    return pd.DataFrame(diag_rows)


def enforce_news_quality_gate(news_quality_diag: pd.DataFrame):
    if not STRICT_NEWS_MODE:
        return

    if news_quality_diag.empty:
        raise RuntimeError("News quality diagnostics are empty under STRICT_NEWS_MODE=1")

    failing = news_quality_diag[news_quality_diag["status"].eq("FAIL")].copy()
    if failing.empty:
        return

    msg_lines = ["News quality gate failed:"]
    for _, r in failing.iterrows():
        metric = r.get("metric", "")
        value = r.get("value", "")
        threshold = r.get("threshold", "")
        detail = r.get("detail", "")
        msg_lines.append(f"- {metric}: value={value}, threshold={threshold}, detail={detail}")

    raise RuntimeError("\n".join(msg_lines))
    

def as_series(x: Any, index=None, name: str | None = None) -> pd.Series:
    if isinstance(x, pd.Series):
        return x
    if x is None:
        if index is None:
            return pd.Series(dtype="object", name=name)
        return pd.Series([pd.NA] * len(index), index=index, name=name, dtype="object")
    if isinstance(x, (list, tuple, np.ndarray, pd.Index)):
        return pd.Series(x, name=name)
    if index is not None:
        return pd.Series([x] * len(index), index=index, name=name)
    return pd.Series([x], name=name)

def to_numeric_series(x: Any, index=None, name: str | None = None) -> pd.Series:
    s = as_series(x, index=index, name=name)
    return pd.to_numeric(s, errors="coerce")

def to_float_scalar(x: Any) -> float:
    s = pd.to_numeric(pd.Series([x]), errors="coerce")
    v = s.iloc[0]
    return float(v) if pd.notna(v) else np.nan

def norm_col(x: str) -> str:
    x = str(x).strip()
    x = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", x)
    x = x.replace("%", "pct")
    x = x.replace("/", "_")
    x = x.replace("-", "_")
    x = re.sub(r"[^A-Za-z0-9_]+", "_", x)
    x = re.sub(r"_+", "_", x).strip("_").lower()
    return x


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [norm_col(c) for c in out.columns]
    return out


def choose_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = {norm_col(c): c for c in df.columns}
    for c in candidates:
        key = norm_col(c)
        if key in cols:
            return cols[key]
    return None


def read_csv_output(filename: str, required: bool = False) -> pd.DataFrame:
    path = OUTPUT_DIR / filename
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required file not found: {path}")
        return pd.DataFrame()
    return normalize_cols(pd.read_csv(path))


def write_csv(df: pd.DataFrame, filename: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / filename, index=False)


def parse_date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.date


def parse_dt_series(s: pd.Series) -> pd.Series:
    if s is None or len(s) == 0:
        return pd.Series(dtype="datetime64[ns, UTC]")
    x = pd.to_datetime(s, errors="coerce", utc=True)
    try:
        return x.dt.tz_convert(TZ_NAME)
    except Exception:
        return x


def boolize(v) -> bool:
    if pd.isna(v):
        return False
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "t"}


def hour_float(ts: pd.Timestamp) -> float:
    if pd.isna(ts):
        return np.nan
    h = ts.hour + ts.minute / 60.0
    if h < 3.5:
        h += 24.0
    return h


def assign_session_window(ts: pd.Timestamp) -> str:
    h = hour_float(ts)
    if pd.isna(h):
        return ""
    for name, (start_h, end_h) in SESSION_WINDOWS.items():
        if start_h <= h < end_h:
            return name
    return "other_valid_hours"


def resolve_session_window_from_row(row: pd.Series) -> str:
    existing = str(row.get("session_window_ist", "") or "").strip()
    if existing:
        return existing
    ts = row.get("timestamp_ist", pd.NaT)
    return assign_session_window(ts)


def resolve_session_window_from_ts_or_row(
    ts: pd.Timestamp,
    row: Optional[pd.Series] = None,
) -> str:
    if row is not None:
        existing = str(row.get("session_window_ist", "") or "").strip()
        if existing:
            return existing
    return assign_session_window(ts)


def sort_session_window_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "session_window_ist" not in df.columns:
        return pd.DataFrame() if df is None else df.copy()
    out = df.copy()
    out["session_window_rank"] = (
        out["session_window_ist"]
        .map(SESSION_WINDOW_RANK)
        .fillna(999)
        .astype(int)
    )
    sort_cols = [c for c in ["trade_date_ist", "session_window_rank", "timestamp_ist"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols)
    return out.drop(columns=["session_window_rank"], errors="ignore").reset_index(drop=True)


def pct_change(last_val, first_val):
    if pd.isna(last_val) or pd.isna(first_val) or first_val == 0:
        return np.nan
    return (last_val - first_val) / first_val * 100.0


def sign_bias_to_score(bias: str) -> int:
    b = str(bias).strip().lower()
    if b in {"positive", "bullish", "up", "long"}:
        return 1
    if b in {"negative", "bearish", "down", "short"}:
        return -1
    return 0


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def safe_json(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


# def source_rank(source_name: str) -> int:
#     s = str(source_name).lower()
#     if any(k in s for k in ["reuters", "bloomberg", "associated press", "ap "]):
#         return 5
#     if any(k in s for k in ["financial times", "ft", "wsj", "wall street journal", "cnbc"]):
#         return 4
#     if any(k in s for k in ["eia", "opec", "fred", "white house", "treasury", "state department"]):
#         return 4
#     if any(k in s for k in ["bbc", "guardian", "cnn", "fox", "al jazeera", "times"]):
#         return 3
#     return 2


def keyword_score(text: str) -> int:
    t = str(text).lower()
    score = 0
    rules = {
        "opec": 3,
        "production": 1,
        "output": 2,
        "supply": 2,
        "inventory": 2,
        "draw": 2,
        "build": 2,
        "iran": 3,
        "hormuz": 4,
        "strait": 1,
        "shipping": 3,
        "tanker": 3,
        "sanction": 3,
        "trump": 2,
        "tariff": 2,
        "fed": 2,
        "cpi": 2,
        "pce": 2,
        "dollar": 2,
        "usd": 2,
        "ceasefire": 3,
        "attack": 4,
        "missile": 4,
        "drone": 3,
        "risk": 1,
        "red sea": 3,
        "drawdown": 2,
    }
    for k, v in rules.items():
        if k in t:
            score += v
    return score


def contains_any(text: str, patterns: List[str]) -> bool:
    t = str(text).lower()
    return any(re.search(p, t) for p in patterns)


# ============================================================
# NEWS CLASSIFICATION
# ============================================================

def fetch_gdelt_news_for_daterange(start_date, end_date) -> pd.DataFrame:
    """
    Fetch crude-oil-relevant headlines from GDELT DOC v2 API.
    Free, no API key required, covers full historical date range.
    This is the primary fix for sitemap-only discovery failing on historical dates.
    """
    GDELT_OIL_QUERY = (
        '"crude oil" OR opec OR iran OR tanker OR sanction '
        'OR "red sea" OR eia OR ceasefire OR "oil price"'
    )
    _DOMAIN_TO_SOURCE = {
        "aljazeera": "Al Jazeera",
        "cnn.com": "CNN",
        "reuters": "Reuters",
        "bbc": "BBC",
        "bloomberg": "Bloomberg",
        "apnews": "Associated Press",
        "ap.org": "Associated Press",
        "wsj": "Wall Street Journal",
        "ft.com": "Financial Times",
    }

    start_ts = pd.Timestamp(str(start_date))
    end_ts = pd.Timestamp(str(end_date))
    all_articles: List[dict] = []
    chunk_days = 12

    print(f"[GDELT] fetching {start_date} to {end_date} in {chunk_days}-day chunks")
    current = start_ts
    while current <= end_ts:
        chunk_end = min(
            current + pd.Timedelta(days=chunk_days - 1) + pd.Timedelta(hours=23, minutes=59, seconds=59),
            end_ts,
        )
        params = {
            "query": GDELT_OIL_QUERY,
            "mode": "artlist",
            "format": "json",
            "startdatetime": current.strftime("%Y%m%d%H%M%S"),
            "enddatetime": chunk_end.strftime("%Y%m%d%H%M%S"),
            "maxrecords": "250",
            "sourcelang": "english",
        }
        try:
            data = fetch_json(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params=params,
                timeout=45,
            )
            chunk_articles = data.get("articles") or []
            all_articles.extend(chunk_articles)
            print(f"[GDELT] {current.date()} to {chunk_end.date()}: {len(chunk_articles)} articles")
        except Exception as _e:
            print(f"[GDELT] {current.date()} to {chunk_end.date()}: error={_e}")
        current = chunk_end + pd.Timedelta(seconds=1)
        time.sleep(2.0)

    if not all_articles:
        print("[GDELT] no articles returned — will rely on sitemap/RSS only")
        return pd.DataFrame()

    rows: List[dict] = []
    for art in all_articles:
        art_url = canonicalize_url(str(art.get("url", "") or ""))
        title = clean_headline_text(str(art.get("title", "") or ""))
        seendate = str(art.get("seendate", "") or "").strip()
        domain = str(art.get("domain", "") or "").lower()
        if not art_url or not title or len(title) < 8:
            continue

        ts = pd.NaT
        if seendate:
            try:
                ts = pd.to_datetime(seendate, format="%Y%m%dT%H%M%SZ", utc=True)
                if pd.notna(ts):
                    ts = ts.tz_convert(TZ_NAME)
            except Exception:
                try:
                    ts = pd.to_datetime(seendate, utc=True, errors="coerce")
                    if pd.notna(ts):
                        ts = ts.tz_convert(TZ_NAME)
                except Exception:
                    pass

        url_date = extract_date_from_url(art_url)
        trade_date = pd.to_datetime(ts).date() if pd.notna(ts) else url_date

        source_name = next(
            (v for k, v in _DOMAIN_TO_SOURCE.items() if k in domain),
            domain.replace("www.", "").split(".")[0].replace("-", " ").title(),
        )
        kscore = int(keyword_score(title))

        rows.append({
            "source_name": source_name,
            "source_url": art_url,
            "headline": title,
            "summary_1_sentence": "",
            "body_text": "",
            "event_datetime_original": seendate,
            "event_datetime_ist": ts,
            "trade_date_ist": trade_date,
            "keyword_relevance_score": kscore,
            "discovery_method": "gdelt_api",
            "coverage_verified_flag": bool(art_url and pd.notna(ts)),
            "news_row_quality": "gdelt_title_only",
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df[df["keyword_relevance_score"] >= HIST_NEWS_MIN_TEXT_SCORE].copy()
    df = df.drop_duplicates(subset=["source_url"]).reset_index(drop=True)
    df = df.sort_values(["trade_date_ist", "keyword_relevance_score"], ascending=[True, False])
    print(f"[GDELT] {len(df)} articles after keyword filter (min={HIST_NEWS_MIN_TEXT_SCORE})")
    return df.reset_index(drop=True)


def build_historical_news_bundle(trade_dates: List) -> dict:
    HIST_NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    trade_dates = sorted(pd.Series(trade_dates).dropna().tolist())
    if not trade_dates:
        return {
            "raw_news": pd.DataFrame(),
            "discovered_urls": pd.DataFrame(),
            "discovery_diag": pd.DataFrame(),
            "article_diag": pd.DataFrame(),
        }

    min_date = min(trade_dates)
    max_date = max(trade_dates)

    discovery_rows = []
    discovery_diag_rows = []
    rss_full_rows: List[pd.DataFrame] = []  # for direct promotion as article candidates

    cached_urls = read_cache_csv(HIST_NEWS_DISCOVERY_CACHE)
    if not cached_urls.empty:
        if "url_date_hint" in cached_urls.columns:
            cached_urls["url_date_hint"] = parse_date_series(cached_urls["url_date_hint"])
        if "lastmod_date_hint" in cached_urls.columns:
            cached_urls["lastmod_date_hint"] = parse_date_series(cached_urls["lastmod_date_hint"])

    for cfg in LIVE_NEWS_SOURCE_CONFIG:
        # Inject date-range-targeted monthly sitemaps; standard sitemaps only have last 48h
        _extra: List[str] = []
        _sk = cfg.get("source_key", "")
        _d = pd.Timestamp(min_date).replace(day=1)
        while _d <= pd.Timestamp(max_date):
            if _sk == "cnn":
                _extra.append(f"https://www.cnn.com/sitemaps/cnn/{_d.year}-{_d.month:02d}.xml")
            elif _sk == "al_jazeera":
                _extra.append(
                    f"https://www.aljazeera.com/wp-sitemap-posts-post-{_d.year}{_d.month:02d}.xml"
                )
            _d += pd.DateOffset(months=1)

        _cfg = dict(cfg)
        if _extra:
            _cfg["sitemap_urls"] = _extra + list(cfg.get("sitemap_urls", []))

        url_df, diag_df = discover_urls_from_sitemaps(_cfg, min_date, max_date)

        # Fix diagnostic: only count sitemap_fetch records, not url_candidate records
        _sf = (
            diag_df[diag_df["record_type"].eq("sitemap_fetch")].copy()
            if not diag_df.empty and "record_type" in diag_df.columns
            else diag_df.copy()
        )
        _ok = int(_sf["ok"].fillna(False).sum()) if not _sf.empty and "ok" in _sf.columns else 0
        _fail = int((~_sf["ok"].fillna(False)).sum()) if not _sf.empty and "ok" in _sf.columns else 0
        _codes = (
            _sf["status_code"].dropna().astype(int).value_counts().to_dict()
            if not _sf.empty and "status_code" in _sf.columns
            else {}
        )
        print(
            f"[DISCOVERY] {cfg['source_name']}: sitemap_fetches ok={_ok} fail={_fail} "
            f"status_codes={_codes}  url_df_rows={len(url_df)}"
        )

        if not url_df.empty:
            discovery_rows.append(url_df)
        if not diag_df.empty:
            discovery_diag_rows.append(diag_df)

        rss_rows = fetch_rss_feed(cfg["source_name"], cfg.get("rss_url", ""))
        print(f"[DISCOVERY] {cfg['source_name']} RSS: rows={len(rss_rows) if rss_rows is not None else 0}")

        if rss_rows is not None and not rss_rows.empty:
            # URL seeds for article fetch (existing behavior)
            rss_df = normalize_cols(rss_rows.copy())
            rss_df["source_url"] = rss_df["source_url"].astype(str).map(canonicalize_url)
            rss_df["source_name"] = cfg["source_name"]
            rss_df["url_date_hint"] = rss_df["source_url"].map(extract_date_from_url)
            rss_df["lastmod_date_hint"] = parse_date_series(
                rss_df.get("trade_date_ist", pd.Series([pd.NaT] * len(rss_df)))
            )
            rss_df["discovery_method"] = "rss"
            rss_df = rss_df[
                ["source_name", "source_url", "url_date_hint", "lastmod_date_hint", "discovery_method"]
            ].drop_duplicates()
            discovery_rows.append(rss_df)

            # Direct promotion: RSS rows already have headline + timestamp; no fetch needed
            _rss_full = rss_rows.copy()
            if "body_text" not in _rss_full.columns:
                _rss_full["body_text"] = ""
            rss_full_rows.append(_rss_full)

    discovered_urls = pd.concat(discovery_rows, ignore_index=True, sort=False) if discovery_rows else pd.DataFrame(
        columns=["source_name", "source_url", "url_date_hint", "lastmod_date_hint", "discovery_method"]
    )

    if not cached_urls.empty:
        discovered_urls = pd.concat([cached_urls, discovered_urls], ignore_index=True, sort=False)

    if not discovered_urls.empty:
        discovered_urls["source_url"] = discovered_urls["source_url"].astype(str).map(canonicalize_url)
        if "url_date_hint" in discovered_urls.columns:
            discovered_urls["url_date_hint"] = parse_date_series(discovered_urls["url_date_hint"])
        if "lastmod_date_hint" in discovered_urls.columns:
            discovered_urls["lastmod_date_hint"] = parse_date_series(discovered_urls["lastmod_date_hint"])

        # url_date_hint is extracted from URL path and is always the publication date.
        # lastmod_date_hint can be a re-crawl date after publication, causing false exclusions.
        if "url_date_hint" in discovered_urls.columns:
            rough_date = discovered_urls["url_date_hint"].copy()
        else:
            rough_date = pd.Series(pd.NaT, index=discovered_urls.index)
        _mask_no_url_date = rough_date.isna()
        if "lastmod_date_hint" in discovered_urls.columns:
            rough_date = rough_date.where(~_mask_no_url_date, discovered_urls["lastmod_date_hint"])

        def _date_in_range(v) -> bool:
            if v is None:
                return True
            try:
                if pd.isna(v):
                    return True
            except Exception:
                pass
            try:
                return min_date <= v <= max_date
            except Exception:
                return True  # undatable → include, let article-level extraction handle it

        in_range = rough_date.apply(_date_in_range)
        discovered_urls = discovered_urls[in_range.fillna(True)].copy()

        discovered_urls = discovered_urls.drop_duplicates(subset=["source_name", "source_url"]).copy()

        if "url_date_hint" in discovered_urls.columns:
            discovered_urls["day_rank"] = (
                discovered_urls
                .sort_values(["source_name", "url_date_hint", "source_url"])
                .groupby(["source_name", "url_date_hint"])
                .cumcount() + 1
            )
            discovered_urls = discovered_urls[
                discovered_urls["url_date_hint"].isna() | (discovered_urls["day_rank"] <= HIST_NEWS_MAX_URLS_PER_DAY)
            ].copy()
            discovered_urls = discovered_urls.drop(columns=["day_rank"], errors="ignore")

    discovered_urls = discovered_urls.reset_index(drop=True)
    print(
        f"[DISCOVERY] Final discovered_urls={len(discovered_urls)}  "
        f"min_date={min_date}  max_date={max_date}"
    )
    if not discovered_urls.empty and "source_name" in discovered_urls.columns:
        print(f"[DISCOVERY] by source: {discovered_urls['source_name'].value_counts().to_dict()}")
    write_cache_csv(discovered_urls, HIST_NEWS_DISCOVERY_CACHE)

    article_cache = read_cache_csv(HIST_NEWS_ARTICLE_CACHE)
    cached_article_rows = []
    article_diag_rows = []

    cached_url_set = set()
    if not article_cache.empty and "source_url" in article_cache.columns:
        article_cache["source_url"] = article_cache["source_url"].astype(str).map(canonicalize_url)
        cached_url_set = set(article_cache["source_url"].dropna().astype(str).tolist())

    to_fetch = []
    for _, r in discovered_urls.iterrows():
        src_url = canonicalize_url(r.get("source_url", ""))
        src_name = str(r.get("source_name", "") or "").strip()
        method = str(r.get("discovery_method", "sitemap") or "sitemap")
        if not src_url or not src_name:
            continue
        if src_url in cached_url_set:
            continue
        to_fetch.append((src_url, src_name, method))
        
    print(f"[FETCH] to_fetch={len(to_fetch)}  already_cached={len(cached_url_set)}")

    fresh_rows = []
    with ThreadPoolExecutor(max_workers=HIST_NEWS_CONCURRENCY) as ex:
        futs = [ex.submit(extract_article_row, url, src_name, method) for url, src_name, method in to_fetch]
        for fut in as_completed(futs):
            try:
                row, diag = fut.result()
            except Exception as e:
                row, diag = None, {
                    "source_name": "",
                    "source_url": "",
                    "discovery_method": "",
                    "ok": False,
                    "status_code": np.nan,
                    "error": str(e),
                    "headline": "",
                    "event_datetime_original": "",
                    "event_datetime_ist": "",
                    "trade_date_ist": "",
                    "keyword_relevance_score": 0,
                    "kept": False,
                    "reject_reason": "future_exception",
                }
            article_diag_rows.append(diag)
            if row:
                fresh_rows.append(row)
    _kept = sum(1 for d in article_diag_rows if d.get("kept"))
    _reject_breakdown: dict = {}
    for _d in article_diag_rows:
        if not _d.get("kept"):
            _r = _d.get("reject_reason", "unknown")
            _reject_breakdown[_r] = _reject_breakdown.get(_r, 0) + 1
    print(
        f"[FETCH] fresh_rows kept={_kept}  rejected={len(article_diag_rows)-_kept}  "
        f"reasons={_reject_breakdown}"
    )

    all_article_rows = []
    if not article_cache.empty:
        all_article_rows.append(article_cache)
    if fresh_rows:
        all_article_rows.append(pd.DataFrame(fresh_rows))
    # Direct RSS promotion: bypasses fetch entirely for recent dates
    for _rss_art_df in rss_full_rows:
        if not _rss_art_df.empty:
            all_article_rows.append(_rss_art_df)

    raw_news = pd.concat(all_article_rows, ignore_index=True, sort=False) if all_article_rows else pd.DataFrame()

    if article_diag_rows:
        article_diag = pd.DataFrame(article_diag_rows)
    else:
        article_diag = pd.DataFrame(columns=[
            "source_name", "source_url", "discovery_method", "ok", "status_code", "error",
            "headline", "event_datetime_original", "event_datetime_ist", "trade_date_ist",
            "keyword_relevance_score", "kept", "reject_reason"
        ])

    raw_news = standardize_raw_news_candidates(raw_news, trade_dates)

    if not raw_news.empty:
        text_blob = (
            raw_news[["headline", "summary_1_sentence", "body_text"]]
            .fillna("")
            .astype(str)
            .assign(body_text=lambda d: d["body_text"].str[:4000])
            .agg(" ".join, axis=1)
            .str.strip()
        )
        raw_news["keyword_relevance_score"] = text_blob.map(keyword_score).fillna(0).astype(int)
        raw_news = raw_news[raw_news["keyword_relevance_score"] >= HIST_NEWS_MIN_TEXT_SCORE].copy()
        print(f"[BUILD] after keyword filter (min={HIST_NEWS_MIN_TEXT_SCORE}): raw_news={len(raw_news)}")
        raw_news = raw_news.sort_values(
            ["trade_date_ist", "keyword_relevance_score", "event_datetime_ist", "source_name"],
            ascending=[True, False, True, True]
        ).copy()
        raw_news["row_rank_for_day"] = raw_news.groupby("trade_date_ist").cumcount() + 1
        raw_news = raw_news[raw_news["row_rank_for_day"] <= (HIST_NEWS_MAX_ARTICLES_PER_DAY * 2)].copy()
        raw_news = raw_news.drop(columns=["row_rank_for_day"], errors="ignore")

    if not raw_news.empty:
        write_cache_csv(raw_news, HIST_NEWS_ARTICLE_CACHE)

    discovery_diag = pd.concat(discovery_diag_rows, ignore_index=True, sort=False) if discovery_diag_rows else pd.DataFrame()

    return {
        "raw_news": raw_news.reset_index(drop=True),
        "discovered_urls": discovered_urls.reset_index(drop=True),
        "discovery_diag": discovery_diag.reset_index(drop=True),
        "article_diag": article_diag.reset_index(drop=True),
    }

def classify_event(headline: str, summary: str, overrides: Optional[dict] = None) -> dict:
    text = f"{headline} {summary}".strip().lower()
    overrides = overrides or {}

    trump_statement_flag = boolize(overrides.get("trump_statement_flag")) or contains_any(text, [r"\btrump\b"])
    trump_post_flag = boolize(overrides.get("trump_post_flag")) or contains_any(text, [r"\btruth social\b", r"\bpost(ed)?\b"])
    iran_hormuz_flag = boolize(overrides.get("iran_hormuz_flag")) or contains_any(text, [r"\biran\b", r"\bhormuz\b", r"\bstrait of hormuz\b"])
    shipping_disruption_flag = boolize(overrides.get("shipping_disruption_flag")) or contains_any(text, [r"\bshipping\b", r"\btanker\b", r"\bmaritime\b", r"\bred sea\b"])
    sanctions_flag = boolize(overrides.get("sanctions_flag")) or contains_any(text, [r"\bsanction", r"\bembargo"])
    talks_negotiation_flag = boolize(overrides.get("talks_negotiation_flag")) or contains_any(text, [r"\btalks?\b", r"\bnegotiat", r"\bdiploma"])
    ceasefire_flag = boolize(overrides.get("ceasefire_flag")) or contains_any(text, [r"\bceasefire\b", r"\btruce\b", r"\bde-escalat"])
    attack_threat_flag = boolize(overrides.get("attack_threat_flag")) or contains_any(text, [r"\battack\b", r"\bthreat\b", r"\bmissile\b", r"\bdrone\b", r"\bstrike\b"])
    opec_supply_flag = boolize(overrides.get("opec_supply_flag")) or contains_any(text, [r"\bopec\b", r"\bopec\+\b", r"\bquota\b", r"\boutput\b", r"\bproduction\b"])
    inventory_flag = boolize(overrides.get("inventory_flag")) or contains_any(text, [r"\binventory\b", r"\bstockpile\b", r"\beia\b.*\bcrud"])
    usd_macro_flag = boolize(overrides.get("usd_macro_flag")) or contains_any(text, [r"\bfed\b", r"\bcpi\b", r"\bpce\b", r"\bdollar\b", r"\busd\b", r"\brates?\b"])
    equity_risk_sentiment_flag = boolize(overrides.get("equity_risk_sentiment_flag")) or contains_any(text, [r"\brisk[- ]?off\b", r"\brisk[- ]?on\b", r"\bstocks?\b", r"\bequities\b", r"\brecession\b"])

    event_type = "other"
    market_interpretation_bucket = "cross_currents"
    expected_wti_bias = "neutral"
    expected_brent_bias = "neutral"
    confidence = 2

    if iran_hormuz_flag or shipping_disruption_flag:
        event_type = "shipping_geopolitics"
        market_interpretation_bucket = "supply_shock_bullish"
        expected_wti_bias = "positive"
        expected_brent_bias = "positive"
        confidence = 5
    elif attack_threat_flag or sanctions_flag:
        event_type = "attack_threat_sanctions"
        market_interpretation_bucket = "supply_shock_bullish"
        expected_wti_bias = "positive"
        expected_brent_bias = "positive"
        confidence = 4
    elif talks_negotiation_flag or ceasefire_flag:
        event_type = "talks_ceasefire"
        market_interpretation_bucket = "supply_relief_bearish"
        expected_wti_bias = "negative"
        expected_brent_bias = "negative"
        confidence = 4
    elif opec_supply_flag:
        event_type = "opec_supply"
        if contains_any(text, [r"\bincrease\b", r"\braise\b", r"\bhigher output\b", r"\boutput increase\b", r"\bmore barrels\b"]):
            market_interpretation_bucket = "supply_relief_bearish"
            expected_wti_bias = "negative"
            expected_brent_bias = "negative"
        else:
            market_interpretation_bucket = "supply_shock_bullish"
            expected_wti_bias = "positive"
            expected_brent_bias = "positive"
        confidence = 4
    elif inventory_flag:
        event_type = "inventory"
        if contains_any(text, [r"\bdraw\b", r"\bfall\b", r"\bdecline\b"]):
            market_interpretation_bucket = "inventory_draw_bullish"
            expected_wti_bias = "positive"
            expected_brent_bias = "positive"
        elif contains_any(text, [r"\bbuild\b", r"\brise\b", r"\bincrease\b"]):
            market_interpretation_bucket = "inventory_build_bearish"
            expected_wti_bias = "negative"
            expected_brent_bias = "negative"
        confidence = 4
    elif usd_macro_flag:
        event_type = "usd_macro"
        if contains_any(text, [r"\bstrong(er)? dollar\b", r"\bhawkish\b", r"\bhotter\b", r"\bhigher for longer\b"]):
            market_interpretation_bucket = "macro_dollar_bearish"
            expected_wti_bias = "negative"
            expected_brent_bias = "negative"
        elif contains_any(text, [r"\bweaker dollar\b", r"\bdovish\b", r"\bcooling\b", r"\brate cut\b"]):
            market_interpretation_bucket = "macro_dollar_bullish"
            expected_wti_bias = "positive"
            expected_brent_bias = "positive"
        confidence = 3
    elif equity_risk_sentiment_flag:
        event_type = "equity_risk_sentiment"
        if contains_any(text, [r"\brisk[- ]?off\b", r"\brecession\b", r"\bgrowth scare\b"]):
            market_interpretation_bucket = "macro_demand_bearish"
            expected_wti_bias = "negative"
            expected_brent_bias = "negative"
        elif contains_any(text, [r"\brisk[- ]?on\b", r"\bgrowth optimism\b"]):
            market_interpretation_bucket = "macro_demand_bullish"
            expected_wti_bias = "positive"
            expected_brent_bias = "positive"
        confidence = 3
    elif trump_statement_flag or trump_post_flag:
        event_type = "trump_rhetoric"
        market_interpretation_bucket = "headline_rhetoric"
        expected_wti_bias = "neutral"
        expected_brent_bias = "neutral"
        confidence = 2

    if overrides.get("event_type"):
        event_type = str(overrides["event_type"])
    if overrides.get("market_interpretation_bucket"):
        market_interpretation_bucket = str(overrides["market_interpretation_bucket"])
    if overrides.get("expected_wti_bias"):
        expected_wti_bias = str(overrides["expected_wti_bias"])
    if overrides.get("expected_brent_bias"):
        expected_brent_bias = str(overrides["expected_brent_bias"])
    if overrides.get("confidence_1_to_5"):
        try:
            confidence = int(float(overrides["confidence_1_to_5"]))
        except Exception:
            pass

    return {
        "event_type": event_type,
        "trump_statement_flag": trump_statement_flag,
        "trump_post_flag": trump_post_flag,
        "trump_direct_quote_short": overrides.get("trump_direct_quote_short", ""),
        "iran_hormuz_flag": iran_hormuz_flag,
        "shipping_disruption_flag": shipping_disruption_flag,
        "sanctions_flag": sanctions_flag,
        "talks_negotiation_flag": talks_negotiation_flag,
        "ceasefire_flag": ceasefire_flag,
        "attack_threat_flag": attack_threat_flag,
        "opec_supply_flag": opec_supply_flag,
        "inventory_flag": inventory_flag,
        "usd_macro_flag": usd_macro_flag,
        "equity_risk_sentiment_flag": equity_risk_sentiment_flag,
        "market_interpretation_bucket": market_interpretation_bucket,
        "expected_wti_bias": expected_wti_bias,
        "expected_brent_bias": expected_brent_bias,
        "confidence_1_to_5": clamp(confidence, 1, 5),
    }


# ============================================================
# LOAD PHASE-1 OUTPUTS
# ============================================================

def parse_rss_datetime(text: str) -> pd.Timestamp | NaTType:
    if not text:
        return pd.NaT
    try:
        dt = parsedate_to_datetime(text)
        ts = pd.Timestamp(dt)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert(TZ_NAME)
    except Exception:
        try:
            ts = pd.to_datetime(text, utc=True, errors="coerce")
            if pd.isna(ts):
                return pd.NaT
            return ts.tz_convert(TZ_NAME)
        except Exception:
            return pd.NaT


_HTTP_SESSION = None
_HOST_NEXT_ALLOWED_AT = defaultdict(float)
_HOST_LOCK = threading.Lock()

def get_http_session() -> requests.Session:
    global _HTTP_SESSION
    if _HTTP_SESSION is not None:
        return _HTTP_SESSION

    s = requests.Session()
    retry = Retry(
        total=0,
        connect=0,
        read=0,
        redirect=3,
        status=0,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "text/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    })
    _HTTP_SESSION = s
    return _HTTP_SESSION


def _sleep_for_host(host: str, base_delay: float = HIST_NEWS_PER_HOST_DELAY_SEC) -> None:
    now = time.time()
    with _HOST_LOCK:
        next_allowed = _HOST_NEXT_ALLOWED_AT.get(host, 0.0)
        wait = max(0.0, next_allowed - now)
    if wait > 0:
        time.sleep(wait)
    with _HOST_LOCK:
        _HOST_NEXT_ALLOWED_AT[host] = max(time.time(), _HOST_NEXT_ALLOWED_AT.get(host, 0.0)) + base_delay


def _penalize_host(host: str, status_code: int) -> None:
    penalty = 0.0
    if int(status_code or 0) == 403:
        penalty = HIST_NEWS_PER_HOST_BACKOFF_403_SEC
    elif int(status_code or 0) == 429:
        penalty = HIST_NEWS_PER_HOST_BACKOFF_429_SEC
    elif int(status_code or 0) in (500, 502, 503, 504):
        penalty = 4.0
    if penalty > 0:
        with _HOST_LOCK:
            _HOST_NEXT_ALLOWED_AT[host] = max(_HOST_NEXT_ALLOWED_AT.get(host, 0.0), time.time()) + penalty


def read_cache_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return normalize_cols(pd.read_csv(path))
    except Exception:
        return pd.DataFrame()


def write_cache_csv(df: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def fetch_url_payload(url: str, timeout: int = HIST_NEWS_REQUEST_TIMEOUT_SEC) -> Tuple[str, dict]:
    original_url = canonicalize_url(url)
    meta = {
        "original_url": original_url,
        "url": original_url,
        "ok": False,
        "status_code": np.nan,
        "content_type": "",
        "content_length": np.nan,
        "final_url": original_url,
        "redirected_flag": False,
        "elapsed_ms": np.nan,
        "blocked_flag": False,
        "block_signal": "",
        "error": "",
        "fetched_at_utc": pd.Timestamp.now("UTC").isoformat(),
    }
    if not original_url:
        meta["error"] = "blank_url"
        return "", meta

    host = (urlparse(original_url).netloc or "").lower()
    session = get_http_session()
    last_error = ""

    for attempt in range(1, HIST_NEWS_FETCH_RETRIES + 1):
        try:
            _sleep_for_host(host)
            t0 = time.time()
            resp = session.get(original_url, timeout=timeout, allow_redirects=True)
            meta["elapsed_ms"] = round((time.time() - t0) * 1000.0, 1)
            meta["status_code"] = resp.status_code
            meta["content_type"] = resp.headers.get("content-type", "")
            meta["content_length"] = len(resp.content or b"")
            meta["final_url"] = canonicalize_url(resp.url)
            meta["redirected_flag"] = canonicalize_url(resp.url) != original_url

            raw = resp.content or b""
            if original_url.lower().endswith(".gz") or meta["final_url"].lower().endswith(".gz"):
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass

            if int(resp.status_code) in (403, 429, 500, 502, 503, 504):
                _penalize_host(host, resp.status_code)
                if attempt < HIST_NEWS_FETCH_RETRIES:
                    time.sleep((2 ** (attempt - 1)) + random.uniform(0.4, 1.4))
                    continue

            resp.raise_for_status()
            text = raw.decode(resp.encoding or "utf-8", errors="ignore")

            blocked, signal = detect_block_or_interstitial(text, meta)
            meta["blocked_flag"] = bool(blocked)
            meta["block_signal"] = signal

            if blocked and signal != "non_html_or_unsupported" and attempt < HIST_NEWS_FETCH_RETRIES:
                _penalize_host(host, int(meta.get("status_code") or 0))
                time.sleep((2 ** (attempt - 1)) + random.uniform(0.5, 1.5))
                continue

            if blocked:
                meta["ok"] = False
                meta["error"] = signal or "blocked_or_unsupported"
                return "", meta
            
            meta["ok"] = True
            return text, meta

        except Exception as e:
            last_error = str(e)
            meta["error"] = last_error
            if int(meta.get("status_code") or 0) in (403, 429, 500, 502, 503, 504) and attempt < HIST_NEWS_FETCH_RETRIES:
                time.sleep((2 ** (attempt - 1)) + random.uniform(0.4, 1.4))
                continue
            break

    return "", meta
    

def fetch_url_text(url: str, timeout: int = HIST_NEWS_REQUEST_TIMEOUT_SEC) -> tuple[str, dict]:
    headers = {"User-Agent": "Mozilla/5.0"}
    meta = {"url": url, "ok": False, "status_code": None, "content_type": "", "error": ""}
    try:
        resp = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        meta["status_code"] = resp.status_code
        meta["content_type"] = resp.headers.get("content-type", "")
        resp.raise_for_status()
        meta["ok"] = True
        return resp.text, meta
    except Exception as e:
        meta["error"] = str(e)
        return "", meta


def fetch_live_news_candidates(trade_dates) -> pd.DataFrame:
    frames = []
    sourcespecs = [
        {"source_name": "Al Jazeera", "url_env": "ALJAZEERA_RSS_URL", "fallback_url": "https://www.aljazeera.com/xml/rss/all.xml"},
        {"source_name": "CNN", "url_env": "CNN_RSS_URL", "fallback_url": "http://rss.cnn.com/rss/edition.rss"},
        {"source_name": "CBS", "url_env": "CBS_RSS_URL", "fallback_url": "https://www.cbsnews.com/latest/rss/main"},
        {"source_name": "Reuters", "url_env": "REUTERS_AUTH_RSS_URL", "fallback_url": ""},
    ]

    print(f"[NEWS] fetch_live_news_candidates start trade_dates={len(trade_dates)}")

    for spec in sourcespecs:
        feedurl = os.getenv(spec["url_env"], "").strip() or spec["fallback_url"]
        if not feedurl:
            print(f"[NEWS] skip {spec['source_name']} no feed url")
            continue

        print(f"[NEWS] fetching {spec['source_name']} url={feedurl}")
        started = time.time()
        try:
            srcdf = fetch_feed_as_dataframe(feedurl, source_name=spec["source_name"])
        except Exception as e:
            print(f"[NEWS] fetch failed {spec['source_name']} err={e}")
            srcdf = pd.DataFrame()

        elapsed = round(time.time() - started, 2)
        print(f"[NEWS] fetched {spec['source_name']} rows={len(srcdf)} elapsed_sec={elapsed}")

        if srcdf.empty:
            continue

        if "source_name" not in srcdf.columns:
            srcdf["source_name"] = spec["source_name"]
        if "source_url" not in srcdf.columns:
            srcdf["source_url"] = ""

        dtcol = choose_col(srcdf, ["event_datetime_ist", "published_at_ist", "published_at", "timestamp", "datetime"])
        if dtcol:
            srcdf["event_datetime_ist"] = parse_dt_series(srcdf[dtcol])

        if "trade_date_ist" not in srcdf.columns:
            srcdf["trade_date_ist"] = pd.to_datetime(srcdf["event_datetime_ist"], errors="coerce").dt.date
        else:
            srcdf["trade_date_ist"] = parse_date_series(srcdf["trade_date_ist"])

        before = len(srcdf)
        srcdf = srcdf[srcdf["trade_date_ist"].isin(trade_dates)].copy()
        print(f"[NEWS] filtered {spec['source_name']} by trade_dates kept={len(srcdf)} dropped={before-len(srcdf)}")

        frames.append(srcdf)

    if not frames:
        print("[NEWS] fetch_live_news_candidates end no frames")
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True, sort=False)
    out["source_priority_score"] = out["source_name"].map(_source_rank)
    out = out.sort_values(["trade_date_ist", "source_priority_score", "event_datetime_ist"], ascending=[True, False, True]).reset_index(drop=True)
    print(f"[NEWS] fetch_live_news_candidates end total_rows={len(out)}")
    return out

def clean_headline_text(x: str) -> str:
    s = re.sub(r"\s+", " ", str(x or "")).strip()
    s = re.sub(r"\s*[-|]\s*(CNN|Al Jazeera|CBS News|Reuters)\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*::\s*.+$", "", s)
    return s.strip()


def find_meta_content(html: str, attr_name: str, attr_value: str) -> str:
    if not html:
        return ""
    pat = rf'(?is)<meta[^>]+{re.escape(attr_name)}=["\']{re.escape(attr_value)}["\'][^>]+content=["\'](.*?)["\']'
    m = re.search(pat, html)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    pat2 = rf'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+{re.escape(attr_name)}=["\']{re.escape(attr_value)}["\']'
    m2 = re.search(pat2, html)
    return re.sub(r"\s+", " ", m2.group(1)).strip() if m2 else ""


def find_link_href(html: str, rel_value: str) -> str:
    if not html:
        return ""
    pat = rf'(?is)<link[^>]+rel=["\']{re.escape(rel_value)}["\'][^>]+href=["\'](.*?)["\']'
    m = re.search(pat, html)
    if m:
        return m.group(1).strip()
    pat2 = rf'(?is)<link[^>]+href=["\'](.*?)["\'][^>]+rel=["\']{re.escape(rel_value)}["\']'
    m2 = re.search(pat2, html)
    return m2.group(1).strip() if m2 else ""


def strip_tags_basic(html: str) -> str:
    s = re.sub(r"(?is)<script\b.*?</script>", " ", str(html or ""))
    s = re.sub(r"(?is)<style\b.*?</style>", " ", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_json_ld_blobs(html: str) -> List[Any]:
    blobs = []
    for m in re.finditer(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', str(html or "")):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            blobs.append(json.loads(raw))
        except Exception:
            try:
                fixed = raw.replace("\n", " ").replace("\r", " ")
                blobs.append(json.loads(fixed))
            except Exception:
                continue
    return blobs


def deep_find_values(obj: Any, key: str) -> List[Any]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k) == key:
                out.append(v)
            out.extend(deep_find_values(v, key))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(deep_find_values(item, key))
    return out


def extract_title_from_html(html: str) -> Tuple[str, str]:
    vals = [
        (find_meta_content(html, "property", "og:title"), "og:title"),
        (find_meta_content(html, "name", "twitter:title"), "twitter:title"),
    ]
    for blob in extract_json_ld_blobs(html):
        for v in deep_find_values(blob, "headline"):
            vals.append((str(v).strip(), "jsonld:headline"))
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", str(html or ""))
    if m:
        vals.append((strip_tags_basic(m.group(1)), "title"))
    m2 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", str(html or ""))
    if m2:
        vals.append((strip_tags_basic(m2.group(1)), "h1"))

    for v, src in vals:
        cv = clean_headline_text(v)
        if cv and len(cv) >= 8:
            return cv, src
    return "", ""


def extract_description_from_html(html: str) -> Tuple[str, str]:
    vals = [
        (find_meta_content(html, "property", "og:description"), "og:description"),
        (find_meta_content(html, "name", "description"), "meta:description"),
    ]
    for blob in extract_json_ld_blobs(html):
        for v in deep_find_values(blob, "description"):
            vals.append((str(v).strip(), "jsonld:description"))

    article_match = re.search(r"(?is)<article\b.*?</article>", str(html or ""))
    if article_match:
        txt = strip_tags_basic(article_match.group(0))
        parts = [x.strip() for x in re.split(r"(?<=[.!?])\s+", txt) if x.strip()]
        if parts:
            vals.append((parts[0][:500], "article:first_paragraph"))

    for v, src in vals:
        cv = re.sub(r"\s+", " ", str(v or "")).strip()
        if cv and len(cv) >= 20:
            return cv, src
    return "", ""


def build_intraday_shock_windows(
    wti_intraday_ctx: dict,
    brent_intraday_ctx: dict,
) -> pd.DataFrame:
    rows = []

    for ctx in [wti_intraday_ctx, brent_intraday_ctx]:
        product = str(ctx.get("product", "")).lower()
        timeframe_used = str(ctx.get("timeframe_used", "")).strip()
        df = ctx.get("bars", pd.DataFrame())

        if df is None or df.empty:
            continue

        x = df.copy()
        x["trade_date_ist"] = parse_date_series(x["trade_date_ist"])
        x["timestamp_ist"] = parse_dt_series(x["timestamp_ist"])
        x["open_num"] = to_numeric_series(x["open_native"], index=x.index)
        x["close_num"] = to_numeric_series(x["close_native"], index=x.index)

        x["bar_ret_pct"] = np.where(
            x["open_num"].ne(0),
            (x["close_num"] - x["open_num"]) / x["open_num"] * 100.0,
            np.nan,
        )
        x["abs_bar_ret_pct"] = x["bar_ret_pct"].abs()
        x = x[x["abs_bar_ret_pct"].notna()].copy()
        if x.empty:
            continue

        x["shock_rank"] = x.groupby("trade_date_ist")["abs_bar_ret_pct"].rank(
            method="first", ascending=False
        )
        x = x[(x["shock_rank"] <= 3) & (x["abs_bar_ret_pct"] >= SHOCK_BAR_THRESHOLD_PCT)].copy()
        if x.empty:
            continue

        x["product"] = product
        x["intraday_timeframe_used"] = timeframe_used
        x["shock_precision_label"] = np.where(
            x["intraday_timeframe_used"].eq("60m"), "coarse", "normal"
        )

        rows.append(
            x[
                [
                    "trade_date_ist",
                    "timestamp_ist",
                    "product",
                    "intraday_timeframe_used",
                    "shock_precision_label",
                    "bar_ret_pct",
                    "abs_bar_ret_pct",
                    "shock_rank",
                ]
            ]
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "trade_date_ist",
                "timestamp_ist",
                "product",
                "intraday_timeframe_used",
                "shock_precision_label",
                "bar_ret_pct",
                "abs_bar_ret_pct",
                "shock_rank",
            ]
        )

    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values(
        ["trade_date_ist", "timestamp_ist", "product"]
    ).reset_index(drop=True)
    return out


def shock_proximity_stats(shock_windows: pd.DataFrame, trade_date, event_dt_ist: Optional[pd.Timestamp]) -> Tuple[float, int, bool]:
    if shock_windows.empty or pd.isna(event_dt_ist):
        return np.nan, 0, False

    day = shock_windows[shock_windows["trade_date_ist"].eq(trade_date)].copy()
    if day.empty:
        return np.nan, 0, False

    mins = (day["timestamp_ist"] - event_dt_ist).abs().dt.total_seconds() / 60.0
    nearest = float(mins.min()) if len(mins) else np.nan

    if pd.isna(nearest):
        score = 0
    elif nearest <= 30:
        score = 4
    elif nearest <= 60:
        score = 3
    elif nearest <= EVENT_SHOCK_WINDOW_MIN:
        score = 2
    elif nearest <= 240:
        score = 1
    else:
        score = 0

    return nearest, score, score >= 2

def load_phase1():
    daily_master = read_output_table("daily_master_summary.xlsx", required=True)
    day_labels = read_output_table("day_type_labels.xlsx", required=True)
    deviations = read_output_table("deviation_pattern_labels.xlsx", required=True)
    day_window_matrix = read_output_table("day_window_behavior_matrix.xlsx", required=True)
    arche = read_output_table("archetype_similarity_features.xlsx", required=True)
    wti_5m = read_output_table("wti_5m_ist.xlsx", required=True)
    brent_5m = read_output_table("brent_5m_ist.xlsx", required=True)
    wti_15m = read_output_table("wti_15m_ist.xlsx", required=True)
    brent_15m = read_output_table("brent_15m_ist.xlsx", required=True)
    wti_60m = read_output_table("wti_60m_ist.xlsx", required=True)
    brent_60m = read_output_table("brent_60m_ist.xlsx", required=True)

    for df in [daily_master, day_labels, deviations, day_window_matrix, arche, wti_5m, brent_5m, wti_15m, brent_15m]:
        if not df.empty:
            td = choose_col(df, ["trade_date_ist"])
            if td:
                df["trade_date_ist"] = parse_date_series(df[td])

    for df in [wti_5m, brent_5m, wti_15m, brent_15m, wti_60m, brent_60m]:
        if not df.empty:
            ts = choose_col(df, ["timestamp_ist"])
            if ts:
                df["timestamp_ist"] = parse_dt_series(df[ts])

    return {
        "daily_master": daily_master,
        "day_labels": day_labels,
        "deviations": deviations,
        "day_window_matrix": day_window_matrix,
        "arche": arche,
        "wti_5m": wti_5m,
        "brent_5m": brent_5m,
        "wti_15m": wti_15m,
        "brent_15m": brent_15m,
        "wti_60m": wti_60m,
        "brent_60m": brent_60m,
    }

# ============================================================
# BUILD NEWS MASTER
# ============================================================

def read_output_table(filename: str, required: bool = False) -> pd.DataFrame:
    path = OUTPUT_DIR / filename
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required file not found: {path}")
        return pd.DataFrame()

    if path.suffix.lower() == ".xlsx":
        return normalize_cols(pd.read_excel(path))
    if path.suffix.lower() == ".csv":
        return normalize_cols(pd.read_csv(path))

    raise ValueError(f"Unsupported file type: {path.suffix}")


def write_output_table(df: pd.DataFrame, filename: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename

    out = df.copy()

    if path.suffix.lower() == ".xlsx":
        for col in out.columns:
            s = out[col]
            if getattr(s.dtype, "tz", None) is not None:
                out[col] = s.dt.tz_localize(None)

        out.to_excel(path, index=False)
        return

    if path.suffix.lower() == ".csv":
        out.to_csv(path, index=False)
        return

    raise ValueError(f"Unsupported file type: {path.suffix}")


def standardize_raw_news_candidates(df: pd.DataFrame, trade_dates: List) -> pd.DataFrame:
    required_cols = [
        "trade_date_ist",
        "event_datetime_original",
        "event_datetime_ist",
        "source_name",
        "source_url",
        "headline",
        "summary_1_sentence",
        "body_text",
        "keyword_relevance_score",
        "discovery_method",
        "coverage_verified_flag",
    ]
    OPTIONAL_NEWS_EXTRA_COLS = [
    "inventory_release_flag",
    "inventory_release_type",
    "inventory_release_source",
    "inventory_actual_change_mmbbl",
    "inventory_expected_change_mmbbl",
    "inventory_surprise_mmbbl",
    "inventory_surprise_abs_mmbbl",
    "inventory_surprise_bias",
    "inventory_consensus_available_flag",
    "inventory_other_news_overlap_count",
    "inventory_other_news_overlap_flag",
    "inventory_clean_signal_flag",
    "inventory_market_agreed_flag",
    "inventory_market_deviation_flag",
    "inventory_no_clear_price_response_flag",
    "inventory_impact_strength_1_to_5",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=required_cols)

    out = normalize_cols(df.copy())

    for c in required_cols:
        if c not in out.columns:
            out[c] = "" if c not in {"coverage_verified_flag", "keyword_relevance_score"} else (False if c == "coverage_verified_flag" else 0)

    out["event_datetime_ist"] = parse_dt_series(out["event_datetime_ist"])
    out["trade_date_ist"] = parse_date_series(out["trade_date_ist"])
    if out["trade_date_ist"].isna().any():
        mask = out["trade_date_ist"].isna() & pd.Series(out["event_datetime_ist"]).notna()
        out.loc[mask, "trade_date_ist"] = pd.Series(out.loc[mask, "event_datetime_ist"]).dt.date

    out["source_url"] = out["source_url"].astype(str).map(canonicalize_url)
    out["headline"] = out["headline"].astype(str).map(clean_headline_text)
    out["summary_1_sentence"] = out["summary_1_sentence"].fillna("").astype(str)
    out["body_text"] = out["body_text"].fillna("").astype(str)
    out["keyword_relevance_score"] = pd.to_numeric(out["keyword_relevance_score"], errors="coerce").fillna(0).astype(int)
    out["coverage_verified_flag"] = out["coverage_verified_flag"].map(boolize).fillna(False)

    out = out[out["headline"].str.strip().str.len() > 0].copy()
    out = out[out["trade_date_ist"].isin(set(trade_dates))].copy()

    out = out.sort_values(
        ["trade_date_ist", "keyword_relevance_score", "event_datetime_ist", "source_name", "source_url"],
        ascending=[True, False, True, True, True]
    ).copy()

    out = out.drop_duplicates(subset=["source_name", "source_url"])
    out = out.drop_duplicates(subset=["trade_date_ist", "headline"])

    out["rank_for_day"] = out.groupby(["trade_date_ist", "source_name"]).cumcount() + 1
    out = out[out["rank_for_day"] <= HIST_NEWS_MAX_ARTICLES_PER_DAY].copy()
    out = out.drop(columns=["rank_for_day"], errors="ignore")

    for c in OPTIONAL_NEWS_EXTRA_COLS:
        if c not in out.columns:
            out[c] = False if c.endswith("_flag") else np.nan
        
    keep_cols = required_cols + [c for c in OPTIONAL_NEWS_EXTRA_COLS if c in out.columns]
    extra_passthrough = [c for c in out.columns if c not in keep_cols]
    return out[keep_cols + extra_passthrough].reset_index(drop=True)


def load_raw_news(trade_dates: List) -> pd.DataFrame:
    HIST_NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if RAW_NEWS_INPUT_CSV and Path(RAW_NEWS_INPUT_CSV).exists():
        raw = normalize_cols(pd.read_csv(RAW_NEWS_INPUT_CSV))
        raw = standardize_raw_news_candidates(raw, trade_dates)
        write_output_table(raw, HIST_NEWS_RAW_CSV.name)
        write_output_table(raw, HIST_NEWS_RAW_XLSX.name)
        return raw

    # Honour REBUILD_RAW_NEWS_EACH_RUN=0: reuse existing raw CSV if non-empty
    if not REBUILD_RAW_NEWS_EACH_RUN and HIST_NEWS_RAW_CSV.exists():
        print(f"[NEWS] REBUILD_RAW_NEWS_EACH_RUN=0 — loading cached raw news from {HIST_NEWS_RAW_CSV}")
        _cached_raw = normalize_cols(pd.read_csv(HIST_NEWS_RAW_CSV))
        _cached_raw = standardize_raw_news_candidates(_cached_raw, trade_dates)
        if not _cached_raw.empty:
            print(f"[NEWS] cache hit: {len(_cached_raw)} rows")
            return _cached_raw
        print("[NEWS] cached CSV was empty after standardization — rebuilding")

    bundle = build_historical_news_bundle(trade_dates)

    if not bundle["discovered_urls"].empty:
        write_output_table(bundle["discovered_urls"], "news_discovered_urls.csv")
    if not bundle["discovery_diag"].empty:
        write_output_table(bundle["discovery_diag"], HIST_NEWS_DISCOVERY_DIAG.name)
    if not bundle["article_diag"].empty:
        write_output_table(bundle["article_diag"], HIST_NEWS_ARTICLE_DIAG.name)

    raw = bundle["raw_news"].copy()

    # GDELT: primary fix for historical coverage gaps that sitemaps cannot fill
    try:
        gdelt_rows = fetch_gdelt_news_for_daterange(min(trade_dates), max(trade_dates))
        if not gdelt_rows.empty:
            print(f"[GDELT] injecting {len(gdelt_rows)} rows into raw_news")
            raw = pd.concat([raw, gdelt_rows], ignore_index=True, sort=False)
    except Exception as _gdelt_err:
        print(f"[GDELT] skipped: {_gdelt_err}")

    inv_rows = build_eia_inventory_event_rows(trade_dates)
    if not inv_rows.empty:
        raw = pd.concat([raw, inv_rows], ignore_index=True, sort=False)

    raw = standardize_raw_news_candidates(raw, trade_dates)

    write_output_table(raw, HIST_NEWS_RAW_CSV.name)
    write_output_table(raw, HIST_NEWS_RAW_XLSX.name)

    print(f"[NEWS] built internal raw news rows={len(raw)} path={HIST_NEWS_RAW_CSV}")
    return raw


def build_no_event_row(d) -> dict:
    event_dt = pd.Timestamp(str(d)).tz_localize(TZ_NAME) + pd.Timedelta(hours=12)
    return {
        "event_id": f"NOEVENT_{pd.Timestamp(d).strftime('%Y%m%d')}_01",
        "trade_date_ist": d,
        "event_datetime_original": "",
        "event_datetime_ist": event_dt,
        "source_name": "synthetic_absence_marker",
        "source_url": "",
        "headline": "No major verified crude catalyst identified",
        "summary_1_sentence": "No major verified crude-relevant headline cleared the relevance threshold for this trade date.",
        "event_type": "no_major_catalyst",
        "trump_statement_flag": False,
        "trump_post_flag": False,
        "trump_direct_quote_short": "",
        "iran_hormuz_flag": False,
        "shipping_disruption_flag": False,
        "sanctions_flag": False,
        "talks_negotiation_flag": False,
        "ceasefire_flag": False,
        "attack_threat_flag": False,
        "opec_supply_flag": False,
        "inventory_flag": False,
        "usd_macro_flag": False,
        "equity_risk_sentiment_flag": False,
        "market_interpretation_bucket": "no_major_catalyst",
        "expected_wti_bias": "neutral",
        "expected_brent_bias": "neutral",
        "confidence_1_to_5": 1,
        "headline_rank_for_day": 1,
        "raw_relevance_score": 0,
        "no_major_headline_flag": True,
        "keyword_relevance_score": 0,
        "shock_proximity_minutes": np.nan,
        "shock_proximity_score": 0,
        "is_shock_timed_candidate": False,
        "news_row_quality": "synthetic_absence_marker",
        "coverage_verified_flag": False,
    }


def build_news_master(trade_dates, raw_news: pd.DataFrame, shock_windows: pd.DataFrame) -> pd.DataFrame:
    if raw_news is None:
        raw_news = pd.DataFrame()

    news = dedupe_and_cluster_news_candidates(raw_news)

    if news.empty:
        rows = [build_no_event_row(d) for d in trade_dates]
        out = pd.DataFrame(rows)
        out["trade_date_ist"] = out["trade_date_ist"].astype(str)
        return out

    news["trade_date_ist"] = parse_date_series(news["trade_date_ist"])
    news["event_datetime_ist"] = parse_dt_series(news["event_datetime_ist"])

    if "headline" not in news.columns:
        news["headline"] = ""
    if "source_name" not in news.columns:
        news["source_name"] = ""
    if "source_url" not in news.columns:
        news["source_url"] = ""
    if "summary_1_sentence" not in news.columns:
        news["summary_1_sentence"] = ""
    if "body_text" not in news.columns:
        news["body_text"] = ""

    rows = []
    for _, r in news.iterrows():
        headline = str(r.get("headline", "") or "")
        source_name = str(r.get("source_name", "") or "")
        source_url = str(r.get("source_url", "") or "")
        trade_date = r.get("trade_date_ist")
        event_dt = r.get("event_datetime_ist")

        _summary = str(r.get("summary_1_sentence", "") or "")
        _body = str(r.get("body_text", "") or "")

        flags = classify_headline_flags(headline, _summary)

        preset_event_type = str(r.get("event_type", "") or "").strip()
        preset_interp = str(r.get("market_interpretation_bucket", "") or "").strip()
        preset_wti_bias = str(r.get("expected_wti_bias", "") or "").strip()
        preset_brent_bias = str(r.get("expected_brent_bias", "") or "").strip()

        event_type = preset_event_type or infer_event_type(headline, flags)
        wti_bias = preset_wti_bias or infer_expected_bias(flags, product="WTI")
        brent_bias = preset_brent_bias or infer_expected_bias(flags, product="BRENT")
        interpretation = preset_interp or infer_market_interpretation_bucket(flags)

        try:
            keyword_score_val = compute_keyword_relevance_score(flags, headline, _summary, _body)
        except TypeError:
            keyword_score_val = compute_keyword_relevance_score(flags, headline)

        src_rank = _source_rank(source_name)
        conf = 1.0
        conf += src_rank * 2.0
        conf += 1.0 if source_url else 0.0
        conf += 1.0 if pd.notna(event_dt) else 0.0
        conf += min(float(keyword_score_val) / 4.0, 1.0)
        conf = round(float(min(conf, 5.0)), 2)

        event_session = assign_session_window(event_dt) if pd.notna(event_dt) else ""
        _prox_mins, _prox_raw, _is_shock_timed = shock_proximity_stats(
            shock_windows, trade_date, event_dt
        )
        shock_score = float(_prox_raw) if pd.notna(_prox_raw) else 0.0

        if float(keyword_score_val) < MIN_EVENT_RELEVANCE_SCORE:
            continue

        _cov_verified = boolize(r.get("coverage_verified_flag", False))

        rows.append({
            "event_id": stable_event_id(trade_date, headline, source_name),
            "trade_date_ist": trade_date,
            "event_datetime_ist": event_dt,
            "headline": headline,
            "summary_1_sentence": _summary,
            "source_name": source_name,
            "source_url": source_url,
            "event_type": event_type,
            "event_session_window_ist": event_session,
            "market_interpretation_bucket": interpretation,
            "expected_wti_bias": wti_bias,
            "expected_brent_bias": brent_bias,
            "keyword_relevance_score": round(float(keyword_score_val), 2),
            "raw_relevance_score": round(float(keyword_score_val), 2),
            "shock_proximity_score": round(float(shock_score), 2),
            "shock_proximity_minutes": float(_prox_mins) if pd.notna(_prox_mins) else np.nan,
            "is_shock_timed_candidate": bool(_is_shock_timed),
            "confidence_1_to_5": conf,
            "source_priority_score": round(float(src_rank * 5.0), 2),
            "coverage_verified_flag": _cov_verified,
            "no_major_headline_flag": False,
            "news_row_quality": "real_article_with_url" if _cov_verified else "real_article_no_url",

            # preserve structured inventory fields
            "inventory_release_flag": boolize(r.get("inventory_release_flag", False)),
            "inventory_release_type": str(r.get("inventory_release_type", "") or ""),
            "inventory_release_source": str(r.get("inventory_release_source", "") or ""),
            "inventory_actual_change_mmbbl": to_float_scalar(r.get("inventory_actual_change_mmbbl")),
            "inventory_expected_change_mmbbl": to_float_scalar(r.get("inventory_expected_change_mmbbl")),
            "inventory_surprise_mmbbl": to_float_scalar(r.get("inventory_surprise_mmbbl")),
            "inventory_surprise_abs_mmbbl": to_float_scalar(r.get("inventory_surprise_abs_mmbbl")),
            "inventory_surprise_bias": str(r.get("inventory_surprise_bias", "") or ""),
            "inventory_consensus_available_flag": boolize(r.get("inventory_consensus_available_flag", False)),

            **flags,
        })

    out = pd.DataFrame(rows)

    if not out.empty:
        _sort_for_rank = out.sort_values(
            ["trade_date_ist", "confidence_1_to_5", "keyword_relevance_score"],
            ascending=[True, False, False],
        ).copy()
        _sort_for_rank["headline_rank_for_day"] = (
            _sort_for_rank.groupby("trade_date_ist").cumcount() + 1
        )
        out.loc[_sort_for_rank.index, "headline_rank_for_day"] = _sort_for_rank["headline_rank_for_day"].values

    if out.empty:
        rows = [build_no_event_row(d) for d in trade_dates]
        out = pd.DataFrame(rows)
        out["trade_date_ist"] = out["trade_date_ist"].astype(str)
        return out

    covered_days = set(parse_date_series(out["trade_date_ist"]).dropna().tolist())
    missing_days = [d for d in trade_dates if d not in covered_days]

    if missing_days:
        out = pd.concat(
            [out, pd.DataFrame([build_no_event_row(d) for d in missing_days])],
            ignore_index=True,
            sort=False,
        )

    out["trade_date_ist"] = parse_date_series(out["trade_date_ist"])
    out["event_datetime_ist"] = parse_dt_series(out["event_datetime_ist"])

    out = out.sort_values(
        ["trade_date_ist", "confidence_1_to_5", "keyword_relevance_score", "event_datetime_ist"],
        ascending=[True, False, False, True]
    ).reset_index(drop=True)

    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


# ============================================================
# REACTION LINKING
# ============================================================

def product_reaction_after_event(
    intraday_ctx: dict,
    trade_date,
    event_dt_ist: (pd.Timestamp),
) -> dict:
    timeframe_used = str(intraday_ctx.get("timeframe_used", "")).strip()
    intraday = intraday_ctx.get("bars", pd.DataFrame())

    blank = {
        "event_session_window_ist": "",
        "first_reaction_window_ist": "",
        "ret_1h_pct": np.nan,
        "ret_4h_pct": np.nan,
        "mfe_4h_pct": np.nan,
        "mae_4h_pct": np.nan,
        "reaction_strength_score_1_to_5": np.nan,
        "reaction_side": "",
        "intraday_timeframe_used": timeframe_used,
        "reaction_precision_label": "coarse" if timeframe_used == "60m" else "normal",
    }
    if intraday.empty:
        return blank

    day = intraday[intraday["trade_date_ist"].eq(trade_date)].copy()
    if day.empty:
        return blank

    day = day.sort_values("timestamp_ist").copy()
    if pd.isna(event_dt_ist):
        event_dt_ist = day["timestamp_ist"].iloc[0]

    after = day[day["timestamp_ist"] >= event_dt_ist].copy()
    if after.empty:
        after = day.copy()

    entry_bar = after.iloc[0]
    entry_ts = entry_bar["timestamp_ist"]
    entry_px = to_float_scalar(entry_bar.get("open_native"))

    h1 = after[after["timestamp_ist"] <= entry_ts + pd.Timedelta(hours=1)].copy()
    h4 = after[after["timestamp_ist"] <= entry_ts + pd.Timedelta(hours=4)].copy()
    if h1.empty:
        h1 = after.iloc[[0]].copy()
    if h4.empty:
        h4 = after.iloc[[0]].copy()

    last_1h = to_float_scalar(h1["close_native"].iloc[-1])
    last_4h = to_float_scalar(h4["close_native"].iloc[-1])
    hi_4h = float(to_numeric_series(h4["high_native"], index=h4.index).max()) if not h4.empty else np.nan
    lo_4h = float(to_numeric_series(h4["low_native"], index=h4.index).min()) if not h4.empty else np.nan

    ret_1h = pct_change(last_1h, entry_px)
    ret_4h = pct_change(last_4h, entry_px)
    mfe_4h = pct_change(hi_4h, entry_px)
    mae_4h = pct_change(lo_4h, entry_px)

    abs4 = abs(ret_4h) if pd.notna(ret_4h) else np.nan
    if pd.isna(abs4):
        strength = np.nan
        side = ""
    else:
        if abs4 >= 3.0:
            strength = 5
        elif abs4 >= 2.0:
            strength = 4
        elif abs4 >= 1.0:
            strength = 3
        elif abs4 >= 0.4:
            strength = 2
        else:
            strength = 1
        side = "up" if ret_4h > 0 else "down" if ret_4h < 0 else "flat"

    return {
        "event_session_window_ist": assign_session_window(event_dt_ist),
        "first_reaction_window_ist": resolve_session_window_from_row(entry_bar),
        "ret_1h_pct": ret_1h,
        "ret_4h_pct": ret_4h,
        "mfe_4h_pct": mfe_4h,
        "mae_4h_pct": mae_4h,
        "reaction_strength_score_1_to_5": strength,
        "reaction_side": side,
        "intraday_timeframe_used": timeframe_used,
        "reaction_precision_label": "coarse" if timeframe_used == "60m" else "normal",
    }


def bias_match(expected_bias: str, ret_4h_pct):
    if pd.isna(ret_4h_pct):
        return np.nan
    b = sign_bias_to_score(expected_bias)
    if b == 0:
        return abs(ret_4h_pct) <= 0.5
    return (b > 0 and ret_4h_pct > 0) or (b < 0 and ret_4h_pct < 0)


def build_news_reaction_matrix(
    news_master: pd.DataFrame,
    wti_intraday_ctx: dict,
    brent_intraday_ctx: dict,
) -> pd.DataFrame:
    nm = news_master.copy()
    nm["trade_date_ist"] = parse_date_series(nm["trade_date_ist"])
    nm["event_datetime_ist"] = parse_dt_series(nm["event_datetime_ist"])

    rows = []
    for _, r in nm.iterrows():
        wti = product_reaction_after_event(
            wti_intraday_ctx, r["trade_date_ist"], r["event_datetime_ist"]
        )
        brent = product_reaction_after_event(
            brent_intraday_ctx, r["trade_date_ist"], r["event_datetime_ist"]
        )

        rows.append({
            "event_id": r["event_id"],
            "trade_date_ist": r["trade_date_ist"],
            "headline_rank_for_day": r["headline_rank_for_day"],
            "headline": r["headline"],
            "event_type": r["event_type"],
            "market_interpretation_bucket": r["market_interpretation_bucket"],
            "expected_wti_bias": r["expected_wti_bias"],
            "expected_brent_bias": r["expected_brent_bias"],
            "no_major_headline_flag": r["no_major_headline_flag"],
            "event_session_window_ist": wti["event_session_window_ist"] or brent["event_session_window_ist"],

            "wti_intraday_timeframe_used": wti["intraday_timeframe_used"],
            "wti_reaction_precision_label": wti["reaction_precision_label"],
            "wti_first_reaction_window_ist": wti["first_reaction_window_ist"],
            "wti_ret_1h_pct": wti["ret_1h_pct"],
            "wti_ret_4h_pct": wti["ret_4h_pct"],
            "wti_mfe_4h_pct": wti["mfe_4h_pct"],
            "wti_mae_4h_pct": wti["mae_4h_pct"],
            "wti_reaction_strength_score_1_to_5": wti["reaction_strength_score_1_to_5"],
            "wti_reaction_side": wti["reaction_side"],
            "wti_reaction_matched_expected_flag": bias_match(r["expected_wti_bias"], wti["ret_4h_pct"]),
            "brent_intraday_timeframe_used": brent["intraday_timeframe_used"],
            "brent_reaction_precision_label": brent["reaction_precision_label"],
            "brent_first_reaction_window_ist": brent["first_reaction_window_ist"],
            "brent_ret_1h_pct": brent["ret_1h_pct"],
            "brent_ret_4h_pct": brent["ret_4h_pct"],
            "brent_mfe_4h_pct": brent["mfe_4h_pct"],
            "brent_mae_4h_pct": brent["mae_4h_pct"],
            "brent_reaction_strength_score_1_to_5": brent["reaction_strength_score_1_to_5"],
            "brent_reaction_side": brent["reaction_side"],
            "brent_reaction_matched_expected_flag": bias_match(r["expected_brent_bias"], brent["ret_4h_pct"]),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


# ============================================================
# DAY ROLLUP + NEWS FLAG / BEHAVIOR LINKS
# ============================================================

def build_news_day_rollup(news_master: pd.DataFrame, reaction_matrix: pd.DataFrame, trade_dates) -> pd.DataFrame:
    if news_master.empty:
        return pd.DataFrame()

    nm = news_master.copy()
    nm["trade_date_ist"] = parse_date_series(nm["trade_date_ist"])

    rm = reaction_matrix.copy()
    if not rm.empty and "trade_date_ist" in rm.columns:
        rm["trade_date_ist"] = parse_date_series(rm["trade_date_ist"])

    rows = []
    for d in trade_dates:
        g = nm[nm["trade_date_ist"].eq(d)].copy()
        rg = rm[rm["trade_date_ist"].eq(d)].copy() if not rm.empty else pd.DataFrame()

        if g.empty:
            rows.append({
                "trade_date_ist": d,
                "event_count": 0,
                "major_headline_count": 0,
                "verified_event_count": 0,
                "causal_event_count": 0,
                "no_major_headline_flag": True,
                "news_coverage_status": "no_major_catalyst",
                "news_quality_gate_passed_for_day": False,
                "dominant_event_id": "",
                "dominant_event_type": "no_major_catalyst",
                "dominant_market_interpretation_bucket": "no_major_catalyst",
                "dominant_expected_wti_bias": "neutral",
                "dominant_expected_brent_bias": "neutral",
                "dominant_event_session_window_ist": "",
                "dominant_headline": "",
                "dominant_source_url": "",
                "composite_expected_wti_bias": "neutral",
                "composite_expected_brent_bias": "neutral",
                "max_keyword_relevance_score": 0.0,
                "max_confidence_1_to_5": 0.0,
                "avg_wti_ret_4h_pct": np.nan,
                "avg_brent_ret_4h_pct": np.nan,
            })
            continue

        real = g[~g["event_type"].fillna("").eq("no_major_catalyst")].copy()
        base = real if not real.empty else g

        dominant = (
            base.sort_values(
                ["confidence_1_to_5", "keyword_relevance_score", "event_datetime_ist"],
                ascending=[False, False, True]
            )
            .iloc[0]
        )

        wti_bias_num = base["expected_wti_bias"].map(sign_bias_to_score).fillna(0)
        brent_bias_num = base["expected_brent_bias"].map(sign_bias_to_score).fillna(0)
        wt = pd.to_numeric(base["confidence_1_to_5"], errors="coerce").fillna(1.0)

        comp_wti = np.average(wti_bias_num, weights=np.maximum(wt, 0.1)) if len(base) else 0.0
        comp_brent = np.average(brent_bias_num, weights=np.maximum(wt, 0.1)) if len(base) else 0.0

        verified_event_count = int(base["source_url"].fillna("").astype(str).str.len().gt(0).sum())
        major_headline_count = int(len(base))
        no_major_headline_flag = bool(real.empty)

        if not real.empty:
            causal_mask = (
                pd.to_numeric(real["confidence_1_to_5"], errors="coerce").fillna(0).ge(3)
                & real["source_url"].fillna("").astype(str).str.len().gt(0)
                & real["event_datetime_ist"].notna()
            )
            causal_event_count = int(causal_mask.sum())
        else:
            causal_event_count = 0

        if no_major_headline_flag:
            news_coverage_status = "no_major_catalyst"
        elif causal_event_count > 0:
            news_coverage_status = "confirmed_causal"
        elif verified_event_count > 0:
            news_coverage_status = "verified_but_not_causal"
        else:
            news_coverage_status = "unverified_coverage"

        news_quality_gate_passed_for_day = bool(
            news_coverage_status in ["confirmed_causal", "verified_but_not_causal"]
        )

        rows.append({
            "trade_date_ist": d,
            "event_count": int(len(base)),
            "major_headline_count": major_headline_count,
            "verified_event_count": verified_event_count,
            "causal_event_count": causal_event_count,
            "no_major_headline_flag": no_major_headline_flag,
            "news_coverage_status": news_coverage_status,
            "news_quality_gate_passed_for_day": news_quality_gate_passed_for_day,
            "dominant_event_id": str(dominant.get("event_id", "")),
            "dominant_event_type": str(dominant.get("event_type", "")),
            "dominant_market_interpretation_bucket": str(dominant.get("market_interpretation_bucket", "")),
            "dominant_expected_wti_bias": str(dominant.get("expected_wti_bias", "neutral")),
            "dominant_expected_brent_bias": str(dominant.get("expected_brent_bias", "neutral")),
            "dominant_event_session_window_ist": str(dominant.get("event_session_window_ist", "")),
            "dominant_headline": str(dominant.get("headline", "")),
            "dominant_source_url": str(dominant.get("source_url", "")),
            "composite_expected_wti_bias": _sign_label(comp_wti),
            "composite_expected_brent_bias": _sign_label(comp_brent),
            "max_keyword_relevance_score": round(float(pd.to_numeric(base["keyword_relevance_score"], errors="coerce").max()), 2),
            "max_confidence_1_to_5": round(float(pd.to_numeric(base["confidence_1_to_5"], errors="coerce").max()), 2),
            "avg_wti_ret_4h_pct": pd.to_numeric(
                rg.get("wti_ret_4h_pct", pd.Series(dtype="float64")), errors="coerce"
            ).mean(),
            "avg_brent_ret_4h_pct": pd.to_numeric(
                rg.get("brent_ret_4h_pct", pd.Series(dtype="float64")), errors="coerce"
            ).mean(),
        })

    out = pd.DataFrame(rows).sort_values("trade_date_ist").reset_index(drop=True)
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


# def build_news_day_rollup(news_master: pd.DataFrame, reaction_matrix: pd.DataFrame, trade_dates) -> pd.DataFrame:
#     if news_master.empty:
#         return pd.DataFrame()

#     nm = news_master.copy()
#     nm["trade_date_ist"] = parse_date_series(nm["trade_date_ist"])

#     rm = reaction_matrix.copy()
#     if not rm.empty and "trade_date_ist" in rm.columns:
#         rm["trade_date_ist"] = parse_date_series(rm["trade_date_ist"])

#     rows = []
#     for d in trade_dates:
#         g = nm[nm["trade_date_ist"].eq(d)].copy()
#         rg = rm[rm["trade_date_ist"].eq(d)].copy() if not rm.empty else pd.DataFrame()

#         if g.empty:
#             rows.append({
#                 "trade_date_ist": d,
#                 "event_count": 0,
#                 "verified_event_count": 0,
#                 "dominant_event_type": "no_major_catalyst",
#                 "dominant_event_session_window_ist": "",
#                 "dominant_headline": "",
#                 "dominant_source_url": "",
#                 "composite_expected_wti_bias": "neutral",
#                 "composite_expected_brent_bias": "neutral",
#                 "max_keyword_relevance_score": 0.0,
#                 "max_confidence_1_to_5": 0.0,
#                 "avg_wti_ret_4h_pct": np.nan,
#                 "avg_brent_ret_4h_pct": np.nan,
#             })
#             continue

#         real = g[~g["event_type"].fillna("").eq("synthetic_absence_marker")].copy()
#         base = real if not real.empty else g

#         dominant = base.sort_values(
#             ["confidence_1_to_5", "keyword_relevance_score", "event_datetime_ist"],
#             ascending=[False, False, True]
#         ).iloc[0]

#         wti_bias_num = base["expected_wti_bias"].map(sign_bias_to_score).fillna(0)
#         brent_bias_num = base["expected_brent_bias"].map(sign_bias_to_score).fillna(0)
#         wt = pd.to_numeric(base["confidence_1_to_5"], errors="coerce").fillna(1)

#         comp_wti = np.average(wti_bias_num, weights=np.maximum(wt, 0.1)) if len(base) else 0.0
#         comp_brent = np.average(brent_bias_num, weights=np.maximum(wt, 0.1)) if len(base) else 0.0

#         rows.append({
#             "trade_date_ist": d,
#             "event_count": int(len(base)),
#             "verified_event_count": int(base["source_url"].fillna("").astype(str).str.len().gt(0).sum()),
#             "dominant_event_type": str(dominant.get("event_type", "")),
#             "dominant_event_session_window_ist": str(dominant.get("event_session_window_ist", "")),
#             "dominant_headline": str(dominant.get("headline", "")),
#             "dominant_source_url": str(dominant.get("source_url", "")),
#             "composite_expected_wti_bias": _sign_label(comp_wti),
#             "composite_expected_brent_bias": _sign_label(comp_brent),
#             "max_keyword_relevance_score": round(float(pd.to_numeric(base["keyword_relevance_score"], errors="coerce").max()), 2),
#             "max_confidence_1_to_5": round(float(pd.to_numeric(base["confidence_1_to_5"], errors="coerce").max()), 2),
#             "avg_wti_ret_4h_pct": pd.to_numeric(rg.get("wti_ret_4h_pct", pd.Series(dtype="float64")), errors="coerce").mean(),
#             "avg_brent_ret_4h_pct": pd.to_numeric(rg.get("brent_ret_4h_pct", pd.Series(dtype="float64")), errors="coerce").mean(),
#         })

#     out = pd.DataFrame(rows).sort_values("trade_date_ist").reset_index(drop=True)
#     out["trade_date_ist"] = out["trade_date_ist"].astype(str)
#     return out

def build_analysis_intraday_context(
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_60m: pd.DataFrame,
    product: str = "",
) -> dict:
    ctx = resolve_intraday_source(df_5m, df_15m, df_60m, product=product)
    bars = ctx["bars"].copy()

    if bars.empty:
        ctx["analysis_mode"] = "empty"
        return ctx

    if "session_window_ist" not in bars.columns:
        bars["session_window_ist"] = bars["timestamp_ist"].apply(assign_session_window)
    else:
        bars["session_window_ist"] = bars.apply(resolve_session_window_from_row, axis=1)

    bars = sort_session_window_df(bars)
    ctx["bars"] = bars
    ctx["analysis_mode"] = "phase1_compatible_analysis_intraday"
    return ctx


def build_news_flag_behavior_links(news_master: pd.DataFrame, reaction_matrix: pd.DataFrame, daily_master: pd.DataFrame, day_labels: pd.DataFrame, rollup: pd.DataFrame) -> pd.DataFrame:
    nm = news_master.copy()
    rm = reaction_matrix.copy()
    dm = daily_master.copy()
    dl = day_labels.copy()
    rp = rollup.copy()

    nm["trade_date_ist"] = parse_date_series(nm["trade_date_ist"])
    rm["trade_date_ist"] = parse_date_series(rm["trade_date_ist"])
    rp["trade_date_ist"] = parse_date_series(rp["trade_date_ist"])

    if not dm.empty:
        dm["trade_date_ist"] = parse_date_series(dm["trade_date_ist"])
    if not dl.empty:
        dl["trade_date_ist"] = parse_date_series(dl["trade_date_ist"])

    day_cols = ["trade_date_ist"]
    for c in ["wti_net_day_return_pct", "brent_net_day_return_pct"]:
        if c in dm.columns:
            day_cols.append(c)

    label_cols = ["trade_date_ist"]
    for c in ["price_path_bucket_primary", "geo_bucket_primary"]:
        if c in dl.columns:
            label_cols.append(c)

    rollup_cols = ["trade_date_ist"]
    for c in [
        "major_headline_count",
        "verified_event_count",
        "causal_event_count",
        "news_coverage_status",
        "news_quality_gate_passed_for_day",
        "dominant_event_id"
    ]:
        if c in rp.columns:
            rollup_cols.append(c)

    out = (
        nm.merge(rm, how="left", on=["event_id", "trade_date_ist"])
          .merge(
              dm[day_cols] if len(day_cols) > 1 else pd.DataFrame(columns=["trade_date_ist"]),
              how="left",
              on="trade_date_ist"
          )
          .merge(
              dl[label_cols] if len(label_cols) > 1 else pd.DataFrame(columns=["trade_date_ist"]),
              how="left",
              on="trade_date_ist"
          )
          .merge(
              rp[rollup_cols] if len(rollup_cols) > 1 else pd.DataFrame(columns=["trade_date_ist"]),
              how="left",
              on="trade_date_ist"
          )
    )

    keep_cols = [
        "trade_date_ist", "event_id", "headline_rank_for_day", "headline", "summary_1_sentence",
        "event_type", "market_interpretation_bucket",
        "trump_statement_flag", "trump_post_flag", "iran_hormuz_flag", "shipping_disruption_flag",
        "sanctions_flag", "talks_negotiation_flag", "ceasefire_flag", "attack_threat_flag",
        "opec_supply_flag", "inventory_flag", "usd_macro_flag", "equity_risk_sentiment_flag",
        "expected_wti_bias", "expected_brent_bias",
        "event_session_window_ist",
        "wti_ret_1h_pct", "wti_ret_4h_pct", "wti_mfe_4h_pct", "wti_mae_4h_pct",
        "wti_reaction_strength_score_1_to_5", "wti_reaction_matched_expected_flag",
        "brent_ret_1h_pct", "brent_ret_4h_pct", "brent_mfe_4h_pct", "brent_mae_4h_pct",
        "brent_reaction_strength_score_1_to_5", "brent_reaction_matched_expected_flag",
        "wti_net_day_return_pct", "brent_net_day_return_pct",
        "price_path_bucket_primary", "geo_bucket_primary", "no_major_headline_flag",
        "major_headline_count", "verified_event_count", "causal_event_count",
        "news_coverage_status", "news_quality_gate_passed_for_day",
        "coverage_verified_flag", "news_row_quality", "shock_proximity_minutes", "shock_proximity_score",
        "is_shock_timed_candidate",
        "source_name", "source_url"
    ]

    for c in keep_cols:
        if c not in out.columns:
            out[c] = np.nan

    out = out[keep_cols].sort_values(["trade_date_ist", "headline_rank_for_day"]).reset_index(drop=True)
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


# ============================================================
# ENRICH EXISTING FILES
# ============================================================

def map_geo_bucket(event_type: str, interpretation: str, no_major: bool) -> Tuple[str, str]:
    if no_major:
        return "no_major_catalyst", "price_led_or_technical"
    et = str(event_type)
    if et in {"shipping_geopolitics", "attack_threat_sanctions", "talks_ceasefire", "trump_rhetoric"}:
        return "geopolitics", interpretation
    if et in {"opec_supply", "inventory"}:
        return "physical_supply", interpretation
    if et in {"usd_macro", "equity_risk_sentiment"}:
        return "macro_risk", interpretation
    return "other_news", interpretation


def enrich_day_type_labels(day_labels: pd.DataFrame, deviations: pd.DataFrame, rollup: pd.DataFrame) -> pd.DataFrame:
    if day_labels.empty:
        return day_labels

    dl = day_labels.copy()
    dv = deviations.copy()
    rp = rollup.copy()

    dl["trade_date_ist"] = parse_date_series(dl["trade_date_ist"])
    if not dv.empty:
        dv["trade_date_ist"] = parse_date_series(dv["trade_date_ist"])
    rp["trade_date_ist"] = parse_date_series(rp["trade_date_ist"])

    out = dl.merge(
    rp[[
        "trade_date_ist", "major_headline_count", "verified_event_count",
        "causal_event_count", "no_major_headline_flag", "news_coverage_status",
        "news_quality_gate_passed_for_day",
        "dominant_event_type", "dominant_market_interpretation_bucket"
    ]],
    how="left",
    on="trade_date_ist"
)

    if not dv.empty and "deviation_flag" in dv.columns:
        out = out.merge(
            dv[["trade_date_ist", "deviation_flag"]],
            how="left",
            on="trade_date_ist",
            suffixes=("", "_dev")
        )
        out["deviation_from_recent_pattern_flag"] = out["deviation_flag"].fillna(out.get("deviation_from_recent_pattern_flag", False))
        out = out.drop(columns=[c for c in ["deviation_flag"] if c in out.columns])

    geo1, geo2 = [], []
    for _, r in out.iterrows():
        g1, g2 = map_geo_bucket(
            r.get("dominant_event_type", ""),
            r.get("dominant_market_interpretation_bucket", ""),
            boolize(r.get("no_major_headline_flag"))
        )
        geo1.append(g1)
        geo2.append(g2)
    out["geo_bucket_primary"] = geo1
    out["geo_bucket_secondary"] = geo2

    base_conf_raw = out["bucket_confidence_1_to_5"] if "bucket_confidence_1_to_5" in out.columns else pd.Series(2, index=out.index)
    base_conf = pd.to_numeric(base_conf_raw, errors="coerce").fillna(2).astype(int)
    valid_news_for_labeling = (
        out["news_quality_gate_passed_for_day"].fillna(False)
        & out["news_coverage_status"].fillna("").astype(str).isin(["confirmed_causal", "verified_but_not_causal"])
    )
    uplift = np.where(
        valid_news_for_labeling & (out["major_headline_count"].fillna(0).astype(int) > 0),
        1,
        0
    )

    out["bucket_confidence_1_to_5"] = np.clip(base_conf + uplift, 1, 5)

    out["why_this_bucket_short"] = np.where(
        valid_news_for_labeling & (out["major_headline_count"].fillna(0).astype(int) > 0),
        "price_plus_verified_news_reaction",
        out.get("why_this_bucket_short", "price_derived_only")
    )
    out["main_evidence_short"] = np.where(
        valid_news_for_labeling & (out["major_headline_count"].fillna(0).astype(int) > 0),
        "daily_intraday_bar_features_plus_verified_news",
        out.get("main_evidence_short", "daily_intraday_bar_features")
    )
    
    out["deviation_type_short"] = np.where(
        out["deviation_from_recent_pattern_flag"].fillna(False) & (out["major_headline_count"].fillna(0).astype(int) > 0),
        "news_linked_deviation",
        out.get("deviation_type_short", "")
    )

    out = out.sort_values("trade_date_ist").reset_index(drop=True)
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


def enrich_deviation_labels(deviations: pd.DataFrame, rollup: pd.DataFrame) -> pd.DataFrame:
    if deviations.empty:
        return deviations

    dv = deviations.copy()
    rp = rollup.copy()
    dv["trade_date_ist"] = parse_date_series(dv["trade_date_ist"])
    rp["trade_date_ist"] = parse_date_series(rp["trade_date_ist"])

    out = dv.merge(rp, how="left", on="trade_date_ist")

    reasons, alt_short, alt_flag = [], [], []
    for _, r in out.iterrows():
        dev = boolize(r.get("deviation_flag"))
        no_major = boolize(r.get("no_major_headline_flag"))
        evt = str(r.get("dominant_event_type", ""))
        interp = str(r.get("dominant_market_interpretation_bucket", ""))
        coverage_status = str(r.get("news_coverage_status", ""))
        trusted_news = coverage_status in {"confirmed_causal", "verified_but_not_causal"}
        
        

        if not dev:
            reasons.append("")
            alt_short.append("")
            alt_flag.append(False)
        elif not trusted_news:
            reasons.append("news_coverage_insufficient_for_causal_attribution")
            alt_short.append("deviation_unattributed_due_to_weak_news_coverage")
            alt_flag.append(False)
        elif no_major:
            reasons.append("no_major_verified_catalyst_price_led")
            alt_short.append("technical_or_liquidity_deviation")
            alt_flag.append(True)
        else:
            reasons.append(f"{evt}|{interp}")
            if evt in {"shipping_geopolitics", "attack_threat_sanctions", "opec_supply", "inventory"}:
                alt_short.append("event_driven_trend_or_range_expansion")
            elif evt in {"usd_macro", "equity_risk_sentiment", "trump_rhetoric"}:
                alt_short.append("macro_or_rhetoric_cross_current")
            else:
                alt_short.append("news_linked_regime_shift")
            alt_flag.append(True)

    out["likely_reason_for_deviation"] = reasons
    out["related_news_event_id_if_any"] = np.where(
        out["deviation_flag"].fillna(False)
        & out["news_coverage_status"].fillna("").astype(str).eq("confirmed_causal")
        & (~out["no_major_headline_flag"].fillna(False)),
        out["dominant_event_id"].fillna(""),
        ""
    )
    out["did_deviation_still_follow_an_alternate_repeatable_pattern"] = alt_flag
    out["alternate_pattern_short"] = alt_short

    keep = [
        "trade_date_ist", "expected_pattern_based_on_prior_5_days", "actual_pattern_observed",
        "deviation_flag", "deviation_severity_1_to_5", "likely_reason_for_deviation",
        "related_news_event_id_if_any", "did_deviation_still_follow_an_alternate_repeatable_pattern",
        "alternate_pattern_short"
    ]
    for c in keep:
        if c not in out.columns:
            out[c] = np.nan

    out = out[keep].sort_values("trade_date_ist").reset_index(drop=True)
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


def enrich_day_window_matrix(day_window_matrix: pd.DataFrame, rollup: pd.DataFrame) -> pd.DataFrame:
    if day_window_matrix.empty:
        return day_window_matrix

    mx = day_window_matrix.copy()
    rp = rollup.copy()
    mx["trade_date_ist"] = parse_date_series(mx["trade_date_ist"])
    rp["trade_date_ist"] = parse_date_series(rp["trade_date_ist"])

    out = mx.merge(
        rp[[
            "trade_date_ist", "major_headline_count", "no_major_headline_flag",
            "dominant_event_id", "dominant_event_type",
            "dominant_market_interpretation_bucket", "dominant_event_session_window_ist"
        ]],
        how="left", on="trade_date_ist"
    ).sort_values("trade_date_ist").reset_index(drop=True)

    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


def enrich_archetype_features(arche: pd.DataFrame, day_labels: pd.DataFrame, rollup: pd.DataFrame, news_master: pd.DataFrame) -> pd.DataFrame:
    if arche.empty:
        return arche

    ar = arche.copy()
    dl = day_labels.copy()
    rp = rollup.copy()
    nm = news_master.copy()

    ar["trade_date_ist"] = parse_date_series(ar["trade_date_ist"])
    dl["trade_date_ist"] = parse_date_series(dl["trade_date_ist"])
    rp["trade_date_ist"] = parse_date_series(rp["trade_date_ist"])
    nm["trade_date_ist"] = parse_date_series(nm["trade_date_ist"])

    daily_news_scores = nm.groupby("trade_date_ist").agg(
        trump_count=("trump_statement_flag", "sum"),
        shipping_count=("shipping_disruption_flag", "sum"),
        iran_hormuz_count=("iran_hormuz_flag", "sum"),
        sanctions_count=("sanctions_flag", "sum"),
        attack_count=("attack_threat_flag", "sum"),
        opec_count=("opec_supply_flag", "sum"),
        inventory_count=("inventory_flag", "sum"),
    ).reset_index()

    out = ar.merge(rp, how="left", on="trade_date_ist").merge(
        dl[["trade_date_ist", "price_path_bucket_primary", "geo_bucket_primary"]],
        how="left", on="trade_date_ist"
    ).merge(daily_news_scores, how="left", on="trade_date_ist")

    for c in ["trump_count", "shipping_count", "iran_hormuz_count", "sanctions_count", "attack_count", "opec_count", "inventory_count"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    out["rhetoric_intensity_score"] = np.clip(
        1 + out["trump_count"] + 0.5 * out["attack_count"] + 0.5 * out["sanctions_count"],
        1, 5
    )
    out["shipping_risk_score"] = np.clip(
        1 + out["shipping_count"] + out["iran_hormuz_count"],
        1, 5
    )
    out["physical_supply_risk_score"] = np.clip(
        1 + out["opec_count"] + 0.5 * out["inventory_count"] + 0.5 * out["sanctions_count"] + 0.5 * out["attack_count"],
        1, 5
    )

    out["day_type_vector_json"] = out.apply(
        lambda r: safe_json({
            "price_path_bucket_primary": r.get("price_path_bucket_primary", ""),
            "geo_bucket_primary": r.get("geo_bucket_primary", ""),
            "major_headline_count": r.get("major_headline_count", 0),
            "dominant_event_type": r.get("dominant_event_type", ""),
            "dominant_market_interpretation_bucket": r.get("dominant_market_interpretation_bucket", ""),
            "dominant_expected_wti_bias": r.get("dominant_expected_wti_bias", "neutral"),
        }),
        axis=1
    )

    drop_cols = ["trump_count", "shipping_count", "iran_hormuz_count", "sanctions_count", "attack_count", "opec_count", "inventory_count"]
    out = out.drop(columns=[c for c in drop_cols if c in out.columns])

    out = out.sort_values("trade_date_ist").reset_index(drop=True)
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


# ============================================================
# PREDICTIVE SCORING + ENGINE
# ============================================================

def build_predictive_scoring_v1(daily_master: pd.DataFrame, deviations: pd.DataFrame, rollup: pd.DataFrame) -> pd.DataFrame:
    dm = daily_master.copy()
    dv = deviations.copy()
    rp = rollup.copy()

    dm["trade_date_ist"] = parse_date_series(dm["trade_date_ist"])
    if not dv.empty:
        dv["trade_date_ist"] = parse_date_series(dv["trade_date_ist"])
    rp["trade_date_ist"] = parse_date_series(rp["trade_date_ist"])

    merge_cols = ["trade_date_ist"]
    if not dv.empty:
        for c in ["expected_pattern_based_on_prior_5_days", "deviation_flag"]:
            if c in dv.columns:
                merge_cols.append(c)

    out = dm.merge(
        dv[merge_cols] if len(merge_cols) > 1 else pd.DataFrame(columns=["trade_date_ist"]),
        how="left", on="trade_date_ist"
    ).merge(rp, how="left", on="trade_date_ist")

    rows = []
    for _, r in out.iterrows():
        coverage_status = str(r.get("news_coverage_status", ""))
        trusted_news = coverage_status in {"confirmed_causal", "verified_but_not_causal"}

        news_bias = sign_bias_to_score(r.get("dominant_expected_wti_bias", "neutral")) if trusted_news else 0
        no_major = boolize(r.get("no_major_headline_flag")) if trusted_news else False
        gap = to_float_scalar(r.get("wti_gap_pct_native"))
        expected_pattern = str(r.get("expected_pattern_based_on_prior_5_days", "")).strip()

        directional_bias_score = 0
        volatility_score = 0

        directional_bias_score += news_bias * 40

        if pd.notna(gap):
            directional_bias_score += int(np.sign(gap) * min(abs(gap) * 8, 20))
            volatility_score += 2 if abs(gap) >= 2 else 1 if abs(gap) >= 1 else 0

        evt = str(r.get("dominant_event_type", "")) if trusted_news else ""
        if evt in {"shipping_geopolitics", "attack_threat_sanctions", "opec_supply", "inventory"}:
            volatility_score += 2
        elif evt in {"usd_macro", "equity_risk_sentiment", "trump_rhetoric"}:
            volatility_score += 1

        mcount = to_float_scalar(r.get("major_headline_count"))
        if trusted_news and pd.notna(mcount) and mcount >= 2:
            volatility_score += 1

        if trusted_news and no_major:
            volatility_score -= 1

        if trusted_news and abs(directional_bias_score) >= 35 and volatility_score >= 2:
            predicted_day_type_primary = "all_day_trend_up" if directional_bias_score > 0 else "all_day_trend_down"
        elif trusted_news and no_major and volatility_score <= 0:
            predicted_day_type_primary = "range_chop"
        else:
            predicted_day_type_primary = expected_pattern if expected_pattern else "mixed_regime_day"

        predicted_directional_bias = "bullish" if directional_bias_score > 15 else "bearish" if directional_bias_score < -15 else "neutral"

        prediction_confidence_1_to_5 = clamp(
            1
            + int(abs(directional_bias_score) >= 20)
            + int(abs(directional_bias_score) >= 40)
            + max(0, volatility_score // 2),
            1, 5
        )

        if not trusted_news:
            prediction_confidence_1_to_5 = max(1, prediction_confidence_1_to_5 - 1)

        rows.append({
            "trade_date_ist": r["trade_date_ist"],
            "expected_pattern_based_on_prior_5_days": expected_pattern,
            "news_coverage_status": coverage_status,
            "dominant_event_type": evt,
            "dominant_market_interpretation_bucket": r.get("dominant_market_interpretation_bucket", "") if trusted_news else "",
            "dominant_expected_wti_bias": r.get("dominant_expected_wti_bias", "neutral") if trusted_news else "unknown_due_to_coverage",
            "major_headline_count": r.get("major_headline_count", 0) if trusted_news else 0,
            "no_major_headline_flag": no_major,
            "wti_gap_pct_native": gap,
            "directional_bias_score": directional_bias_score,
            "volatility_score": volatility_score,
            "predicted_day_type_primary": predicted_day_type_primary,
            "predicted_directional_bias": predicted_directional_bias,
            "prediction_confidence_1_to_5": prediction_confidence_1_to_5,
        })

    pred = pd.DataFrame(rows).sort_values("trade_date_ist").reset_index(drop=True)
    pred["trade_date_ist"] = pred["trade_date_ist"].astype(str)
    return pred


def build_decision_engine_v1(pred: pd.DataFrame, reaction_matrix: pd.DataFrame, rollup: pd.DataFrame) -> pd.DataFrame:
    pr = pred.copy()
    rm = reaction_matrix.copy()
    rp = rollup.copy()

    pr["trade_date_ist"] = parse_date_series(pr["trade_date_ist"])
    rm["trade_date_ist"] = parse_date_series(rm["trade_date_ist"])
    rp["trade_date_ist"] = parse_date_series(rp["trade_date_ist"])

    dominant = rp[[
        "trade_date_ist", "dominant_event_id", "dominant_event_type",
        "dominant_expected_wti_bias", "no_major_headline_flag", "news_coverage_status"
    ]].merge(
        rm, how="left", left_on=["trade_date_ist", "dominant_event_id"], right_on=["trade_date_ist", "event_id"]
    )

    out = pr.merge(
        dominant[[
            "trade_date_ist", "dominant_event_id", "news_coverage_status",
            "wti_ret_1h_pct", "wti_ret_4h_pct",
            "wti_reaction_matched_expected_flag", "wti_reaction_strength_score_1_to_5",
            "event_session_window_ist", "wti_first_reaction_window_ist"
        ]],
        how="left", on="trade_date_ist", suffixes=("", "_dom")
    )

    if "news_coverage_status_dom" in out.columns:
        out["news_coverage_status"] = out["news_coverage_status"].fillna(out["news_coverage_status_dom"])
        out = out.drop(columns=["news_coverage_status_dom"])

    rows = []
    for _, r in out.iterrows():
        coverage_status = str(r.get("news_coverage_status", ""))
        confirmed_causal = coverage_status == "confirmed_causal"
        trusted_news = coverage_status in {"confirmed_causal", "verified_but_not_causal"}

        no_major = boolize(r.get("no_major_headline_flag")) if trusted_news else False
        dir_bias = str(r.get("predicted_directional_bias", "neutral"))
        matched = r.get("wti_reaction_matched_expected_flag")
        ret1 = to_float_scalar(r.get("wti_ret_1h_pct"))
        ret4 = to_float_scalar(r.get("wti_ret_4h_pct"))
        strength = to_float_scalar(r.get("wti_reaction_strength_score_1_to_5"))
        conf_val = to_float_scalar(r.get("prediction_confidence_1_to_5"))
        conf = int(conf_val) if pd.notna(conf_val) else 1

        engine_context = "neutral_wait"
        trade_bias = "flat"
        trigger_type = "none"
        validation_rule = "wait_for_price_confirmation"
        invalidation_rule = "n/a"
        sizing_bucket = "skip"
        notes = "insufficient_signal"

        if not trusted_news:
            engine_context = "price_only_or_unverified_news"
            trade_bias = "flat"
            trigger_type = "wait_for_opening_range_break"
            validation_rule = "do_not_use_news_as_causal_signal_when_coverage_is_weak"
            invalidation_rule = "skip_if_move_is_justified_only_by_unverified_news"
            sizing_bucket = "tiny"
            notes = "news_coverage_insufficient"
        elif no_major:
            if str(r.get("predicted_day_type_primary", "")) == "range_chop":
                engine_context = "mean_reversion_watch"
                trade_bias = "fade_extremes"
                trigger_type = "range_extreme_rejection"
                validation_rule = "only_trade_rejections_near_prior_extremes"
                invalidation_rule = "abort_if_range_breaks_and_holds"
                sizing_bucket = "small"
                notes = "no_major_verified_catalyst_and_low_expected_volatility"
            else:
                engine_context = "technical_watch"
                trade_bias = "flat"
                trigger_type = "wait_for_opening_range_break"
                validation_rule = "only_act_after_clean_range_break"
                invalidation_rule = "ignore_false_breaks_without_follow_through"
                sizing_bucket = "small"
                notes = "verified_no_major_catalyst_price_led_day"
        else:
            if confirmed_causal and dir_bias == "bullish" and matched is True and pd.notna(strength) and strength >= 2:
                engine_context = "event_follow_through_long"
                trade_bias = "long"
                trigger_type = "buy_pullback_or_breakout"
                validation_rule = "headline_bias_positive_and_1h_to_4h_reaction_confirmed"
                invalidation_rule = "stand_down_if_event_window_low_breaks"
                sizing_bucket = "full" if conf >= 4 and strength >= 3 else "medium"
                notes = f"confirmed_positive_event_reaction ret1h={ret1:.2f} ret4h={ret4:.2f}" if pd.notna(ret1) and pd.notna(ret4) else "confirmed_positive_event_reaction"
            elif confirmed_causal and dir_bias == "bearish" and matched is True and pd.notna(strength) and strength >= 2:
                engine_context = "event_follow_through_short"
                trade_bias = "short"
                trigger_type = "sell_rally_or_breakdown"
                validation_rule = "headline_bias_negative_and_1h_to_4h_reaction_confirmed"
                invalidation_rule = "stand_down_if_event_window_high_breaks"
                sizing_bucket = "full" if conf >= 4 and strength >= 3 else "medium"
                notes = f"confirmed_negative_event_reaction ret1h={ret1:.2f} ret4h={ret4:.2f}" if pd.notna(ret1) and pd.notna(ret4) else "confirmed_negative_event_reaction"
            elif confirmed_causal and dir_bias in {"bullish", "bearish"} and matched is False:
                engine_context = "event_fade_or_cross_current"
                trade_bias = "reduced_conviction"
                trigger_type = "wait_for_second_signal"
                validation_rule = "do_not_chase_first_headline_if_price_disagrees"
                invalidation_rule = "skip_if_cross_current_persists"
                sizing_bucket = "tiny"
                notes = "headline_and_price_conflict"
            else:
                engine_context = "headline_present_but_weak"
                trade_bias = "flat"
                trigger_type = "wait_for_us_open_or_range_resolution"
                validation_rule = "need_follow_through_after_headline"
                invalidation_rule = "skip_on_low_energy_tape"
                sizing_bucket = "small"
                notes = "verified_headline_present_without_strong_confirmation"

        rows.append({
            "trade_date_ist": r["trade_date_ist"],
            "dominant_event_id": r.get("dominant_event_id", ""),
            "news_coverage_status": coverage_status,
            "predicted_day_type_primary": r.get("predicted_day_type_primary", ""),
            "predicted_directional_bias": dir_bias,
            "prediction_confidence_1_to_5": conf,
            "engine_context": engine_context,
            "recommended_trade_bias": trade_bias,
            "trigger_type": trigger_type,
            "validation_rule": validation_rule,
            "invalidation_rule": invalidation_rule,
            "sizing_bucket": sizing_bucket,
            "event_session_window_ist": r.get("event_session_window_ist", ""),
            "wti_first_reaction_window_ist": r.get("wti_first_reaction_window_ist", ""),
            "wti_ret_1h_pct": ret1,
            "wti_ret_4h_pct": ret4,
            "notes": notes,
        })

    eng = pd.DataFrame(rows).sort_values("trade_date_ist").reset_index(drop=True)
    eng["trade_date_ist"] = eng["trade_date_ist"].astype(str)
    return eng


# ============================================================
# OPTIONAL MD REPORT
# ============================================================

def build_trader_style_report(rollup: pd.DataFrame, pred: pd.DataFrame, engine: pd.DataFrame, deviations: pd.DataFrame) -> str:
    rp = rollup.copy()
    pr = pred.copy()
    en = engine.copy()
    dv = deviations.copy()

    if not rp.empty:
        rp["trade_date_ist"] = pd.to_datetime(rp["trade_date_ist"], errors="coerce")
    if not pr.empty:
        pr["trade_date_ist"] = pd.to_datetime(pr["trade_date_ist"], errors="coerce")
    if not en.empty:
        en["trade_date_ist"] = pd.to_datetime(en["trade_date_ist"], errors="coerce")
    if not dv.empty:
        dv["trade_date_ist"] = pd.to_datetime(dv["trade_date_ist"], errors="coerce")

    merged = rp.merge(pr, how="left", on="trade_date_ist").merge(en, how="left", on="trade_date_ist", suffixes=("", "_engine"))
    if not dv.empty:
        merged = merged.merge(dv[["trade_date_ist", "deviation_flag", "likely_reason_for_deviation"]], how="left", on="trade_date_ist")

    lines = []
    lines.append("# Trader-style news / reaction report")
    lines.append("")
    lines.append("## Regime map")
    lines.append("")

    if merged.empty:
        lines.append("- No rows available.")
        return "\n".join(lines)

    counts = merged["predicted_day_type_primary"].fillna("unknown").value_counts().to_dict()
    for k, v in counts.items():
        lines.append(f"- {k}: {v} day(s)")
    lines.append("")
    lines.append("## Strongest recurring behaviors")
    lines.append("")

    top_evt = merged["dominant_event_type"].fillna("unknown").value_counts().head(5).to_dict()
    for k, v in top_evt.items():
        lines.append(f"- {k}: {v} dominant day(s)")
    lines.append("")

    lines.append("## Weak spots in data")
    lines.append("")
    no_news_days = int(merged["no_major_headline_flag"].fillna(False).sum()) if "no_major_headline_flag" in merged.columns else 0
    conflict_days = int(((merged.get("predicted_directional_bias", pd.Series(dtype=str)).fillna("neutral").isin(["bullish", "bearish"])) &
                         (merged.get("recommended_trade_bias", pd.Series(dtype=str)).fillna("flat").eq("reduced_conviction"))).sum()) if not merged.empty else 0
    lines.append(f"- No-major-catalyst days: {no_news_days}")
    lines.append(f"- Headline/price conflict days: {conflict_days}")
    lines.append("- News relevance still depends on your raw news input quality and timestamps.")
    lines.append("")

    lines.append("## Build next")
    lines.append("")
    lines.append("- Add source-verified ingestion from your preferred wires/API.")
    lines.append("- Add better timestamp precision for event time vs first market reaction.")
    lines.append("- Add forward prediction labels instead of same-day interpretation only.")
    lines.append("- Add execution logic with stop/target simulation on the decision layer.")
    lines.append("")

    lines.append("## Daily sheet")
    lines.append("")
    for _, r in merged.sort_values("trade_date_ist").iterrows():
        d = r["trade_date_ist"]
        d = d.strftime("%Y-%m-%d") if pd.notna(d) else ""
        lines.append(
            f"- {d}: event={r.get('dominant_event_type','')}, "
            f"headline_count={r.get('major_headline_count','')}, "
            f"pred={r.get('predicted_day_type_primary','')}/{r.get('predicted_directional_bias','')}, "
            f"engine={r.get('recommended_trade_bias','')}, "
            f"deviation={r.get('deviation_flag','')}"
        )

    return "\n".join(lines)

# ============================================================
# NEWLY ADDED BY CODEX
# ============================================================

def resolve_intraday_source(
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_60m: pd.DataFrame,
    product: str = "",
) -> dict:
    candidates = [
        ("5m", df_5m),
        ("15m", df_15m),
        ("60m", df_60m),
    ]

    for timeframe, df in candidates:
        if df is not None and not df.empty:
            out = df.copy()
            if "trade_date_ist" in out.columns:
                out["trade_date_ist"] = parse_date_series(out["trade_date_ist"])
            if "timestamp_ist" in out.columns:
                out["timestamp_ist"] = parse_dt_series(out["timestamp_ist"])
            return {
                "product": str(product).upper(),
                "timeframe_used": timeframe,
                "bars": out,
                "selection_mode": "best_available_intraday",
            }

    return {
        "product": str(product).upper(),
        "timeframe_used": "",
        "bars": pd.DataFrame(),
        "selection_mode": "best_available_intraday",
    }

def _price_namespace(df: pd.DataFrame) -> str:
    inr_cols = ["open_inr", "high_inr", "low_inr", "close_inr"]
    if df is not None and not df.empty and all(c in df.columns for c in inr_cols):
        if df[inr_cols].notna().any().any():
            return "inr"
    return "native"


def _col(ns: str, field: str) -> str:
    return f"{field}_{ns}"


def _numeric_col(df: pd.DataFrame, col_name: str) -> pd.Series:
    if col_name not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[col_name], errors="coerce")


def _source_rank(source_name: str) -> float:
    s = str(source_name or "").strip().lower()
    for k, v in PREFERRED_LIVE_SOURCE_SCORES.items():
        if k in s:
            return v
    return 0.40


def _severity_bucket(score: float) -> str:
    if pd.isna(score):
        return "unknown"
    if score >= 8.5:
        return "very_high"
    if score >= 6.5:
        return "high"
    if score >= 4.5:
        return "medium"
    if score >= 2.5:
        return "low"
    return "very_low"


def _sign_label(x: float) -> str:
    if pd.isna(x):
        return "neutral"
    if x > 0:
        return "bullish"
    if x < 0:
        return "bearish"
    return "neutral"


def canonicalize_url(url: str) -> str:
    s = str(url or "").strip()
    if not s:
        return ""
    try:
        p = urlparse(s)
        scheme = p.scheme.lower() or "https"
        netloc = p.netloc.lower()
        path = re.sub(r"/{2,}", "/", p.path or "/").rstrip("/")
        if not path:
            path = "/"
        keep_params = []
        for k, v in parse_qsl(p.query, keep_blank_values=True):
            lk = str(k).lower()
            if lk.startswith("utm_") or lk in {"spm", "cmpid", "taid", "sr", "source", "eref"}:
                continue
            keep_params.append((k, v))
        query = urlencode(keep_params, doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return s
    

def _canonical_text(x: str) -> str:
    s = str(x or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _story_key(headline: str) -> str:
    words = _canonical_text(headline).split()
    stop = {
        "the", "a", "an", "to", "of", "in", "on", "at", "for", "and", "with",
        "says", "say", "live", "update", "updates", "breaking", "report"
    }
    words = [w for w in words if w not in stop]
    return " ".join(words[:12])


def normalize_canonical_story_key(url: str, source_name: str = "") -> str:
    u = canonicalize_url(url)
    if not u:
        return ""
    p = urlparse(u)
    host = p.netloc.lower()
    if "cnn.com" in host:
        host = "cnn.com"
    elif "aljazeera.com" in host:
        host = "aljazeera.com"
    path = p.path.rstrip("/")
    return f"{host}{path}".lower()

def _first_bar_in_window(day_df: pd.DataFrame, window_name: str) -> Optional[pd.Series]:
    g = day_df[day_df["session_window_ist"].eq(window_name)].sort_values("timestamp_ist")
    if g.empty:
        return None
    return g.iloc[0]


def _window_slice(day_df: pd.DataFrame, start_ts: pd.Timestamp, minutes: int) -> pd.DataFrame:
    return day_df[
        (day_df["timestamp_ist"] >= start_ts) &
        (day_df["timestamp_ist"] <= start_ts + pd.Timedelta(minutes=minutes))
    ].sort_values("timestamp_ist").copy()


def _trade_minutes(ts_a, ts_b) -> float:
    if pd.isna(ts_a) or pd.isna(ts_b):
        return np.nan
    return (ts_b - ts_a).total_seconds() / 60.0


def stable_event_id(trade_date, headline: str, source_name: str) -> str:
    raw = f"{trade_date}|{_story_key(headline)}|{str(source_name or '').strip().lower()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def dedupe_and_cluster_news_candidates(raw_news: pd.DataFrame) -> pd.DataFrame:
    if raw_news is None or raw_news.empty:
        return pd.DataFrame()

    df = raw_news.copy()

    for c in ["headline", "source_name", "source_url"]:
        if c not in df.columns:
            df[c] = ""

    if "event_datetime_ist" not in df.columns:
        dtcol = choose_col(
            df,
            ["event_datetime_ist", "published_at", "published_at_utc", "published_at_ist", "timestamp", "datetime"],
        )
        df["event_datetime_ist"] = parse_dt_series(df[dtcol]) if dtcol else pd.NaT
    else:
        df["event_datetime_ist"] = parse_dt_series(df["event_datetime_ist"])

    if "trade_date_ist" not in df.columns:
        df["trade_date_ist"] = pd.to_datetime(df["event_datetime_ist"], errors="coerce").dt.date
    else:
        df["trade_date_ist"] = parse_date_series(df["trade_date_ist"])

    if "normalized_canonical_key" not in df.columns:
        df["normalized_canonical_key"] = df.apply(
            lambda r: normalize_canonical_story_key(
                r.get("source_url", ""),
                r.get("source_name", ""),
            ),
            axis=1,
        )

    fallback_missing_key = (
        df["normalized_canonical_key"].fillna("").astype(str).str.strip().eq("")
    )
    if fallback_missing_key.any():
        df.loc[fallback_missing_key, "normalized_canonical_key"] = (
            df.loc[fallback_missing_key, "headline"]
            .fillna("")
            .astype(str)
            .map(_canonical_text)
            .map(_story_key)
        )

    if "_source_rank" not in df.columns:
        df["_source_rank"] = df["source_name"].map(_source_rank)
    else:
        df["_source_rank"] = pd.to_numeric(df["_source_rank"], errors="coerce").fillna(0)

    if "has_url" not in df.columns:
        df["has_url"] = df["source_url"].fillna("").astype(str).str.len().gt(0)
    else:
        df["has_url"] = df["has_url"].map(boolize)

    if "has_ts" not in df.columns:
        df["has_ts"] = df["event_datetime_ist"].notna()
    else:
        df["has_ts"] = df["has_ts"].map(boolize)

    df = df[
        df["trade_date_ist"].notna() &
        df["normalized_canonical_key"].fillna("").astype(str).str.strip().ne("")
    ].copy()

    if df.empty:
        return df.reset_index(drop=True)

    df = df.sort_values(
        [
            "trade_date_ist",
            "normalized_canonical_key",
            "_source_rank",
            "has_url",
            "has_ts",
            "event_datetime_ist",
        ],
        ascending=[True, True, False, False, False, True],
    ).drop_duplicates(
        subset=["trade_date_ist", "normalized_canonical_key"],
        keep="first",
    ).reset_index(drop=True)

    kept = []
    last_seen = {}

    for _, row in df.iterrows():
        d = row["trade_date_ist"]
        key = row["normalized_canonical_key"]
        ts = row["event_datetime_ist"]

        cluster_ok = False
        if (d, key) in last_seen:
            prev_ts = last_seen[(d, key)]
            if pd.notna(ts) and pd.notna(prev_ts):
                cluster_ok = abs((ts - prev_ts).total_seconds()) <= EVENT_CLUSTER_MINUTES * 60

        if (d, key) not in last_seen or not cluster_ok:
            kept.append(row.to_dict())

        last_seen[(d, key)] = ts

    out = pd.DataFrame(kept)
    if out.empty:
        return out

    out["trade_date_ist"] = parse_date_series(out["trade_date_ist"])
    out["event_datetime_ist"] = parse_dt_series(out["event_datetime_ist"])

    return out.reset_index(drop=True)


def build_event_severity_features(news_master: pd.DataFrame, reaction_matrix: pd.DataFrame) -> pd.DataFrame:
    if news_master.empty:
        return pd.DataFrame()

    nm = news_master.copy()
    rm = reaction_matrix.copy()

    nm["trade_date_ist"] = parse_date_series(nm["trade_date_ist"])
    if "event_datetime_ist" in nm.columns:
        nm["event_datetime_ist"] = parse_dt_series(nm["event_datetime_ist"])
    if not rm.empty:
        rm["trade_date_ist"] = parse_date_series(rm["trade_date_ist"])

    out = nm.merge(
        rm[[
            "event_id", "trade_date_ist",
            "wti_ret_1h_pct", "wti_ret_4h_pct",
            "brent_ret_1h_pct", "brent_ret_4h_pct",
            "wti_reaction_strength_score_1_to_5",
            "brent_reaction_strength_score_1_to_5",
        ]] if not rm.empty else pd.DataFrame(columns=["event_id", "trade_date_ist"]),
        how="left",
        on=["event_id", "trade_date_ist"],
    )

    weighted_flags = {
        "iran_hormuz_flag": 2.7,
        "shipping_disruption_flag": 2.2,
        "attack_threat_flag": 1.8,
        "sanctions_flag": 1.5,
        "opec_supply_flag": 1.3,
        "inventory_flag": 1.0,
        "talks_negotiation_flag": 1.7,
        "ceasefire_flag": 1.9,
        "usd_macro_flag": 0.9,
        "equity_risk_sentiment_flag": 0.8,
        "trump_statement_flag": 0.6,
        "trump_post_flag": 0.5,
    }

    score = pd.Series(0.0, index=out.index)
    for flag, wt in weighted_flags.items():
        if flag in out.columns:
            score += out[flag].fillna(False).astype(int) * wt

    score += pd.to_numeric(
    out["confidence_1_to_5"] if "confidence_1_to_5" in out.columns else pd.Series(1.0, index=out.index),
    errors="coerce",).fillna(1.0) * 0.9
    
    score += pd.to_numeric(
    out["shock_proximity_score"] if "shock_proximity_score" in out.columns else pd.Series(0.0, index=out.index),
    errors="coerce",).fillna(0.0) * 0.9
    
    score += pd.to_numeric(
    out["keyword_relevance_score"] if "keyword_relevance_score" in out.columns else pd.Series(0.0, index=out.index),
    errors="coerce",).fillna(0.0).clip(0, 10) * 0.18

    out["severity_score_1_to_10"] = score.clip(1, 10).round(2)
    out["severity_bucket"] = out["severity_score_1_to_10"].map(_severity_bucket)

    direction = out.get("expected_wti_bias", pd.Series("", index=out.index)).map(sign_bias_to_score).fillna(0.0)
    out["direction_score_m1_to_p1"] = direction

    realized_dir = pd.Series(
    np.sign(
        pd.to_numeric(
            out["wti_ret_4h_pct"] if "wti_ret_4h_pct" in out.columns else pd.Series(0.0, index=out.index),
            errors="coerce",
        ).fillna(0.0)
    ),
    index=out.index,
    dtype="float64",)
    realized_strength = pd.to_numeric(
        out["wti_reaction_strength_score_1_to_5"] if "wti_reaction_strength_score_1_to_5" in out.columns else pd.Series(0.0, index=out.index),
    errors="coerce",).fillna(0.0)


    absurd = (
        (direction != 0) &
        (realized_dir != 0) &
        (direction != realized_dir) &
        (realized_strength >= 2)
    )
    out["absurdity_score_1_to_5"] = np.where(absurd, np.minimum(5, realized_strength + 1), np.where(direction == 0, 2, 1))
    out["reaction_direction_label"] = realized_dir.map({
    1.0: "bullish",
    -1.0: "bearish",
    0.0: "neutral",}).fillna("neutral")

    out = out.sort_values(["trade_date_ist", "event_datetime_ist", "event_id"]).reset_index(drop=True)
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


def build_news_severity_day_features(
    event_severity: pd.DataFrame,
    news_day_rollup: pd.DataFrame,
    daily_master: pd.DataFrame,
    day_window_matrix: pd.DataFrame,
) -> pd.DataFrame:
    if daily_master.empty:
        return pd.DataFrame()

    ev = event_severity.copy()
    rp = news_day_rollup.copy()
    dm = daily_master.copy()
    mx = day_window_matrix.copy()

    ev["trade_date_ist"] = parse_date_series(ev["trade_date_ist"])
    rp["trade_date_ist"] = parse_date_series(rp["trade_date_ist"])
    dm["trade_date_ist"] = parse_date_series(dm["trade_date_ist"])
    if not mx.empty:
        mx["trade_date_ist"] = parse_date_series(mx["trade_date_ist"])

    rows = []
    for d in sorted(dm["trade_date_ist"].dropna().unique().tolist()):
        g = ev[ev["trade_date_ist"].eq(d)].copy()
        mx_row = mx[mx["trade_date_ist"].eq(d)].copy() if not mx.empty else pd.DataFrame()

        if g.empty:
            rows.append({
                "trade_date_ist": d,
                "event_count": 0,
                "verified_event_count": 0,
                "severity_score_1_to_10": 1.0,
                "severity_bucket": "very_low",
                "direction_score_m1_to_p1": 0.0,
                "ambiguity_score_1_to_10": 1.0,
                "absurdity_score_1_to_5": 1.0,
                "dominant_event_type": "no_major_catalyst",
                "dominant_event_session_window_ist": "",
                "dominant_headline": "",
                "dominant_source_url": "",
                "news_regime_label": "none_material",
                "window_pressure_label": "",
            })
            continue

        sev = pd.to_numeric(g["severity_score_1_to_10"], errors="coerce").fillna(0.0)
        dirs = pd.to_numeric(g["direction_score_m1_to_p1"], errors="coerce").fillna(0.0)
        absurd = pd.to_numeric(g["absurdity_score_1_to_5"], errors="coerce").fillna(1.0)

        weighted_dir = np.average(dirs, weights=np.maximum(sev, 0.1)) if len(g) else 0.0
        pos_mass = sev[dirs > 0].sum()
        neg_mass = sev[dirs < 0].sum()

        ambiguity = 1.0
        if (pos_mass + neg_mass) > 0:
            ambiguity = 1.0 + 9.0 * (min(pos_mass, neg_mass) / max(pos_mass + neg_mass, 1e-9))

        dominant = g.sort_values(
            ["severity_score_1_to_10", "absurdity_score_1_to_5", "event_datetime_ist"],
            ascending=[False, False, True]
        ).iloc[0]

        if weighted_dir > 0.20:
            regime = "hard_threat"
        elif weighted_dir < -0.20:
            regime = "de_escalation"
        elif ambiguity >= 4:
            regime = "mixed_signals"
        else:
            regime = "none_material"

        window_pressure = ""
        if not mx_row.empty and "strongest_window_of_day" in mx_row.columns:
            window_pressure = str(mx_row["strongest_window_of_day"].iloc[0] or "")

        rows.append({
            "trade_date_ist": d,
            "event_count": int(len(g)),
            "verified_event_count": int(g["source_url"].fillna("").astype(str).str.len().gt(0).sum()),
            "severity_score_1_to_10": round(float(sev.max()), 2),
            "severity_bucket": _severity_bucket(float(sev.max())),
            "direction_score_m1_to_p1": round(float(weighted_dir), 3),
            "ambiguity_score_1_to_10": round(float(ambiguity), 2),
            "absurdity_score_1_to_5": round(float(absurd.max()), 2),
            "dominant_event_type": str(dominant.get("event_type", "")),
            "dominant_event_session_window_ist": str(dominant.get("event_session_window_ist", "")),
            "dominant_headline": str(dominant.get("headline", "")),
            "dominant_source_url": str(dominant.get("source_url", "")),
            "news_regime_label": regime,
            "window_pressure_label": window_pressure,
        })

    out = pd.DataFrame(rows).sort_values("trade_date_ist").reset_index(drop=True)
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out

def build_event_reaction_profiles(
    event_severity: pd.DataFrame,
    wti_intraday: pd.DataFrame,
    brent_intraday: pd.DataFrame,
) -> pd.DataFrame:
    if event_severity.empty:
        return pd.DataFrame()

    ev = event_severity.copy()
    ev["trade_date_ist"] = parse_date_series(ev["trade_date_ist"])
    ev["event_datetime_ist"] = parse_dt_series(ev["event_datetime_ist"])

    rows = []
    for product, intraday in [("WTI", wti_intraday), ("BRENT", brent_intraday)]:
        if intraday.empty:
            continue

        intraday = intraday.copy()
        intraday["trade_date_ist"] = parse_date_series(intraday["trade_date_ist"])
        intraday["timestamp_ist"] = parse_dt_series(intraday["timestamp_ist"])
        ns = _price_namespace(intraday)

        for _, e in ev.iterrows():
            day = intraday[intraday["trade_date_ist"].eq(e["trade_date_ist"])].sort_values("timestamp_ist").copy()
            if day.empty:
                continue

            open_col = _col(ns, "open")
            high_col = _col(ns, "high")
            low_col = _col(ns, "low")
            close_col = _col(ns, "close")

            after = day[day["timestamp_ist"] >= e["event_datetime_ist"]].copy()
            if after.empty:
                after = day.copy()

            entry = after.iloc[0]
            entry_ts = entry["timestamp_ist"]
            entry_px = to_float_scalar(entry.get(open_col))
            if pd.isna(entry_px):
                continue

            row = {
                "event_id": e["event_id"],
                "trade_date_ist": e["trade_date_ist"],
                "product": product,
                "event_type": e.get("event_type", ""),
                "severity_bucket": e.get("severity_bucket", "unknown"),
                "severity_score_1_to_10": e.get("severity_score_1_to_10", np.nan),
                "direction_score_m1_to_p1": e.get("direction_score_m1_to_p1", np.nan),
                "absurdity_score_1_to_5": e.get("absurdity_score_1_to_5", np.nan),
                "event_session_window_ist": resolve_session_window_from_row(entry),
                "entry_ts": entry_ts,
                "entry_price": entry_px,
                "unit_label": ns,
            }

            for hz in REACTION_HORIZONS_MINUTES:
                sl = _window_slice(day, entry_ts, hz)
                if sl.empty:
                    row[f"ret_{hz}m_pct"] = np.nan
                    row[f"mfe_{hz}m_points"] = np.nan
                    row[f"mae_{hz}m_points"] = np.nan
                    continue

                close_px = to_float_scalar(sl[close_col].iloc[-1])
                high_px = float(_numeric_col(sl, high_col).max())
                low_px = float(_numeric_col(sl, low_col).min())

                row[f"ret_{hz}m_pct"] = pct_change(close_px, entry_px)
                row[f"mfe_{hz}m_points"] = high_px - entry_px
                row[f"mae_{hz}m_points"] = low_px - entry_px

            rows.append(row)

    out = pd.DataFrame(rows).sort_values(["trade_date_ist", "event_id", "product"]).reset_index(drop=True)
    if not out.empty:
        out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


def build_event_pattern_library(event_profiles: pd.DataFrame, min_obs: int = 3) -> pd.DataFrame:
    if event_profiles.empty:
        return pd.DataFrame()

    grp_cols = ["product", "event_type", "severity_bucket", "event_session_window_ist"]
    rows = []

    for key, g in event_profiles.groupby(grp_cols, dropna=False):
        if len(g) < min_obs:
            continue

        row = dict(zip(grp_cols, key))
        row["obs_count"] = int(len(g))
        row["median_severity_score_1_to_10"] = pd.to_numeric(g["severity_score_1_to_10"], errors="coerce").median()
        row["median_absurdity_score_1_to_5"] = pd.to_numeric(g["absurdity_score_1_to_5"], errors="coerce").median()

        for hz in REACTION_HORIZONS_MINUTES:
            ret_col = f"ret_{hz}m_pct"
            mfe_col = f"mfe_{hz}m_points"
            mae_col = f"mae_{hz}m_points"
            row[f"median_{ret_col}"] = pd.to_numeric(g[ret_col], errors="coerce").median()
            row[f"q25_{ret_col}"] = pd.to_numeric(g[ret_col], errors="coerce").quantile(0.25)
            row[f"q75_{ret_col}"] = pd.to_numeric(g[ret_col], errors="coerce").quantile(0.75)
            row[f"median_{mfe_col}"] = pd.to_numeric(g[mfe_col], errors="coerce").median()
            row[f"median_{mae_col}"] = pd.to_numeric(g[mae_col], errors="coerce").median()

        r120_raw = row.get("median_ret_120m_pct")
        r120: float = to_float_scalar(r120_raw)
        row["expected_direction_template"] = _sign_label(r120)
        row["expected_move_strength_pct"] = abs(r120) if pd.notna(r120) else np.nan
        rows.append(row)

    return pd.DataFrame(rows).sort_values(grp_cols).reset_index(drop=True)


def build_technical_pattern_overlay(
    daily_master: pd.DataFrame,
    day_window_matrix: pd.DataFrame,
) -> pd.DataFrame:
    if daily_master.empty:
        return pd.DataFrame()

    dm = daily_master.copy()
    mx = day_window_matrix.copy()
    dm["trade_date_ist"] = parse_date_series(dm["trade_date_ist"])
    if not mx.empty:
        mx["trade_date_ist"] = parse_date_series(mx["trade_date_ist"])

    out = dm.merge(mx, how="left", on="trade_date_ist")
    rows = []

    for _, r in out.iterrows():
        gap = to_float_scalar(r.get("wti_gap_pct_native"))
        daily_ret = to_float_scalar(r.get("wti_net_day_return_pct"))
        eur = str(r.get("europe_open_direction", "")).upper()
        eur_mid = str(r.get("europe_mid_direction", "")).upper()
        us = str(r.get("us_open_direction", "")).upper()
        mcx_open = str(r.get("mcx_open_drive_direction", "")).upper()
        strongest = str(r.get("strongest_window_of_day", ""))

        tech_type = "mixed"
        tech_bias = "neutral"
        conviction = 2
        notes = ""

        if pd.notna(gap) and gap > 0 and eur == "UP" and us == "UP":
            tech_type, tech_bias, conviction, notes = "gap_follow_trend_up", "bullish", 4, "positive_gap_follow"
        elif pd.notna(gap) and gap < 0 and eur == "DOWN" and us == "DOWN":
            tech_type, tech_bias, conviction, notes = "gap_follow_trend_down", "bearish", 4, "negative_gap_follow"
        elif mcx_open == "UP" and eur == "DOWN" and us == "DOWN":
            tech_type, tech_bias, conviction, notes = "europe_reversal_down", "bearish", 4, "early_strength_failed"
        elif mcx_open == "DOWN" and eur == "UP" and us == "UP":
            tech_type, tech_bias, conviction, notes = "europe_reversal_up", "bullish", 4, "early_weakness_failed"
        elif eur_mid == us and eur_mid in {"UP", "DOWN"}:
            tech_type = "us_continuation_up" if us == "UP" else "us_continuation_down"
            tech_bias = "bullish" if us == "UP" else "bearish"
            conviction = 3
            notes = "us_extended_europe"
        elif strongest in {"europe_open", "europe_mid", "us_open"} and pd.notna(daily_ret) and abs(daily_ret) < 0.6:
            tech_type, tech_bias, conviction, notes = "range_compression", "neutral", 2, "push_but_flat_close"
        elif pd.notna(daily_ret) and daily_ret > 0:
            tech_type, tech_bias, conviction, notes = "close_strength_up", "bullish", 2, "green_close"
        elif pd.notna(daily_ret) and daily_ret < 0:
            tech_type, tech_bias, conviction, notes = "close_strength_down", "bearish", 2, "red_close"

        rows.append({
            "trade_date_ist": r["trade_date_ist"],
            "technical_overlay_type": tech_type,
            "technical_direction_bias": tech_bias,
            "technical_conviction_score_1_to_5": conviction,
            "technical_control_window": strongest,
            "technical_notes_short": notes,
        })

    out = pd.DataFrame(rows).sort_values("trade_date_ist").reset_index(drop=True)
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


def build_pattern_mode_daily(
    news_severity: pd.DataFrame,
    technical_overlay: pd.DataFrame,
    day_labels: pd.DataFrame,
    deviations: pd.DataFrame,
) -> pd.DataFrame:
    ns = news_severity.copy()
    te = technical_overlay.copy()
    dl = day_labels.copy()
    dv = deviations.copy()

    for df in [ns, te, dl, dv]:
        if not df.empty and "trade_date_ist" in df.columns:
            df["trade_date_ist"] = parse_date_series(df["trade_date_ist"])

    out = ns.merge(te, how="outer", on="trade_date_ist")
    if not dl.empty and "price_path_bucket_primary" in dl.columns:
        out = out.merge(dl[["trade_date_ist", "price_path_bucket_primary"]], how="left", on="trade_date_ist")
    if not dv.empty and "deviation_flag" in dv.columns:
        out = out.merge(dv[["trade_date_ist", "deviation_flag"]], how="left", on="trade_date_ist")

    rows = []
    for _, r in out.iterrows():
        sev = to_float_scalar(r.get("severity_score_1_to_10"))
        absurd = to_float_scalar(r.get("absurdity_score_1_to_5"))
        amb = to_float_scalar(r.get("ambiguity_score_1_to_10"))
        tech_conv = to_float_scalar(r.get("technical_conviction_score_1_to_5"))
        dev = boolize(r.get("deviation_flag"))

        mode = "mixed_or_unresolved"
        alt = ""
        why = ""

        if pd.notna(sev) and sev >= 7 and pd.notna(absurd) and absurd >= 3 and (pd.isna(tech_conv) or tech_conv <= 2):
            mode, alt, why = "news_absurd_pattern", "technical_overlay_failed", "strong_news_nonconventional_path"
        elif pd.notna(sev) and sev >= 6 and pd.notna(tech_conv) and tech_conv >= 3:
            mode, alt, why = "news_plus_technical_overlay", "news_absurd_pattern" if absurd >= 3 else "technical_only", "news_and_session_pattern_aligned"
        elif (pd.isna(sev) or sev < 5) and pd.notna(tech_conv) and tech_conv >= 3:
            mode, alt, why = "technical_only", "news_plus_technical_overlay", "low_news_pressure_repeatable_price_structure"
        elif pd.notna(amb) and amb >= 5:
            mode, alt, why = "mixed_signal_whipsaw", "news_absurd_pattern", "competing_headlines_high_ambiguity"

        if dev and mode == "technical_only":
            alt = "news_absurd_pattern"

        rows.append({
            "trade_date_ist": r["trade_date_ist"],
            "dominant_pattern_mode": mode,
            "alternate_pattern_mode_if_any": alt,
            "technical_overlay_type": r.get("technical_overlay_type", ""),
            "technical_direction_bias": r.get("technical_direction_bias", ""),
            "news_absurdity_score_1_to_5": absurd,
            "pattern_mode_reason_short": why,
        })

    out = pd.DataFrame(rows).sort_values("trade_date_ist").reset_index(drop=True)
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


def _evaluate_trade_path(
    day_df: pd.DataFrame,
    entry_ts: pd.Timestamp,
    direction: str,
    entry_price: float,
    stop_price: float,
    target_1r: float,
    target_2r: float,
    target_3r: float,
    unit_label: str,
) -> dict:
    blank = {
        "exit_ts": pd.NaT,
        "exit_price": np.nan,
        "exit_reason": "",
        "pnl_points": np.nan,
        "risk_points": np.nan,
        "pnl_r": np.nan,
        "mfe_points": np.nan,
        "mae_points": np.nan,
        "time_to_mfe_minutes": np.nan,
        "time_to_mae_minutes": np.nan,
        "hit_1r": False,
        "hit_2r": False,
        "hit_3r": False,
        "time_to_1r_minutes": np.nan,
        "time_to_2r_minutes": np.nan,
        "time_to_3r_minutes": np.nan,
        "unit_label": unit_label,
    }
    if day_df.empty or pd.isna(entry_ts) or pd.isna(entry_price) or pd.isna(stop_price):
        return blank

    future = day_df[day_df["timestamp_ist"] >= entry_ts].sort_values("timestamp_ist").copy()
    if future.empty:
        return blank

    ns = "inr" if unit_label == "inr" else "native"
    hi = _numeric_col(future, _col(ns, "high"))
    lo = _numeric_col(future, _col(ns, "low"))
    cl = _numeric_col(future, _col(ns, "close"))
    ts = future["timestamp_ist"]

    risk = abs(entry_price - stop_price)
    if pd.isna(risk) or risk <= 0:
        return blank

    if direction == "long":
        mfe_series = hi - entry_price
        mae_series = lo - entry_price
        hit1 = hi >= target_1r
        hit2 = hi >= target_2r
        hit3 = hi >= target_3r
    else:
        mfe_series = entry_price - lo
        mae_series = entry_price - hi
        hit1 = lo <= target_1r
        hit2 = lo <= target_2r
        hit3 = lo <= target_3r

    hit_1r = bool(hit1.fillna(False).any())
    hit_2r = bool(hit2.fillna(False).any())
    hit_3r = bool(hit3.fillna(False).any())

    time_to_1r = _trade_minutes(entry_ts, ts.loc[hit1.fillna(False)].iloc[0]) if hit_1r else np.nan
    time_to_2r = _trade_minutes(entry_ts, ts.loc[hit2.fillna(False)].iloc[0]) if hit_2r else np.nan
    time_to_3r = _trade_minutes(entry_ts, ts.loc[hit3.fillna(False)].iloc[0]) if hit_3r else np.nan

    mfe_points = float(mfe_series.max()) if not mfe_series.empty else np.nan
    mae_points = float(mae_series.min()) if not mae_series.empty else np.nan

    mfe_idx = mfe_series.idxmax() if mfe_series.notna().any() else None
    mae_idx = mae_series.idxmin() if mae_series.notna().any() else None

    time_to_mfe = _trade_minutes(entry_ts, future.loc[mfe_idx, "timestamp_ist"]) if mfe_idx is not None else np.nan
    time_to_mae = _trade_minutes(entry_ts, future.loc[mae_idx, "timestamp_ist"]) if mae_idx is not None else np.nan

    exit_ts = pd.NaT
    exit_price = np.nan
    exit_reason = ""

    for i in future.index:
        row_hi = hi.loc[i]
        row_lo = lo.loc[i]
        row_ts = future.loc[i, "timestamp_ist"]

        if direction == "long":
            if pd.notna(row_lo) and row_lo <= stop_price:
                exit_ts, exit_price, exit_reason = row_ts, stop_price, "stop"
                break
            if pd.notna(row_hi) and row_hi >= target_2r:
                exit_ts, exit_price, exit_reason = row_ts, target_2r, "target_2r"
                break
        else:
            if pd.notna(row_hi) and row_hi >= stop_price:
                exit_ts, exit_price, exit_reason = row_ts, stop_price, "stop"
                break
            if pd.notna(row_lo) and row_lo <= target_2r:
                exit_ts, exit_price, exit_reason = row_ts, target_2r, "target_2r"
                break

    if pd.isna(exit_ts):
        exit_ts = future["timestamp_ist"].iloc[-1]
        exit_price = cl.iloc[-1]
        exit_reason = "day_close"

    pnl_points = (exit_price - entry_price) if direction == "long" else (entry_price - exit_price)
    pnl_r = pnl_points / risk if pd.notna(risk) and risk != 0 else np.nan

    return {
        "exit_ts": exit_ts,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "pnl_points": pnl_points,
        "risk_points": risk,
        "pnl_r": pnl_r,
        "mfe_points": mfe_points,
        "mae_points": mae_points,
        "time_to_mfe_minutes": time_to_mfe,
        "time_to_mae_minutes": time_to_mae,
        "hit_1r": hit_1r,
        "hit_2r": hit_2r,
        "hit_3r": hit_3r,
        "time_to_1r_minutes": time_to_1r,
        "time_to_2r_minutes": time_to_2r,
        "time_to_3r_minutes": time_to_3r,
        "unit_label": unit_label,
    }


def build_setup_backtests_detailed(
    wti_intraday: pd.DataFrame,
    brent_intraday: pd.DataFrame,
    news_day_rollup: pd.DataFrame,
    news_severity: pd.DataFrame,
    technical_overlay: pd.DataFrame,
    pattern_mode_daily: pd.DataFrame,
) -> pd.DataFrame:
    rp = news_day_rollup.copy()
    ns = news_severity.copy()
    te = technical_overlay.copy()
    pm = pattern_mode_daily.copy()

    for df in [rp, ns, te, pm]:
        if not df.empty and "trade_date_ist" in df.columns:
            df["trade_date_ist"] = parse_date_series(df["trade_date_ist"])

    day_meta = rp.merge(ns, how="outer", on="trade_date_ist").merge(te, how="left", on="trade_date_ist").merge(pm, how="left", on="trade_date_ist")

    rows = []
    for product, intraday in [("WTI", wti_intraday), ("BRENT", brent_intraday)]:
        if intraday.empty:
            continue

        intraday = intraday.copy()
        intraday["trade_date_ist"] = parse_date_series(intraday["trade_date_ist"])
        intraday["timestamp_ist"] = parse_dt_series(intraday["timestamp_ist"])
        unit_label = _price_namespace(intraday)

        for d, day in intraday.groupby("trade_date_ist"):
            meta = day_meta[day_meta["trade_date_ist"].eq(d)]
            meta_row = meta.iloc[0] if not meta.empty else pd.Series(dtype="object")
            day = day.sort_values("timestamp_ist").copy()

            first_eur = _first_bar_in_window(day, "europe_open")
            first_us = _first_bar_in_window(day, "us_open")
            setups = []

            direction_score = to_float_scalar(meta_row.get("direction_score_m1_to_p1"))
            severity_score = to_float_scalar(meta_row.get("severity_score_1_to_10"))
            pattern_mode = str(meta_row.get("dominant_pattern_mode", ""))

            if pd.notna(direction_score) and abs(direction_score) >= 0.25 and pd.notna(severity_score) and severity_score >= 5:
                anchor_bar = first_eur if first_eur is not None else first_us
                if anchor_bar is not None:
                    o = to_float_scalar(anchor_bar.get(_col(unit_label, "open")))
                    h = to_float_scalar(anchor_bar.get(_col(unit_label, "high")))
                    l = to_float_scalar(anchor_bar.get(_col(unit_label, "low")))
                    direction = "long" if direction_score > 0 else "short"

                    if direction == "long":
                        stop = l
                        risk = o - stop if pd.notna(o) and pd.notna(stop) else np.nan
                        t1, t2, t3 = o + risk, o + 2 * risk, o + 3 * risk
                    else:
                        stop = h
                        risk = stop - o if pd.notna(o) and pd.notna(stop) else np.nan
                        t1, t2, t3 = o - risk, o - 2 * risk, o - 3 * risk

                    if pd.notna(risk) and risk > 0:
                        setups.append(("event_followthrough",anchor_bar,anchor_bar["timestamp_ist"],direction,o,stop,t1,t2,t3,"severity_direction",))

            for setup_name, anchor in [("europe_open_continuation", first_eur), ("us_open_continuation", first_us)]:
                if anchor is None:
                    continue

                o = to_float_scalar(anchor.get(_col(unit_label, "open")))
                c = to_float_scalar(anchor.get(_col(unit_label, "close")))
                h = to_float_scalar(anchor.get(_col(unit_label, "high")))
                l = to_float_scalar(anchor.get(_col(unit_label, "low")))

                if pd.notna(o) and pd.notna(c) and pd.notna(h) and pd.notna(l) and h > l:
                    direction = "long" if c > o else "short"
                    risk = abs(o - l) if direction == "long" else abs(h - o)
                    if risk > 0:
                        stop = l if direction == "long" else h
                        t1 = o + risk if direction == "long" else o - risk
                        t2 = o + 2 * risk if direction == "long" else o - 2 * risk
                        t3 = o + 3 * risk if direction == "long" else o - 3 * risk
                        setups.append((setup_name,anchor,anchor["timestamp_ist"],direction,o,stop,t1,t2,t3,"first_bar_direction",))

            for setup_name, anchor_row, entry_ts, direction, entry_px, stop_px, t1, t2, t3, trigger_basis in setups:
                sim = _evaluate_trade_path(day, entry_ts, direction, entry_px, stop_px, t1, t2, t3, unit_label)
                rows.append({
        "trade_date_ist": d,
        "product": product,
        "setup_name": setup_name,
        "dominant_pattern_mode": pattern_mode,
        "trigger_basis": trigger_basis,
        "entry_window": resolve_session_window_from_row(anchor_row),
        "entry_ts": entry_ts,
        "direction": direction,
        "unit_label": unit_label,
        "entry_price": entry_px,
        "stop_price": stop_px,
        "target_1r": t1,
        "target_2r": t2,
        "target_3r": t3,
        "severity_score_1_to_10": severity_score,
        "direction_score_m1_to_p1": direction_score,
        "technical_overlay_type": meta_row.get("technical_overlay_type", ""),
        "technical_direction_bias": meta_row.get("technical_direction_bias", ""),
        "news_regime_label": meta_row.get("news_regime_label", ""),
        **sim,})

    out = pd.DataFrame(rows).sort_values(["trade_date_ist", "product", "setup_name"]).reset_index(drop=True)
    if not out.empty:
        out["trade_date_ist"] = out["trade_date_ist"].astype(str)
        out["win_flag"] = out["pnl_points"] > 0
    return out


def build_walk_forward_validation(
    setup_backtests: pd.DataFrame,
    train_min_days: int = MIN_TRAIN_DAYS_WALK_FORWARD,
    min_obs_per_setup: int = MIN_SETUP_OBS_WALK_FORWARD,
) -> pd.DataFrame:
    if setup_backtests.empty:
        return pd.DataFrame()

    sb = setup_backtests.copy()
    sb["trade_date_ist"] = parse_date_series(sb["trade_date_ist"])
    unique_dates = sorted(sb["trade_date_ist"].dropna().unique().tolist())
    rows = []

    for i, current_date in enumerate(unique_dates):
        train_dates = unique_dates[:i]
        if len(train_dates) < train_min_days:
            continue

        train = sb[sb["trade_date_ist"].isin(train_dates)].copy()
        test = sb[sb["trade_date_ist"].eq(current_date)].copy()

        for _, cand in test.iterrows():
            hist = train[
                train["setup_name"].eq(cand["setup_name"]) &
                train["product"].eq(cand["product"]) &
                train["dominant_pattern_mode"].eq(cand["dominant_pattern_mode"])
            ].copy()

            if len(hist) < min_obs_per_setup:
                hist = train[
                    train["setup_name"].eq(cand["setup_name"]) &
                    train["product"].eq(cand["product"])
                ].copy()

            obs = len(hist)
            if obs == 0:
                continue

            avg_pnl = pd.to_numeric(hist["pnl_points"], errors="coerce").mean()
            med_pnl = pd.to_numeric(hist["pnl_points"], errors="coerce").median()
            avg_r = pd.to_numeric(hist["pnl_r"], errors="coerce").mean()
            win_rate = hist["win_flag"].fillna(False).mean()
            hit_1r = hist["hit_1r"].fillna(False).mean()
            hit_2r = hist["hit_2r"].fillna(False).mean()
            avg_mfe = pd.to_numeric(hist["mfe_points"], errors="coerce").mean()
            avg_mae = pd.to_numeric(hist["mae_points"], errors="coerce").mean()
            edge = (avg_pnl / abs(avg_mae)) if pd.notna(avg_pnl) and pd.notna(avg_mae) and avg_mae != 0 else np.nan

            rows.append({
                "trade_date_ist": current_date,
                "product": cand["product"],
                "setup_name": cand["setup_name"],
                "dominant_pattern_mode": cand["dominant_pattern_mode"],
                "train_obs": obs,
                "train_win_rate": win_rate,
                "train_hit_1r_rate": hit_1r,
                "train_hit_2r_rate": hit_2r,
                "train_avg_pnl_points": avg_pnl,
                "train_median_pnl_points": med_pnl,
                "train_avg_r": avg_r,
                "train_avg_mfe_points": avg_mfe,
                "train_avg_mae_points": avg_mae,
                "expected_edge_score": edge,
                "realized_pnl_points": cand["pnl_points"],
                "realized_pnl_r": cand["pnl_r"],
                "realized_win_flag": cand["win_flag"],
                "entry_window": cand["entry_window"],
                "direction": cand["direction"],
                "unit_label": cand["unit_label"],
            })

    out = pd.DataFrame(rows).sort_values(["trade_date_ist", "product", "expected_edge_score"], ascending=[True, True, False]).reset_index(drop=True)
    if out.empty:
        return out

    out["is_recommended_setup"] = False
    top_idx = out.groupby(["trade_date_ist", "product"]).head(1).index
    out.loc[top_idx, "is_recommended_setup"] = True
    out["trade_date_ist"] = out["trade_date_ist"].astype(str)
    return out


def build_predictive_scoring_v2(
    daily_master: pd.DataFrame,
    news_severity: pd.DataFrame,
    technical_overlay: pd.DataFrame,
    pattern_mode_daily: pd.DataFrame,
    walk_forward: pd.DataFrame,
) -> pd.DataFrame:
    dm = daily_master.copy()
    ns = news_severity.copy()
    te = technical_overlay.copy()
    pm = pattern_mode_daily.copy()
    wf = walk_forward.copy()

    for df in [dm, ns, te, pm]:
        if not df.empty:
            df["trade_date_ist"] = parse_date_series(df["trade_date_ist"])
    if not wf.empty:
        wf["trade_date_ist"] = parse_date_series(wf["trade_date_ist"])

    best = wf[wf["is_recommended_setup"].fillna(False)].copy() if not wf.empty else pd.DataFrame(columns=["trade_date_ist"])

    out = dm.merge(ns, how="left", on="trade_date_ist").merge(te, how="left", on="trade_date_ist").merge(pm, how="left", on="trade_date_ist")
    if not best.empty:
        out = out.merge(
            best[[
                "trade_date_ist", "product", "setup_name", "train_obs", "train_win_rate",
                "train_hit_1r_rate", "train_hit_2r_rate", "train_avg_pnl_points",
                "train_avg_r", "expected_edge_score", "entry_window", "direction", "unit_label"
            ]],
            how="left",
            on="trade_date_ist"
        )

    rows = []
    for _, r in out.iterrows():
        sev = to_float_scalar(r.get("severity_score_1_to_10"))
        amb = to_float_scalar(r.get("ambiguity_score_1_to_10"))
        tech_conv = to_float_scalar(r.get("technical_conviction_score_1_to_5"))
        edge = to_float_scalar(r.get("expected_edge_score"))
        direction_score = to_float_scalar(r.get("direction_score_m1_to_p1"))
        pred_bias = _sign_label(direction_score)

        conf = 1
        if pd.notna(edge) and edge > 0.75:
            conf += 2
        elif pd.notna(edge) and edge > 0.25:
            conf += 1
        if pd.notna(sev) and sev >= 7:
            conf += 1
        if pd.notna(tech_conv) and tech_conv >= 4:
            conf += 1
        if pd.notna(amb) and amb >= 5:
            conf -= 1
        conf = max(1, min(5, conf))

        rows.append({
            "trade_date_ist": r["trade_date_ist"],
            "dominant_pattern_mode": r.get("dominant_pattern_mode", ""),
            "predicted_directional_bias": pred_bias,
            "predicted_setup_name": r.get("setup_name", ""),
            "predicted_entry_window": r.get("entry_window", ""),
            "predicted_trade_direction": r.get("direction", ""),
            "expected_edge_score": edge,
            "expected_move_points": r.get("train_avg_pnl_points", np.nan),
            "expected_r_multiple": r.get("train_avg_r", np.nan),
            "prediction_confidence_1_to_5": conf,
            "news_regime_label": r.get("news_regime_label", ""),
            "technical_overlay_type": r.get("technical_overlay_type", ""),
            "unit_label": r.get("unit_label", ""),
        })

    pred = pd.DataFrame(rows).sort_values("trade_date_ist").reset_index(drop=True)
    pred["trade_date_ist"] = pred["trade_date_ist"].astype(str)
    return pred


def build_decision_engine_v2(
    predictive: pd.DataFrame,
    pattern_mode_daily: pd.DataFrame,
) -> pd.DataFrame:
    pr = predictive.copy()
    pm = pattern_mode_daily.copy()

    for df in [pr, pm]:
        if not df.empty:
            df["trade_date_ist"] = parse_date_series(df["trade_date_ist"])

    out = pr.merge(pm, how="left", on="trade_date_ist", suffixes=("", "_pm"))
    rows = []

    for _, r in out.iterrows():
        mode = str(r.get("dominant_pattern_mode", ""))
        conf = int(to_float_scalar(r.get("prediction_confidence_1_to_5")) or 1)
        setup = str(r.get("predicted_setup_name", ""))
        bias = str(r.get("predicted_trade_direction", ""))
        entry_window = str(r.get("predicted_entry_window", ""))
        edge = to_float_scalar(r.get("expected_edge_score"))

        trade_bias = "flat"
        sizing = "skip"
        validation_rule = "wait"
        invalidation_rule = "skip_on_conflict"
        notes = ""

        if mode == "news_absurd_pattern":
            trade_bias, sizing, validation_rule, invalidation_rule, notes = "small_probe_only", "small", "confirm_absurd_move_first", "abort_on_reclaim", "nonconventional_news_day"
        elif mode == "news_plus_technical_overlay":
            trade_bias, sizing, validation_rule, invalidation_rule, notes = (bias if bias in {"long", "short"} else "follow_confirmed_bias"), "medium", "take_only_if_news_and_price_align", "abort_if_control_window_breaks", "best_structured_mode"
        elif mode == "technical_only":
            trade_bias, sizing, validation_rule, invalidation_rule, notes = (bias if bias in {"long", "short"} else "range_or_breakout"), "small", "technical_trigger_only", "abort_on_live_news_conflict", "pure_price_structure_day"
        else:
            trade_bias, sizing, validation_rule, invalidation_rule, notes = "flat", "skip", "wait_for_clarity", "do_not_force_trade", "mixed_or_low_edge_day"

        if pd.notna(edge) and edge < 0:
            trade_bias, sizing, notes = "flat", "skip", "historical_edge_negative"

        rows.append({
            "trade_date_ist": r["trade_date_ist"],
            "dominant_pattern_mode": mode,
            "recommended_setup_name": setup,
            "recommended_trade_bias": trade_bias,
            "entry_window": entry_window,
            "prediction_confidence_1_to_5": conf,
            "expected_edge_score": edge,
            "expected_move_points": r.get("expected_move_points", np.nan),
            "expected_r_multiple": r.get("expected_r_multiple", np.nan),
            "sizing_bucket": sizing,
            "validation_rule": validation_rule,
            "invalidation_rule": invalidation_rule,
            "notes": notes,
        })

    eng = pd.DataFrame(rows).sort_values("trade_date_ist").reset_index(drop=True)
    eng["trade_date_ist"] = eng["trade_date_ist"].astype(str)
    return eng


def build_trade_planning_templates(setup_backtests: pd.DataFrame) -> pd.DataFrame:
    if setup_backtests.empty:
        return pd.DataFrame()

    sb = setup_backtests.copy()
    sb["trade_date_ist"] = parse_date_series(sb["trade_date_ist"])

    rows = []
    grp_cols = ["product", "dominant_pattern_mode", "setup_name", "direction", "entry_window", "unit_label"]
    for key, g in sb.groupby(grp_cols, dropna=False):
        row = dict(zip(grp_cols, key))
        row["obs_count"] = int(len(g))
        row["win_rate"] = g["win_flag"].fillna(False).mean()
        row["hit_1r_rate"] = g["hit_1r"].fillna(False).mean()
        row["hit_2r_rate"] = g["hit_2r"].fillna(False).mean()
        row["median_pnl_points"] = pd.to_numeric(g["pnl_points"], errors="coerce").median()
        row["avg_pnl_points"] = pd.to_numeric(g["pnl_points"], errors="coerce").mean()
        row["median_risk_points"] = pd.to_numeric(g["risk_points"], errors="coerce").median()
        row["median_mfe_points"] = pd.to_numeric(g["mfe_points"], errors="coerce").median()
        row["median_mae_points"] = pd.to_numeric(g["mae_points"], errors="coerce").median()
        row["median_time_to_1r_minutes"] = pd.to_numeric(g["time_to_1r_minutes"], errors="coerce").median()
        row["median_time_to_2r_minutes"] = pd.to_numeric(g["time_to_2r_minutes"], errors="coerce").median()
        rows.append(row)

    return pd.DataFrame(rows).sort_values(["product", "dominant_pattern_mode", "setup_name"]).reset_index(drop=True)


# ============================================================
# MAIN
# ============================================================

def main():
    phase1 = load_phase1()

    daily_master = phase1["daily_master"]
    day_labels = phase1["day_labels"]
    deviations = phase1["deviations"]
    day_window_matrix = phase1["day_window_matrix"]
    arche = phase1["arche"]

    if daily_master.empty or "trade_date_ist" not in daily_master.columns:
        raise RuntimeError("daily_master_summary.xlsx is missing or empty. Run phase 1 first.")

    wti_intraday_ctx = resolve_intraday_source(phase1["wti_5m"], phase1["wti_15m"], phase1["wti_60m"], product="WTI")
    brent_intraday_ctx = resolve_intraday_source(phase1["brent_5m"], phase1["brent_15m"], phase1["brent_60m"], product="BRENT")
    
    wti_intraday = wti_intraday_ctx["bars"]
    brent_intraday = brent_intraday_ctx["bars"]

    trade_dates = sorted(pd.Series(daily_master["trade_date_ist"]).dropna().unique().tolist())

    wti_intraday_ctx = build_analysis_intraday_context(phase1["wti_5m"], phase1["wti_15m"], phase1["wti_60m"], product="WTI")
    brent_intraday_ctx = build_analysis_intraday_context(phase1["brent_5m"], phase1["brent_15m"], phase1["brent_60m"], product="BRENT")
    
    shock_windows = build_intraday_shock_windows(wti_intraday_ctx=wti_intraday_ctx,brent_intraday_ctx=brent_intraday_ctx,)
    write_output_table(shock_windows, "intraday_shock_windows.xlsx")

    raw_news = load_raw_news(trade_dates)
    write_output_table(raw_news, "news_raw_candidates.csv")
    write_output_table(raw_news, "news_raw_candidates.xlsx")
    print(f"[NEWS] raw_news rows entering build_news_master = {len(raw_news)}")
    
    news_master = build_news_master(trade_dates, raw_news, shock_windows)
    write_output_table(news_master, "news_events_master.xlsx")
    
    news_master = build_news_master(trade_dates, raw_news, shock_windows)
    write_output_table(news_master, "news_events_master.xlsx")

    news_quality_diag = build_news_quality_diagnostics(news_master, trade_dates)
    write_output_table(news_quality_diag, "news_quality_diagnostics.xlsx")
    enforce_news_quality_gate(news_quality_diag)

    reaction_matrix = build_news_reaction_matrix(news_master=news_master, wti_intraday_ctx=wti_intraday_ctx, brent_intraday_ctx=brent_intraday_ctx,)
    write_output_table(reaction_matrix, "news_reaction_matrix.xlsx")

    news_day_rollup = build_news_day_rollup(news_master, reaction_matrix, trade_dates)
    write_output_table(news_day_rollup, "news_day_rollup.xlsx")

    event_severity = build_event_severity_features(news_master, reaction_matrix)
    write_output_table(event_severity, "event_severity_features.xlsx")

    news_severity = build_news_severity_day_features(
        event_severity=event_severity,
        news_day_rollup=news_day_rollup,
        daily_master=daily_master,
        day_window_matrix=day_window_matrix,
    )
    write_output_table(news_severity, "news_severity_day_features.xlsx")

    event_profiles = build_event_reaction_profiles(
        event_severity=event_severity,
        wti_intraday=wti_intraday,
        brent_intraday=brent_intraday,
    )
    write_output_table(event_profiles, "event_reaction_profiles.xlsx")

    event_pattern_library = build_event_pattern_library(event_profiles, min_obs=3)
    write_output_table(event_pattern_library, "event_pattern_library.xlsx")

    technical_overlay = build_technical_pattern_overlay(
        daily_master=daily_master,
        day_window_matrix=day_window_matrix,
    )
    write_output_table(technical_overlay, "technical_pattern_overlay.xlsx")

    pattern_mode_daily = build_pattern_mode_daily(
        news_severity=news_severity,
        technical_overlay=technical_overlay,
        day_labels=day_labels,
        deviations=deviations,
    )
    write_output_table(pattern_mode_daily, "pattern_mode_daily.xlsx")

    day_labels_enriched = enrich_day_type_labels(day_labels, deviations, news_day_rollup)
    if not day_labels_enriched.empty:
        day_labels_enriched = day_labels_enriched.merge(
            pattern_mode_daily[[
                "trade_date_ist",
                "dominant_pattern_mode",
                "alternate_pattern_mode_if_any",
                "technical_overlay_type",
                "news_absurdity_score_1_to_5",
                "pattern_mode_reason_short",
            ]],
            how="left",
            on="trade_date_ist",
        )
    write_output_table(day_labels_enriched, "day_type_labels.xlsx")

    deviations_enriched = enrich_deviation_labels(deviations, news_day_rollup)
    if not deviations_enriched.empty:
        deviations_enriched = deviations_enriched.merge(
            pattern_mode_daily[[
                "trade_date_ist",
                "dominant_pattern_mode",
                "alternate_pattern_mode_if_any",
            ]],
            how="left",
            on="trade_date_ist",
        )
    write_output_table(deviations_enriched, "deviation_pattern_labels.xlsx")

    day_window_matrix_enriched = enrich_day_window_matrix(day_window_matrix, news_day_rollup)
    if not day_window_matrix_enriched.empty:
        day_window_matrix_enriched = day_window_matrix_enriched.merge(
            pattern_mode_daily[["trade_date_ist", "dominant_pattern_mode"]],
            how="left",
            on="trade_date_ist",
        )
    write_output_table(day_window_matrix_enriched, "day_window_behavior_matrix.xlsx")

    arche_enriched = enrich_archetype_features(arche, day_labels_enriched, news_day_rollup, news_master)
    if not arche_enriched.empty:
        arche_enriched = arche_enriched.merge(
            news_severity[[
                "trade_date_ist",
                "severity_score_1_to_10",
                "ambiguity_score_1_to_10",
                "absurdity_score_1_to_5",
                "direction_score_m1_to_p1",
            ]],
            how="left",
            on="trade_date_ist",
        )
    write_output_table(arche_enriched, "archetype_similarity_features.xlsx")

    setup_backtests = build_setup_backtests_detailed(
        wti_intraday=wti_intraday,
        brent_intraday=brent_intraday,
        news_day_rollup=news_day_rollup,
        news_severity=news_severity,
        technical_overlay=technical_overlay,
        pattern_mode_daily=pattern_mode_daily,
    )
    write_output_table(setup_backtests, "setup_backtests_detailed.xlsx")

    walk_forward = build_walk_forward_validation(
        setup_backtests=setup_backtests,
        train_min_days=MIN_TRAIN_DAYS_WALK_FORWARD,
        min_obs_per_setup=MIN_SETUP_OBS_WALK_FORWARD,
    )
    write_output_table(walk_forward, "walk_forward_validation.xlsx")

    predictive = build_predictive_scoring_v2(
        daily_master=daily_master,
        news_severity=news_severity,
        technical_overlay=technical_overlay,
        pattern_mode_daily=pattern_mode_daily,
        walk_forward=walk_forward,
    )
    write_output_table(predictive, "predictive_scoring_features.xlsx")

    decision_engine = build_decision_engine_v2(
        predictive=predictive,
        pattern_mode_daily=pattern_mode_daily,
    )
    write_output_table(decision_engine, "decision_engine_daily.xlsx")

    trade_templates = build_trade_planning_templates(setup_backtests=setup_backtests)
    write_output_table(trade_templates, "trade_planning_templates.xlsx")

    news_flag_behavior_links = build_news_flag_behavior_links(
        news_master, reaction_matrix, daily_master, day_labels_enriched, news_day_rollup
    )
    write_output_table(news_flag_behavior_links, "news_flag_behavior_links.xlsx")

    report_md = build_trader_style_report(
        news_day_rollup,
        predictive,
        decision_engine,
        deviations_enriched,
    )
    (OUTPUT_DIR / "trader_style_report.md").write_text(report_md, encoding="utf-8")

    summary = pd.DataFrame([
        {"file": "intraday_shock_windows.xlsx", "rows": len(shock_windows)},
        {"file": "news_events_master.xlsx", "rows": len(news_master)},
        {"file": "news_quality_diagnostics.xlsx", "rows": len(news_quality_diag)},
        {"file": "news_reaction_matrix.xlsx", "rows": len(reaction_matrix)},
        {"file": "news_day_rollup.xlsx", "rows": len(news_day_rollup)},
        {"file": "event_severity_features.xlsx", "rows": len(event_severity)},
        {"file": "news_severity_day_features.xlsx", "rows": len(news_severity)},
        {"file": "event_reaction_profiles.xlsx", "rows": len(event_profiles)},
        {"file": "event_pattern_library.xlsx", "rows": len(event_pattern_library)},
        {"file": "technical_pattern_overlay.xlsx", "rows": len(technical_overlay)},
        {"file": "pattern_mode_daily.xlsx", "rows": len(pattern_mode_daily)},
        {"file": "day_type_labels.xlsx", "rows": len(day_labels_enriched)},
        {"file": "deviation_pattern_labels.xlsx", "rows": len(deviations_enriched)},
        {"file": "day_window_behavior_matrix.xlsx", "rows": len(day_window_matrix_enriched)},
        {"file": "archetype_similarity_features.xlsx", "rows": len(arche_enriched)},
        {"file": "setup_backtests_detailed.xlsx", "rows": len(setup_backtests)},
        {"file": "walk_forward_validation.xlsx", "rows": len(walk_forward)},
        {"file": "predictive_scoring_features.xlsx", "rows": len(predictive)},
        {"file": "decision_engine_daily.xlsx", "rows": len(decision_engine)},
        {"file": "trade_planning_templates.xlsx", "rows": len(trade_templates)},
        {"file": "news_flag_behavior_links.xlsx", "rows": len(news_flag_behavior_links)},
        {"file": "trader_style_report.md", "rows": len(news_day_rollup)},
    ])
    write_output_table(summary, "phase2_4_output_summary.xlsx")

if __name__ == "__main__":
    main()