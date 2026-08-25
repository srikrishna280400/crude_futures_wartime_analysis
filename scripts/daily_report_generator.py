"""daily_report_generator.py — Auto-generates the "next trading day" plan.

Purpose
-------
When invoked (or wired into --signals-only), reads the latest produced compact
artifacts and emits a Markdown report for the FIRST trading day AFTER the last
appended data date (i.e. "what do I do tomorrow, window by window"). Includes:
  1. Regime + phase-conditional probabilities per IST window (from window_stats)
  2. Signal cards from playbook/signals_live (Phase-conditional)
  3. LIVE news summary fetched from Al Jazeera, CNN live Iran-war page, and
     the Hormuz Letter X(twitter) handle — used to (a) warn and (b) frame
     escalation vs de-escalation scenarios as DEVIATIONS from the price-only plan
  4. Explicit scenario speculation: if an escalatory / de-escalatory headline
     breaks mid-day, expected directional deviation vs the base plan.

NOTE on data-integrity (Ground Rule 1): every price/pattern number traces to
the artifacts; news lines are fetched live but FAIL SOFTLY (no news → the
scenario table clearly says "no news fetched" rather than hallucinating).

Outputs
-------
  artifacts/daily_trading_report_YYYY-MM-DD.md   (human-scannable plan)
  artifacts/daily_trading_report_YYYY-MM-DD.json (machine-readable)
  Final .md also written to project root as TODAYS_PLAN.md for convenience.
"""

from __future__ import annotations

import json
import re
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ART = BASE / "artifacts"

# IST session windows (MCX trading day 9:00–23:30)
WINDOWS = [
    ("global_reopen_pre_mcx", "03:30–09:00"),
    ("mcx_open_drive", "09:00–10:30"),
    ("india_morning", "10:30–12:30"),
    ("india_midday", "12:30–15:30"),
    ("europe_midday", "15:30–18:00"),
    ("us_pre_open", "18:00–20:00"),
    ("us_open", "20:00–23:00"),
    ("mcx_tail", "23:00–23:30"),
]

# News sources
NEWS_SOURCES = {
    "aljazeera_iran": "https://www.aljazeera.com/where/iran/",
    "aljazeera_mideast": "https://www.aljazeera.com/where/middle-east/",
    "cnn_iran_live": "https://edition.cnn.com/world/live-news/iran-israel-live-intl-hnk",
    "hormuz_letter_x": "https://x.com/hormuzletter",
}

RETRY_BACKOFF = [2, 4, 8]


EXPECTED_WINDOWS = [
    "global_reopen_pre_mcx",
    "mcx_open_drive",
    "india_morning",
    "india_midday",
    "europe_midday",
    "us_pre_open",
    "us_open",
    "mcx_tail",
]


def is_session_complete(prim: pd.DataFrame, date: pd.Timestamp) -> Tuple[bool, List[str]]:
    """Check if a trading day has all expected session windows."""
    date_str = date.date().isoformat()
    session_data = prim[
        (prim['__stream'].isin(['WTI_session', 'BRENT_session'])) &
        (pd.to_datetime(prim['trade_date_ist']).dt.date == date.date())
    ]
    if session_data.empty:
        return False, EXPECTED_WINDOWS.copy()
    present = session_data['session_window_ist'].unique().tolist()
    missing = [w for w in EXPECTED_WINDOWS if w not in present]
    return len(missing) == 0, missing


def next_trading_day(after_dates: List[str]) -> str:
    """First IST trading day strictly after the latest appended data date."""
    latest = max(pd.to_datetime(after_dates))
    d = latest + timedelta(days=1)
    while d.weekday() >= 5:  # Sat/Sun → next Mon
        d += timedelta(days=1)
    return d.date().isoformat()


def plan_target_date(prim: pd.DataFrame, dates: List[str]) -> Tuple[str, str, List[str], bool]:
    """
    Determine the target date for the trading plan.
    Returns: (plan_date, latest_appended_date, missing_windows_today, is_intraday)
    - If latest day is complete → plan for next trading day
    - If latest day is incomplete → plan for today's remaining windows
    """
    latest_dt = max(pd.to_datetime(dates))
    latest_date_str = latest_dt.date().isoformat()
    complete, missing = is_session_complete(prim, latest_dt)

    if complete:
        # Day is done → plan for tomorrow
        plan_date = next_trading_day(dates)
        return plan_date, latest_date_str, [], False
    else:
        # Day in progress → plan for TODAY's remaining windows
        return latest_date_str, latest_date_str, missing, True


