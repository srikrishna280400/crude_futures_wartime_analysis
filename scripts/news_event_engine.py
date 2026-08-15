"""news_event_engine.py — News/Event integration framework for crude oil war regime analysis.

Features:
- GDELT API integration for global event data
- Reuters/NewsAPI sentiment scoring
- Iran/Israel/Hormuz/OPEC keyword filtering
- Event-to-phase mapping and anomaly correlation
- Cached results to avoid rate limits
- Daily event summary for regime classifier

Outputs:
- artifacts/news_events_master.csv (all events)
- artifacts/news_daily_summary.csv (daily aggregates)
- artifacts/news_anomaly_correlation.csv (event-anomaly links)
- artifacts/event_phase_mapping.csv (event impact on phases)
"""

from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")

# ─── Configuration ────────────────────────────────────────────────────────────

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

CACHE_DIR = ARTIFACTS / "news_cache"
CACHE_DIR.mkdir(exist_ok=True)

# API Keys (set via environment)
GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
REUTERS_API_KEY = os.getenv("REUTERS_API_KEY", "")

# Keywords for crude-relevant events
CRUDE_KEYWORDS = {
    "iran": ["iran", "iranian", "tehran", "khamenei", "rouhani", "raisi", "irgc", "revolutionary guard"],
    "israel": ["israel", "israeli", "netanyahu", "idf", "tel aviv", "jerusalem"],
    "hormuz": ["hormuz", "strait of hormuz", "hormuz strait"],
    "opec": ["opec", "opec+", "opec plus", "saudi arabia", "saudi oil", "russia oil"],
    "supply": ["oil supply", "oil production", "barrels per day", "mbd", "output cut", "output hike"],
    "inventory": ["oil inventory", "crude inventory", "eia inventory", "api inventory", "stockpile"],
    "sanctions": ["sanctions", "embargo", "oil sanctions", "iran sanctions", "russia sanctions"],
    "tanker": ["tanker", "oil tanker", "vessel seized", "ship seized", "maritime security"],
    "price": ["oil price", "crude price", "brent crude", "wti crude", "oil rally", "oil slide"],
    "conflict": ["missile", "strike", "attack", "drone", "retaliation", "escalation", "ceasefire"],
    "nuclear": ["nuclear deal", "jcpoa", "nuclear program", "uranium enrichment"],
}

# Geographic focus
GEO_FILTER = ["Iran", "Israel", "Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait",
              "Iraq", "Syria", "Lebanon", "Yemen", "Oman", "Bahrain", "Strait of Hormuz",
              "Persian Gulf", "Gulf of Oman", "Red Sea", "Suez Canal"]

# Cache TTL (hours)
CACHE_TTL_HOURS = 6

# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class NewsEvent:
    event_id: str
    timestamp_utc: str
    timestamp_ist: str
    source: str
    headline: str
    summary: str
    url: str
    categories: List[str]
    sentiment: float  # -1 to 1
    relevance_score: float  # 0 to 1
    entities: List[str]
    themes: List[str]
    locations: List[str]

@dataclass
class DailyNewsSummary:
    date_ist: str
    n_events: int
    avg_sentiment: float
    sentiment_std: float
    categories: Dict[str, int]
    top_entities: Dict[str, int]
    key_themes: List[str]
    bullish_signals: int
    bearish_signals: int
    net_sentiment: float

# ─── Keyword Matching & Scoring ──────────────────────────────────────────────

def score_relevance(text: str) -> Tuple[float, List[str]]:
    """Score text relevance to crude oil war regime (0-1) and return matched categories."""
    text_lower = text.lower()
    matched = []
    total_score = 0

    for category, keywords in CRUDE_KEYWORDS.items():
        cat_score = 0
        for kw in keywords:
            if kw in text_lower:
                cat_score += 1
        if cat_score > 0:
            matched.append(category)
            total_score += min(cat_score * 0.15, 0.5)

    return min(total_score, 1.0), matched

