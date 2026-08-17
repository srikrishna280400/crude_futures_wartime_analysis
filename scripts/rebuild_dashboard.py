"""rebuild_dashboard.py — Read template + artifacts → dashboard_v3.html"""
import json, tempfile, shutil, os, sys
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ART = BASE / "artifacts"
TPL = BASE / "scripts" / "dashboard_template.html"

def rx(path):
    t = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    t.close()
    try: shutil.copy(str(path), t.name); return pd.read_excel(t.name)
    finally: os.unlink(t.name)

def sf(o):
    if isinstance(o,dict): return {k:sf(v) for k,v in o.items()}
    if isinstance(o,list): return [sf(x) for x in o]
    if o is None: return None
    try:
        if pd.isna(o): return None
    except: pass
    if isinstance(o,pd.Timestamp): return str(o)
    if isinstance(o,np.integer): return int(o)
    if isinstance(o,np.floating): return float(o)
    if isinstance(o,np.bool_): return bool(o)
    return o

def build():
    d = {}
    try: d['phases'] = sf(pd.read_csv(ART/'phase_lookup.csv').to_dict(orient='records'))
    except: d['phases'] = []
    try:
        w = rx(BASE/'wti_daily_ist.csv')[['trade_date_ist','close_native','net_day_return_pct']].rename(columns={'close_native':'close','net_day_return_pct':'ret'})
        b = rx(BASE/'brent_daily_ist.csv')[['trade_date_ist','close_native','net_day_return_pct']].rename(columns={'close_native':'close','net_day_return_pct':'ret'})
        p = w.merge(b,on='trade_date_ist',suffixes=('_wti','_brent')).sort_values('trade_date_ist')
        p['trade_date_ist'] = pd.to_datetime(p['trade_date_ist']).dt.strftime('%Y-%m-%d')
        p['cum_wti'] = (p['close_wti']/p['close_wti'].iloc[0]-1)*100
        p['cum_brent'] = (p['close_brent']/p['close_brent'].iloc[0]-1)*100
        d['prices'] = sf(p.to_dict(orient='records'))
        d['latest'] = {'wti':float(p['close_wti'].iloc[-1]),'brent':float(p['close_brent'].iloc[-1]),'date':str(p['trade_date_ist'].iloc[-1])}
    except: d['prices']=[]; d['latest']={}
    try:
        ws = pd.read_csv(ART/'window_stats.csv')
        d['window_stats'] = sf(ws[ws['n_valid']>=3].to_dict(orient='records'))
    except: d['window_stats']=[]
    try:
        sp = pd.read_csv(ART/'playbook_strong_patterns.csv').sort_values('n_observations',ascending=False).head(30)
        d['strong_patterns'] = sf(sp.to_dict(orient='records'))
    except: d['strong_patterns']=[]
    try:
        rp = pd.read_csv(ART/'regime_predictions_live.csv')
        d['regime'] = sf(rp.tail(10).to_dict(orient='records'))
        lr = rp.iloc[-1]; pid = int(lr['predicted_phase'])
        d['current_regime'] = {'date':str(lr['trade_date_ist'])[:10],'phase':pid,'confidence':float(lr.get('prob_phase_'+str(pid),0))}
    except: d['regime']=[]; d['current_regime']={}
    try: d['anomalies'] = sf(pd.read_csv(ART/'anomalies.csv').to_dict(orient='records'))
    except: d['anomalies']=[]
    try: d['signals'] = sf(pd.read_csv(ART/'signals_live.csv').to_dict(orient='records'))
    except: d['signals']=[]
    try:
        with open(ART/'backtest_summary.json') as f: d['backtest'] = json.load(f)
    except: d['backtest']={}
    try:
        d['cross_phase_sim'] = sf(pd.read_csv(ART/'cross_phase_similarity.csv').to_dict(orient='records'))
    except: d['cross_phase_sim'] = []
    try:
        d['cross_phase_borrowed'] = sf(pd.read_csv(ART/'cross_phase_borrowed.csv').to_dict(orient='records'))
    except: d['cross_phase_borrowed'] = []
    return d

if __name__ == "__main__":
    if not TPL.exists(): print(f"Template missing: {TPL}"); sys.exit(1)
    data = build()
    js = json.dumps(data, default=str)
    # Write dashboard HTML (template as-is — no inline data replacement needed)
    html = TPL.read_text(encoding='utf-8')
    (BASE/'dashboard_v3.html').write_text(html, encoding='utf-8')
    print(f">>> wrote dashboard_v3.html ({len(html):,} chars)")
    # Write the separate data JS file that dashboard_v3.html loads
    data_js = "var D=" + js + ";"
    (BASE/'dashboard_data.js').write_text(data_js, encoding='utf-8')
    print(f">>> wrote dashboard_data.js ({len(data_js):,} chars)")