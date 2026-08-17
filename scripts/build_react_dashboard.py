"""build_react_dashboard.py — Generates dashboard_data.json for the React dashboard.
The React/Vite app is at dashboard/; the data JSON is written to dist/public."""

import json, tempfile, shutil, os, subprocess, sys
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ART = BASE / "artifacts"
DASHBOARD_DIR = BASE / "dashboard"
PUBLIC_DIR = DASHBOARD_DIR / "public"
OUTPUT_DIR = BASE / "dashboard_app"

def rx(p):
    t=tempfile.NamedTemporaryFile(suffix=".xlsx",delete=False);t.close()
    try:shutil.copy(str(p),t.name);return pd.read_excel(t.name)
    finally:os.unlink(t.name)

def sf(o):
    if isinstance(o,dict):return{k:sf(v)for k,v in o.items()}
    if isinstance(o,list):return[sf(x)for x in o]
    if o is None:return None
    try:
        if pd.isna(o):return None
    except:pass
    if isinstance(o,pd.Timestamp):return str(o)
    if isinstance(o,np.integer):return int(o)
    if isinstance(o,np.floating):return float(o)
    if isinstance(o,np.bool_):return bool(o)
    return o

def build_data():
    d={}
    try:d['phases']=sf(pd.read_csv(ART/'phase_lookup.csv').to_dict(orient='records'))
    except:d['phases']=[]
    try:
        w=rx(BASE/'wti_daily_ist.csv')[['trade_date_ist','close_native','net_day_return_pct']].rename(columns={'close_native':'c','net_day_return_pct':'r'})
        b=rx(BASE/'brent_daily_ist.csv')[['trade_date_ist','close_native','net_day_return_pct']].rename(columns={'close_native':'c','net_day_return_pct':'r'})
        p=w.merge(b,on='trade_date_ist',suffixes=('_w','_b')).sort_values('trade_date_ist')
        p['trade_date_ist']=pd.to_datetime(p['trade_date_ist']).dt.strftime('%Y-%m-%d')
        p['cw']=(p['c_w']/p['c_w'].iloc[0]-1)*100
        p['cb']=(p['c_b']/p['c_b'].iloc[0]-1)*100
        d['p']=sf(p[['trade_date_ist','c_w','c_b','cw','cb']].to_dict(orient='records'))
        d['l']={'w':float(p['c_w'].iloc[-1]),'b':float(p['c_b'].iloc[-1]),'d':str(p['trade_date_ist'].iloc[-1])}
    except:d['p']=[];d['l']={}
    try:
        ws=pd.read_csv(ART/'window_stats.csv')
        d['ws']=sf(ws[ws['n_valid']>=3].to_dict(orient='records'))
    except:d['ws']=[]
    try:
        sp=pd.read_csv(ART/'playbook_strong_patterns.csv').sort_values('n_observations',ascending=False).head(30)
        d['sp']=sf(sp.to_dict(orient='records'))
    except:d['sp']=[]
    try:
        rp=pd.read_csv(ART/'regime_predictions_live.csv')
        d['rg']=sf(rp.tail(10).to_dict(orient='records'))
        lr=rp.iloc[-1];pid=int(lr['predicted_phase'])
        d['cr']={'d':str(lr['trade_date_ist'])[:10],'p':pid,'c':float(lr.get('prob_phase_'+str(pid),0))}
    except:d['rg']=[];d['cr']={}
    try:d['an']=sf(pd.read_csv(ART/'anomalies.csv').to_dict(orient='records'))
    except:d['an']=[]
    try:d['sg']=sf(pd.read_csv(ART/'signals_live.csv').to_dict(orient='records'))
    except:d['sg']=[]
    try:d['bt']=json.load(open(ART/'backtest_summary.json'))
    except:d['bt']={}
    try:d['dt']=sf(pd.read_csv(ART/'day_type_phase_share.csv').to_dict(orient='records'))
    except:d['dt']=[]
    try:
        tp=pd.read_csv(ART/'triplets_catalog.csv').sort_values('composite_score',ascending=False).head(20)
        d['tp']=sf(tp.to_dict(orient='records'))
    except:d['tp']=[]
    try:d['cf']=sf(pd.read_csv(ART/'conformity_stats.csv').sort_values('n',ascending=False).head(30).to_dict(orient='records'))
    except:d['cf']=[]
    try:d['xs']=sf(pd.read_csv(ART/'cross_phase_similarity.csv').to_dict(orient='records'))
    except:d['xs']=[]
    try:d['xb']=sf(pd.read_csv(ART/'cross_phase_borrowed.csv').to_dict(orient='records'))
    except:d['xb']=[]
    return d

def main():
    print(">>> building react dashboard...", flush=True)
    data = build_data()
    js = json.dumps(data, default=str)

    # Write data JSON to dashboard/public for Vite dev server
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    (PUBLIC_DIR / 'dashboard_data.json').write_text(js, encoding='utf-8')

    # Build the Vite app
    result = subprocess.run(['npm', 'run', 'build'], cwd=str(DASHBOARD_DIR), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"!! Build failed: {result.stderr[-500:]}", flush=True)
        return False

    # Copy built app + data to dashboard_app
    shutil.rmtree(str(OUTPUT_DIR), ignore_errors=True)
    shutil.copytree(str(DASHBOARD_DIR / 'dist'), str(OUTPUT_DIR))
    shutil.copy(str(PUBLIC_DIR / 'dashboard_data.json'), str(OUTPUT_DIR / 'dashboard_data.json'))

    print(f">>> React dashboard built: {OUTPUT_DIR}", flush=True)
    print(f">>>   index.html ({len((OUTPUT_DIR/'index.html').read_bytes())} bytes)", flush=True)
    print(f">>>   dashboard_data.json ({len(js):,} chars)", flush=True)
    print(f">>>   To serve: cd {OUTPUT_DIR} && python3 -m http.server 8080", flush=True)
    print(f">>>   To dev: cd {DASHBOARD_DIR} && npm run dev", flush=True)
    return True

if __name__ == '__main__':
    if not main():
        sys.exit(1)