def score_sentiment(text: str) -> float:
    """Simple rule-based sentiment for oil markets (-1 to 1)."""
    text_lower = text.lower()

    bullish = ["surge", "rally", "jump", "spike", "soar", "climb", "gain", "rise", "higher",
               "bullish", "tight", "shortage", "disruption", "cut", "reduce", "draw", "decline in stock",
               "sanction", "embargo", "conflict", "attack", "strike", "missile", "escalation",
               "closure", "blockade", "interdiction", "seizure"]

    bearish = ["slide", "drop", "fall", "plunge", "tumble", "slump", "decline", "lower", "bearish",
               "glut", "surplus", "build", "increase in stock", "raise output", "hike production",
               "ceasefire", "de-escalation", "talks", "agreement", "deal", "resume", "reopen",
               "ease", "waiver", "exemption"]

    bull = sum(1 for w in bullish if w in text_lower)
    bear = sum(1 for w in bearish if w in text_lower)

    if bull + bear == 0:
        return 0.0

    return (bull - bear) / (bull + bear)

# ─── GDELT Integration ────────────────────────────────────────────────────────

def fetch_gdelt_events(start_date: str, end_date: str, max_records: int = 250) -> List[NewsEvent]:
    """Fetch events from GDELT API."""
    events = []

    params = {
        "format": "json",
        "query": " OR ".join([f"({kw})" for kws in CRUDE_KEYWORDS.values() for kw in kws[:3]]),
        "mode": "artlist",
        "maxrecords": str(max_records),
        "startdatetime": start_date.replace("-", "") + "000000",
        "enddatetime": end_date.replace("-", "") + "235959",
        "sort": "datedesc",
    }

    try:
        response = requests.get(GDELT_API_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        for article in data.get("articles", []):
            try:
                headline = article.get("title", "")
                summary = article.get("seoUrl", "")  # GDELT doesn't always have summary
                url = article.get("url", "")
                source = article.get("domain", "GDELT")
                pub_date = article.get("seendate", "")

                if not headline or not pub_date:
                    continue

                # Parse date
                dt_utc = datetime.strptime(pub_date[:14], "%Y%m%d%H%M%S")
                dt_ist = dt_utc + timedelta(hours=5, minutes=30)

                relevance, categories = score_relevance(headline + " " + summary)
                if relevance < 0.1:
                    continue

                sentiment = score_sentiment(headline + " " + summary)

                event = NewsEvent(
                    event_id=f"GDELT_{pub_date}_{hash(url) % 100000}",
                    timestamp_utc=dt_utc.isoformat(),
                    timestamp_ist=dt_ist.isoformat(),
                    source=source,
                    headline=headline,
                    summary=summary[:500] if summary else headline,
                    url=url,
                    categories=categories,
                    sentiment=sentiment,
                    relevance_score=relevance,
                    entities=extract_entities(headline + " " + summary),
                    themes=categories,
                    locations=extract_locations(headline + " " + summary),
                )
                events.append(event)
            except Exception:
                continue

    except Exception as e:
        print(f"GDELT fetch error: {e}")

    return events

def extract_entities(text: str) -> List[str]:
    """Extract key entities (simple keyword-based)."""
    entities = []
    text_lower = text.lower()

    # Key persons
    persons = ["netanyahu", "khamenei", "raisi", "biden", "putin", "bin salman", "mbs",
               "blinken", "austin", "gallant", "hagari"]
    for p in persons:
        if p in text_lower:
            entities.append(p.title())

    # Organizations
    orgs = ["opec", "iea", "eia", "api", "iaea", "un", "unsc", "eu", "nato", "irgc", "idf", "houthis"]
    for o in orgs:
        if o in text_lower:
            entities.append(o.upper())

    return entities

def extract_locations(text: str) -> List[str]:
    """Extract geographic locations."""
    locations = []
    text_lower = text.lower()

    for loc in GEO_FILTER:
        if loc.lower() in text_lower:
            locations.append(loc)

    return locations

# ─── NewsAPI Integration ─────────────────────────────────────────────────────

def fetch_newsapi_events(start_date: str, end_date: str, max_pages: int = 5) -> List[NewsEvent]:
    """Fetch from NewsAPI.org."""
    if not NEWSAPI_KEY:
        return []

    events = []
    query = " OR ".join([f'"{kw}"' for kws in CRUDE_KEYWORDS.values() for kw in kws[:2]])

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": start_date,
        "to": end_date,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 100,
        "apiKey": NEWSAPI_KEY,
    }

    try:
        for page in range(1, max_pages + 1):
            params["page"] = page
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "ok":
                break

            for article in data.get("articles", []):
                headline = article.get("title", "")
                summary = article.get("description", "") or ""
                url = article.get("url", "")
                source = article.get("source", {}).get("name", "NewsAPI")
                pub_date = article.get("publishedAt", "")

                if not headline or not pub_date:
                    continue

                dt_utc = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                dt_ist = dt_utc + timedelta(hours=5, minutes=30)

                relevance, categories = score_relevance(headline + " " + summary)
                if relevance < 0.1:
                    continue

                sentiment = score_sentiment(headline + " " + summary)

                event = NewsEvent(
                    event_id=f"NEWSAPI_{pub_date[:10]}_{hash(url) % 100000}",
                    timestamp_utc=dt_utc.isoformat(),
                    timestamp_ist=dt_ist.isoformat(),
                    source=source,
                    headline=headline,
                    summary=summary[:500],
                    url=url,
                    categories=categories,
                    sentiment=sentiment,
                    relevance_score=relevance,
                    entities=extract_entities(headline + " " + summary),
                    themes=categories,
                    locations=extract_locations(headline + " " + summary),
                )
                events.append(event)

            time.sleep(0.5)  # Rate limit

    except Exception as e:
        print(f"NewsAPI fetch error: {e}")

    return events