# ----------------------------------------------------------------------
# Live news fetch (fail-soft)
# ----------------------------------------------------------------------
def fetch_aljazeera(url: str) -> List[str]:
    lines = []
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        txt = re.sub(r"<[^>]+>", " ", r.text)
        txt = re.sub(r"\s+", " ", txt)
        for kw in ["Iran", "Israel", "Hormuz", "strike", "oil", "negotiation", "ceasefire", "US", "missile"]:
            m = re.search(r"([A-Z][^.]*%s[^.]*\.)" % kw, txt)
            if m:
                lines.append(m.group(1).strip()[:220])
        lines = list(dict.fromkeys(lines))[:12]
    except Exception as e:
        print(f"  !! news fetch failed ({url}): {e}", flush=True)
    return lines


def fetch_jina(url: str) -> List[str]:
    """Jina.ai reader proxy (free, no key) to render JS-heavy pages (CNN live, X)."""
    lines = []
    try:
        r = requests.get(f"https://r.jina.ai/{url}", timeout=25,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.ok:
            for line in r.text.splitlines():
                line = line.strip()
                if any(k in line.lower() for k in
                       ["iran", "israel", "hormuz", "strike", "oil", "negotiation",
                        "ceasefire", "missile", "tanker", "deal", "supreme"]):
                    lines.append(line[:220])
            lines = list(dict.fromkeys(lines))[:15]
    except Exception as e:
        print(f"  !! jina fetch failed ({url}): {e}", flush=True)
    return lines


def score_news_lines(lines: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """Split fetched lines into escalatory / de-escalatory / neutral buckets via keywords."""
    esc_kw = ["strike", "attack", "missile", "retaliat", "escalat", "target", "warn", "threat",
              "blockad", "seiz", "interdict", "drone", "bomb", "airstrike", "clos", "military action"]
    de_esc_kw = ["ceasefire", "negotiat", "deal", "talks", "de-escalat", "deescalat", "truce",
                 "agreement", "peace", "pause", "diplomacy", "release", "withdraw", "resume talks"]
    esc, de_esc, neutral = [], [], []
    for ln in lines:
        ll = ln.lower()
        if any(k in ll for k in de_esc_kw) and not any(k in ll for k in esc_kw):
            de_esc.append(ln)
        elif any(k in ll for k in esc_kw):
            esc.append(ln)
        else:
            neutral.append(ln)
    return esc, de_esc, neutral


def fetch_live_news() -> Dict:
    print(">>> fetching live news (fail-soft)...", flush=True)
    all_lines = []
    for name, url in NEWS_SOURCES.items():
        try:
            if "x.com" in url:
                all_lines += fetch_jina(url)
            elif "cnn.com" in url:
                all_lines += fetch_jina(url)
            else:
                all_lines += fetch_aljazeera(url)
            time.sleep(1.0)
        except Exception as e:
            print(f"  !! {name} error: {e}", flush=True)
    print(f">>> raw news lines collected: {len(all_lines)}", flush=True)
    esc, de_esc, neutral = score_news_lines(all_lines)
    return {
        "had_news": len(all_lines) > 0,
        "n_escalatory": len(esc),
        "n_deescalatory": len(de_esc),
        "n_neutral": len(neutral),
        "top_escalatory": esc[:4],
        "top_deescalatory": de_esc[:4],
        "top_neutral": neutral[:4],
    }


# ----------------------------------------------------------------------
# Build the plan
# ----------------------------------------------------------------------
def load_artifacts():
    phase = pd.read_csv(ART / "phase_lookup.csv")
    ws = pd.read_csv(ART / "window_stats.csv")
    playbook = pd.read_csv(ART / "playbook_summary.csv")
    reg = pd.read_csv(ART / "regime_predictions_live.csv")
    if (ART / "signals_live.csv").exists():
        try:
            signals = pd.read_csv(ART / "signals_live.csv")
        except Exception:
            signals = pd.DataFrame()
    else:
        signals = pd.DataFrame()
    prim = pd.read_parquet(ART / "primitives.parquet")
    if (ART / "prediction_scorecard.csv").exists():
        try:
            scorecard = pd.read_csv(ART / "prediction_scorecard.csv")
        except Exception:
            scorecard = pd.DataFrame()
    else:
        scorecard = pd.DataFrame()
    return phase, ws, playbook, reg, signals, prim, scorecard


def build_report() -> Dict:
    print(">>> daily_report_generator.py starting", flush=True)
    phase, ws, playbook, reg, signals, prim, scorecard = load_artifacts()

    # Determine current phase (latest regime prediction) + latest data date
    latest_reg = reg.iloc[-1]
    current_phase = int(latest_reg["phase_id"])
    phase_row = phase[phase["phase_id"] == current_phase]
    phase_label = phase_row["phase_label"].iloc[0] if not phase_row.empty else f"Phase {current_phase}"

    # Latest appended data date from primitives (session frames)
    dates = pd.to_datetime(prim[prim['__stream'].isin(['WTI_session', 'BRENT_session'])]['trade_date_ist'])

    # Determine plan target: if today's session is incomplete, plan for today's remaining windows
    plan_date, latest_data_date, missing_windows_today, is_intraday = plan_target_date(prim, dates.dt.date.astype(str).tolist())

    # News
    news = fetch_live_news()

    # Window stats for the current phase (session streams)
    p10 = ws[ws["phase_id"] == current_phase]

    # Get the latest actual closes (last appended day) for the entry/context table
    closes = prim[prim['__stream'] == 'WTI_daily'][['trade_date_ist', 'close_native']].sort_values('trade_date_ist')
    last_close_rows = closes.tail(3)
    latest_wti = float(closes['close_native'].iloc[-1]) if not closes.empty else np.nan
    closes_b = prim[prim['__stream'] == 'BRENT_daily'][['trade_date_ist', 'close_native']].sort_values('trade_date_ist')
    latest_brent = float(closes_b['close_native'].iloc[-1]) if not closes_b.empty else np.nan

    # Build per-window table
    window_rows = []
    for wname, wtime in WINDOWS:
        row_b = p10[(p10["stream"] == "BRENT_session") & (p10["session_window_ist"] == wname)]
        row_w = p10[(p10["stream"] == "WTI_session") & (p10["session_window_ist"] == wname)]
        b = row_b.iloc[0] if not row_b.empty else None
        w = row_w.iloc[0] if not row_w.empty else None
        if b is None and w is None:
            continue
        # Direction: use aggregate of both streams
        ups = int((b["n_up"] if b is not None else 0) + (w["n_up"] if w is not None else 0))
        dns = int((b["n_down"] if b is not None else 0) + (w["n_down"] if w is not None else 0))
        flt = int((b["n_flat"] if b is not None else 0) + (w["n_flat"] if w is not None else 0))
        n = ups + dns + flt
        if n == 0:
            continue
        p_up = ups / n * 100
        p_dn = dns / n * 100
        bias = "UP" if p_up > p_dn else ("DOWN" if p_dn > p_up else "FLAT")
        mean_b = float(b["mean_return_pct"]) if b is not None else np.nan
        mean_w = float(w["mean_return_pct"]) if w is not None else np.nan
        window_rows.append({
            "window": wname, "time_ist": wtime,
            "bias": bias, "p_up": round(p_up, 1), "p_down": round(p_dn, 1),
            "n": int(n), "mean_brent": mean_b, "mean_wti": mean_w,
            "low_conf": bool((b is not None and b["low_confidence_flag"]) or (w is not None and w["low_confidence_flag"])),
        })

    # Signal cards from signals_live / playbook for current phase
    signal_cards = []
    if not signals.empty:
        for _, s in signals.iterrows():
            signal_cards.append({
                "stream": s["stream"], "day_archetype": s["day_archetype"],
                "current_window": s["current_window"], "next_window": s["next_window"],
                "direction": s["direction"], "entry": float(s["entry_price"]),
                "stop": float(s["stop_price"]), "target": float(s["target_price"]),
                "p_up": float(s.get("p_up", np.nan)), "p_down": float(s.get("p_down", np.nan)),
                "size_frac": float(s.get("final_position_fraction", np.nan)),
                "low_conf": bool(s.get("fdr_q_value", 1.0) > 0.05 or s.get("significance") is False),
            })
    else:
        # Fall back to strong playbook patterns for current phase
        sp = playbook[(playbook["phase_id"] == current_phase) &
                      (playbook["n_observations"] >= 5)]
        for _, p in sp.sort_values("n_observations", ascending=False).head(6).iterrows():
            signal_cards.append({
                "stream": p["stream"], "day_archetype": p["day_archetype"],
                "current_window": p["current_window"], "next_window": p["top_next_window"],
                "direction": "UP" if p["pct_up_next"] > p["pct_down_next"] else "DOWN",
                "entry": None, "stop": None, "target": None,
                "p_up": float(p["pct_up_next"]) if "pct_up_next" in p else None,
                "p_down": float(p["pct_down_next"]) if "pct_down_next" in p else None,
                "size_frac": None, "low_conf": bool(p.get("low_confidence_flag", False)),
            })

    # Scorecard verdict
    sc_verdict = {}
    if not scorecard.empty:
        resolved = scorecard[scorecard["resolved"]]
        if not resolved.empty:
            sc_verdict = {
                "resolved": int(len(resolved)),
                "hits": int(resolved["hit"].sum()),
                "hit_rate": float(resolved["hit"].mean()),
                "total_pnl_pts": float(resolved["resolved_pnl_pct"].sum()),
            }

    report = {
        "generated_at": datetime.now().isoformat(),
        "regime": {"phase_id": current_phase, "phase_label": phase_label,
                   "confidence": float(latest_reg.get(f"prob_phase_{current_phase}", 0.0)),
                   "as_of_date": str(latest_reg["trade_date_ist"])[:10]},
        "latest_appended_data_date": latest_data_date,
        "plan_date": plan_date,
        "is_intraday": is_intraday,
        "missing_windows_today": missing_windows_today,
        "instructions": {
            "duration": "09:00–23:30 IST",
            "disclaimer": "Conditional-probability lookup, NOT a forecast. Phase sample small → size 50% max on LOW_CONF cells. Risk: ≤1% equity/trade, stop at -2% day, flatten on any Hormuz/nuclear headline.",
        },
        "latest_closes": {"wti": latest_wti, "brent": latest_brent,
                          "as_of": latest_data_date},
        "window_plan": window_rows,
        "signal_cards": signal_cards,
        "live_news": news,
        "scorecard_verdict": sc_verdict,
    }
    return report


def render_markdown(r: Dict) -> str:
    L = []
    session_tag = " (intraday — remaining windows)" if r.get("is_intraday") else ""
    L.append(f"# Daily Trading Plan — {r['plan_date']} (09:00–23:30 IST){session_tag}")
    L.append(f"\nGenerated {r['generated_at'][:16]} · Data through {r['latest_appended_data_date']}")
    if r.get("is_intraday"):
        missing = r.get("missing_windows_today", [])
        completed = [w["window"] for w in r["window_plan"] if w["window"] not in missing]
        L.append(f"\n⚠️ **INTRADAY UPDATE** — Only {len(completed)} of 8 windows available for {r['plan_date']}.")
        L.append(f"  Completed windows: {', '.join(completed) if completed else 'none yet'}")
        L.append(f"  Remaining windows to monitor: {', '.join(missing) if missing else 'all (session just started)'}")
        L.append(f"  _Plan shows probabilities from historical patterns, but only reflects what the model has seen so far today._")
    reg = r["regime"]
    L.append(f"\n## 1) Regime\n- Phase {reg['phase_id']}: **{reg['phase_label']}** "
             f"(conf {reg['confidence']*100:.0f}%, as of {reg['as_of_date']})")
    cl = r["latest_closes"]
    if cl.get("wti") is not None:
        L.append(f"- Last close (WTI ${cl['wti']:.2f} · BRENT ${cl['brent']:.2f}) as of {cl['as_of']}")
    L.append(f"\n> {r['instructions']['disclaimer']}\n")

    L.append(f"\n## 2) Window-by-Window Plan (Phase {reg['phase_id']})")
    L.append("\n| Window | Time IST | Bias | %UP | %DOWN | n | mean BRENT% | mean WTI% |")
    L.append("|---|---|---|---|---|---|---|---|")
    for w in r["window_plan"]:
        mb = f"{w['mean_brent']:+.2f}" if np.isfinite(w["mean_brent"]) else "-"
        mw = f"{w['mean_wti']:+.2f}" if np.isfinite(w["mean_wti"]) else "-"
        L.append(f"| {w['window']} | {w['time_ist']} | {w['bias']}{' ⚠️' if w['low_conf'] else ''} | "
                 f"{w['p_up']} | {w['p_down']} | {w['n']} | {mb} | {mw} |")

    L.append(f"\n## 3) Active Signal Cards")
    if r["signal_cards"]:
        for s in r["signal_cards"]:
            sizes = f"size {s['size_frac']*100:.0f}%" if s.get("size_frac") is not None and np.isfinite(s.get("size_frac", np.nan)) else ""
            lvl = ""
            if s.get("entry") is not None:
                lvl = f" · Entry {s['entry']:.2f} / SL {s['stop']:.2f} / TP {s['target']:.2f}"
            flu = ""
            if s.get("p_up") is not None:
                flu = f" · P(UP) {s['p_up']:.0f}% / P(DN) {s['p_down']:.0f}%"
            low = " ⚠️LOW-CONF" if s.get("low_conf") else ""
            L.append(f"- **{s['stream']}** P{reg['phase_id']} @ {s['day_archetype']} | "
                     f"{s['current_window']}→{s['next_window']} **{s['direction']}**{low}{lvl}{flu} {sizes}")
    else:
        L.append("_No active signals for the current phase._")

    # News
    nw = r["live_news"]
    L.append(f"\n## 4) Live News (Al Jazeera / CNN Iran live / Hormuz Letter)")
    if nw.get("had_news"):
        L.append(f"\n**Escalatory signals ({nw['n_escalatory']}):**")
        for ln in nw["top_escalatory"][:4]:
            L.append(f"- {ln}")
        L.append(f"\n**De-escalatory signals ({nw['n_deescalatory']}):**")
        for ln in nw["top_deescalatory"][:4]:
            L.append(f"- {ln}")
        L.append(f"\n**Neutral/other ({nw['n_neutral']}):**")
        for ln in nw["top_neutral"][:3]:
            L.append(f"- {ln}")
    else:
        L.append("_No live news fetched (fail-soft). Base pattern plan only — news may deviate._")

    # Scenario speculation
    L.append(f"\n## 5) Scenario Speculation — Deviations from the base plan")
    base_dir = "short" if sum(1 for w in r["window_plan"] if w["bias"] == "DOWN") >= \
                            sum(1 for w in r["window_plan"] if w["bias"] == "UP") else "long"
    L.append(f"- Base plan net bias: **{base_dir.upper()}** (price-only patterns).")
    L.append(f"- **If an ESCALATORY headline breaks** (strike on Iranian soil, Hormuz closure, tanker seizure, "
             f"missile attack): expect an immediate **UP shock spike** (war-premium bid) then whipsaw into "
             f"evening — this REVERSES a base-{base_dir} plan. Prefer range-fade; widen stops; consider "
             f"spinal long into the spike, short into the fade.")
    L.append(f"- **If a DE-ESCALATORY headline breaks** (Hormuz deal, ceasefire, sanctions-lift, talks-resume): "
             f"expect an **immediate DOWN slide** (war premium unwinds hard) — REVERSES a base-{base_dir} plan. "
             f"Shorts favored into any rally-pop.")
    L.append(f"- **If no headline breaks:** trade the base plan as-is at reduced size (phase sample small).")

    # Scorecard verdict
    sc = r.get("scorecard_verdict", {})
    if sc:
        L.append(f"\n## 6) Prediction Scorecard (P1)")
        L.append(f"- Resolved signals: {sc['resolved']} · Hits: {sc['hits']} · Hit-rate: {sc['hit_rate']*100:.0f}% · "
                 f"Net PnL(pts): {sc['total_pnl_pts']:+.2f}")

    L.append(f"\n---\n*Auto-generated by daily_report_generator.py. Not financial advice.*")
    return "\n".join(L)


def main():
    r = build_report()

    # Write JSON + MD
    (ART / f"daily_trading_report_{r['plan_date']}.json").write_text(
        json.dumps(r, indent=2, default=str), encoding="utf-8")
    md = render_markdown(r)
    (ART / f"daily_trading_report_{r['plan_date']}.md").write_text(md, encoding="utf-8")
    (BASE / "TODAYS_PLAN.md").write_text(md, encoding="utf-8")
    print(f">>> wrote news-conditional daily plan for {r['plan_date']}", flush=True)
    return r


if __name__ == "__main__":
    main()