# ─── Caching ──────────────────────────────────────────────────────────────────

def get_cache_path(source: str, date: str) -> Path:
    return CACHE_DIR / f"{source}_{date}.json"

def load_cache(source: str, date: str) -> Optional[List[NewsEvent]]:
    path = get_cache_path(source, date)
    if not path.exists():
        return None

    # Check TTL
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    if datetime.now() - mtime > timedelta(hours=CACHE_TTL_HOURS):
        return None

    try:
        with open(path) as f:
            data = json.load(f)
        return [NewsEvent(**e) for e in data]
    except Exception:
        return None

def save_cache(source: str, date: str, events: List[NewsEvent]) -> None:
    path = get_cache_path(source, date)
    with open(path, "w") as f:
        json.dump([asdict(e) for e in events], f)

# ─── Main Pipeline ────────────────────────────────────────────────────────────

def fetch_all_news(start_date: str, end_date: str) -> List[NewsEvent]:
    """Fetch news from all sources with caching."""
    all_events = []

    # Parse date range
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    # Fetch by day to leverage caching
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")

        # GDELT
        cached = load_cache("gdelt", date_str)
        if cached:
            all_events.extend(cached)
        else:
            events = fetch_gdelt_events(date_str, date_str)
            if events:
                save_cache("gdelt", date_str, events)
                all_events.extend(events)

        # NewsAPI
        cached = load_cache("newsapi", date_str)
        if cached:
            all_events.extend(cached)
        else:
            events = fetch_newsapi_events(date_str, date_str)
            if events:
                save_cache("newsapi", date_str, events)
                all_events.extend(events)

        current += timedelta(days=1)
        time.sleep(0.2)

    return all_events

def build_daily_summaries(events: List[NewsEvent]) -> pd.DataFrame:
    """Aggregate events into daily summaries."""
    if not events:
        return pd.DataFrame()

    df = pd.DataFrame([asdict(e) for e in events])
    df["timestamp_ist"] = pd.to_datetime(df["timestamp_ist"])
    df["date_ist"] = df["timestamp_ist"].dt.date

    summaries = []
    for date, group in df.groupby("date_ist"):
        # Flatten categories
        all_cats = []
        for cats in group["categories"]:
            all_cats.extend(cats)
        cat_counts = pd.Series(all_cats).value_counts().to_dict()

        # Flatten entities
        all_entities = []
        for ents in group["entities"]:
            all_entities.extend(ents)
        ent_counts = pd.Series(all_entities).value_counts().to_dict()

        bullish = (group["sentiment"] > 0.2).sum()
        bearish = (group["sentiment"] < -0.2).sum()

        summaries.append(DailyNewsSummary(
            date_ist=str(date),
            n_events=len(group),
            avg_sentiment=group["sentiment"].mean(),
            sentiment_std=group["sentiment"].std(),
            categories=cat_counts,
            top_entities=ent_counts,
            key_themes=list(cat_counts.keys())[:5],
            bullish_signals=int(bullish),
            bearish_signals=int(bearish),
            net_sentiment=group["sentiment"].mean(),
        ).__dict__)

    return pd.DataFrame(summaries)

def correlate_with_anomalies(events: List[NewsEvent], anomalies_path: Path) -> pd.DataFrame:
    """Correlate news events with detected anomalies."""
    if not anomalies_path.exists():
        return pd.DataFrame()

    anomalies = pd.read_csv(anomalies_path)
    anomalies["trade_date_ist"] = pd.to_datetime(anomalies["trade_date_ist"])

    if not events:
        return pd.DataFrame()

    df = pd.DataFrame([asdict(e) for e in events])
    df["timestamp_ist"] = pd.to_datetime(df["timestamp_ist"])
    df["date_ist"] = df["timestamp_ist"].dt.date

    correlations = []
    for _, anom in anomalies.iterrows():
        anom_date = anom["trade_date_ist"].date()
        anom_metric = anom["anomaly_metric"]
        anom_z = anom["z_value"]

        # Events on same day or 1 day before
        window_events = df[df["date_ist"].between(anom_date - timedelta(days=1), anom_date)]

        if len(window_events) > 0:
            correlations.append({
                "anomaly_date": str(anom_date),
                "anomaly_metric": anom_metric,
                "anomaly_z": anom_z,
                "stream": anom["__stream"],
                "phase_id": anom["phase_id"],
                "phase_label": anom["phase_label"],
                "n_events_window": len(window_events),
                "avg_sentiment": window_events["sentiment"].mean(),
                "max_relevance": window_events["relevance_score"].max(),
                "categories": "|".join(window_events["categories"].explode().unique()),
                "top_headlines": "|".join(window_events["headline"].head(3).tolist()),
            })

    return pd.DataFrame(correlations)

def map_events_to_phases(events: List[NewsEvent], phase_lookup: Path) -> pd.DataFrame:
    """Map events to war regime phases."""
    if not events:
        return pd.DataFrame()

    phase = pd.read_csv(phase_lookup)
    phase["start"] = pd.to_datetime(phase["start_datetime_ist"])
    phase["end"] = pd.to_datetime(phase["end_datetime_ist"])

    df = pd.DataFrame([asdict(e) for e in events])
    df["timestamp_ist"] = pd.to_datetime(df["timestamp_ist"])

    mappings = []
    for _, event in df.iterrows():
        for _, p in phase.iterrows():
            if p["start"] <= event["timestamp_ist"] <= p["end"]:
                mappings.append({
                    "event_id": event["event_id"],
                    "event_timestamp": event["timestamp_ist"],
                    "phase_id": int(p["phase_id"]),
                    "phase_label": p["phase_label"],
                    "headline": event["headline"],
                    "sentiment": event["sentiment"],
                    "relevance": event["relevance_score"],
                    "categories": "|".join(event["categories"]),
                })
                break

    return pd.DataFrame(mappings)

def run_news_pipeline(start_date: str = None, end_date: str = None) -> Dict:
    """Run the complete news/event pipeline."""
    if start_date is None:
        # Default to last 30 days
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    print(f">>> News/Event Pipeline: {start_date} to {end_date}", flush=True)

    # Fetch events
    events = fetch_all_news(start_date, end_date)
    print(f">>> Fetched {len(events)} events from all sources", flush=True)

    if not events:
        return {"status": "warning", "message": "No events fetched"}

    # Save master events
    events_df = pd.DataFrame([asdict(e) for e in events])
    events_df.to_csv(ARTIFACTS / "news_events_master.csv", index=False)

    # Daily summaries
    daily = build_daily_summaries(events)
    daily.to_csv(ARTIFACTS / "news_daily_summary.csv", index=False)

    # Anomaly correlation
    anomaly_corr = correlate_with_anomalies(events, ARTIFACTS / "anomalies.csv")
    anomaly_corr.to_csv(ARTIFACTS / "news_anomaly_correlation.csv", index=False)

    # Phase mapping
    phase_map = map_events_to_phases(events, ARTIFACTS / "phase_lookup.csv")
    phase_map.to_csv(ARTIFACTS / "event_phase_mapping.csv", index=False)

    # Summary stats
    summary = {
        "date_range": f"{start_date} to {end_date}",
        "total_events": len(events),
        "sources": events_df["source"].value_counts().to_dict(),
        "categories": events_df["categories"].explode().value_counts().to_dict(),
        "avg_sentiment": float(events_df["sentiment"].mean()),
        "daily_summaries": len(daily),
        "anomaly_correlations": len(anomaly_corr),
        "phase_mappings": len(phase_map),
    }

    with open(ARTIFACTS / "news_pipeline_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f">>> News Pipeline Complete: {summary}", flush=True)
    return {"status": "success", "summary": summary}

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import sys
    start = sys.argv[1] if len(sys.argv) > 1 else None
    end = sys.argv[2] if len(sys.argv) > 2 else None
    run_news_pipeline(start, end)

if __name__ == "__main__":
    main()