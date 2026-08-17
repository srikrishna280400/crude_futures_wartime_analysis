"""build_single_dashboard.py — Generates a SINGLE self-contained dashboard_v3.html
with ALL data inline. No external JS files, no CDN dependencies, no template files.
Data injected via .replace(), not f-strings — no brace escaping issues."""
import json, tempfile, shutil, os, sys, datetime
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ART = BASE / "artifacts"

def rx(p):
    t = tempfile.NamedTemporaryFile(suffix=".xlsx",delete=False);t.close()
    try: shutil.copy(str(p),t.name);return pd.read_excel(t.name)
    finally: os.unlink(t.name)

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

if __name__=='__main__':
    data=build_data()
    json_str=json.dumps(data,default=str)

    HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Crude Analysis Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0b1120;--p:#131a2b;--p2:#1a2340;--b:#253050;--t:#e2e8f0;--d:#8892b0;--r:#e94560;--g:#f7b733;--gn:#38ada9;--o:#ffa500}
body{font-family:sans-serif;background:var(--bg);color:var(--t);font-size:13px;line-height:1.5}
h1{font-size:22px;padding:18px 24px;background:linear-gradient(135deg,var(--p2),var(--p));border-bottom:1px solid var(--b)}
h1 span{display:block;font-size:12px;color:var(--d);font-weight:400;margin-top:4px}
h2{font-size:16px;color:#fff;padding:12px 20px;border-bottom:1px solid var(--b);margin:0}
.s{display:flex;flex-wrap:wrap;background:var(--p);border-bottom:1px solid var(--b)}
.s button{background:none;border:none;color:var(--d);padding:10px 16px;cursor:pointer;font-size:12px;border-bottom:2px solid transparent}
.s button:hover,.s button.on{background:var(--p2);color:#fff;border-color:var(--r)}
.tb{display:none;padding:16px 20px}
.tb.on{display:block}
.g{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
@media(max-width:800px){.g,.g3{grid-template-columns:1fr}}
.m{background:var(--p2);padding:10px 14px;border-radius:4px;border-left:3px solid var(--b)}
.m.gg{border-color:var(--gn)}.m.bb{border-color:var(--r)}.m.ww{border-color:var(--g)}
.m .l{font-size:10px;color:var(--d);text-transform:uppercase}
.m .v{font-size:18px;font-weight:700;margin-top:2px}
.m .s{font-size:10px;color:var(--d);margin-top:2px}
.card{background:var(--p);border:1px solid var(--b);border-radius:4px;padding:12px;margin:8px 0}
.card .t{font-size:12px;font-weight:600;margin-bottom:6px;color:var(--g)}
table{border-collapse:collapse;width:100%;font-size:11px;margin:6px 0}
th{background:var(--p2);color:var(--t);padding:5px 8px;text-align:left;border-bottom:1px solid var(--b)}
td{padding:4px 8px;border-bottom:1px solid var(--b)}
tr:nth-child(even)td{background:rgba(255,255,255,.02)}
.b{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600}
.b.u{background:rgba(56,173,169,.2);color:var(--gn)}
.b.d{background:rgba(233,69,96,.2);color:var(--r)}
.b.f{background:rgba(136,146,176,.2);color:var(--d)}
.b.w{background:rgba(255,165,0,.2);color:var(--o)}
.sg{background:linear-gradient(135deg,var(--p),var(--p2));padding:10px;border-radius:4px;margin:6px 0;border-left:3px solid var(--g)}
.sg.u{border-color:var(--gn)}.sg.d{border-color:var(--r)}
.sg .h{font-size:10px;color:var(--d)}
.sg .a{font-size:12px;font-weight:600;margin-top:3px}
.sg .m{font-size:10px;color:var(--d);margin-top:3px}
.nn{background:rgba(255,165,0,.08);padding:8px 12px;border-left:3px solid var(--o);margin:6px 0;font-size:11px}
</style>
</head>
<body>

<h1>Crude Oil War-Regime Analysis <span>Agentic pipeline: 15 stages, 80K+ rows, 10 war phases. Conditional-probability patterns, regime classifier, walk-forward backtest.</span></h1>

<div class="s" id="nav">
<button class="on" data-t="overview">Overview</button>
<button data-t="regime">Regime</button>
<button data-t="patterns">Patterns</button>
<button data-t="signals">Signals</button>
<button data-t="backtest">Backtest</button>
<button data-t="macro">Macro</button>
<button data-t="anomalies">Anomalies</button>
<button data-t="cross">Cross-Phase</button>
</div>

<div class="tb on" id="tb-overview">
<h2>Overview</h2>
<p>Pipeline: data ingestion → validator → primitives → window patterns → triplets → conformity → anomalies → day types → cross factor → FDR/Bayesian → synthesis → regime classifier → signal engine → backtester → macro overlay → dashboard. Single command regenerates everything.</p>
<div class="g3" id="kpi"></div>
<h3>Top Patterns (|bias| >= 60%, sorted by n)</h3>
<div id="pat"></div>
<div id="ovchart" style="display:none"></div>
</div>

<div class="tb" id="tb-regime">
<h2>Regime Classifier</h2>
<div class="g3" id="rpm"></div>
<div id="rpt"></div>
</div>

<div class="tb" id="tb-patterns">
<h2>Window Patterns (Phase 10 — current)</h2>
<div id="wint"></div>
</div>

<div class="tb" id="tb-signals">
<h2>Signals</h2>
<div id="sig"></div>
<h3>Strongest Playbook Patterns</h3>
<div id="sigt"></div>
</div>

<div class="tb" id="tb-backtest">
<h2>Walk-Forward Backtest</h2>
<div class="g3" id="btm"></div>
<div class="nn" id="btmc"></div>
</div>

<div class="tb" id="tb-macro">
<h2>Macro Regimes</h2>
<p>DXY, SPX, Gold, VI— API data fetched live. Macro-conditional crude return analysis.</p>
<div class="g3" id="mac"></div>
</div>

<div class="tb" id="tb-anomalies">
<h2>Anomalies</h2>
<div id="ant"></div>
</div>

<div class="tb" id="tb-cross">
<h2>Cross-Phase Similarity</h2>
<p>When current phase has limited data, patterns are borrowed from the most similar historical phase weighted by similarity x reliability.</p>
<h3>Phase 10 Similarity to Historical Phases</h3>
<div id="xst"></div>
<h3>Borrowed Patterns for Phase 10</h3>
<div id="xbt"></div>
</div>

<script>
D=__JSON_DATA__;
function f(v,d){d=d||2;if(v==null)return'-';if(typeof v!='number')return String(v);return v.toFixed(d);}
function pl(id){if(!D.phases)return'P'+id;var p=D.phases.find(function(x){return x.phase_id==id;});return p?'P'+p.phase_id+' '+(p.phase_label||'').substring(0,40):'P'+id;}
// Tab switching
(function(){
  var nav=document.getElementById('nav');
  if(!nav)return;
  var btns=nav.querySelectorAll('button');
  for(var i=0;i<btns.length;i++){
    btns[i].onclick=function(){
      for(var j=0;j<btns.length;j++)btns[j].classList.remove('on');
      var tabs=document.querySelectorAll('.tb');
      for(var j=0;j<tabs.length;j++)tabs[j].classList.remove('on');
      this.classList.add('on');
      var tb=document.getElementById('tb-'+this.dataset.t);
      if(tb)tb.classList.add('on');
    };
  }
})();

// Overview KPIs
try{
var l=D.l||{},r=D.cr||{},bt=D.bt||{},m=(bt.metrics||{}),e=(m.mc_expectancy_ci||[0,0]);
document.getElementById('kpi').innerHTML=
'<div class="m"><div class="l">Latest</div><div class="v">'+(l.d||'-')+'</div><div class="s">WTI $'+f(l.w)+' / Brent $'+f(l.b)+'</div></div>'+
'<div class="m '+(r.c>.7?'gg':'ww')+'"><div class="l">Phase</div><div class="v">'+(r.p?pl(r.p):'-')+'</div><div class="s">'+(r.c?Math.round(r.c*100)+'%':'-')+' confidence</div></div>'+
'<div class="m"><div class="l">Win Rate</div><div class="v">'+f(m.win_rate,1)+'%</div><div class="s">'+(m.total_trades||0)+' trades</div></div>'+
'<div class="m '+(m.sharpe>1?'gg':'')+'"><div class="l">Sharpe</div><div class="v">'+f(m.sharpe)+'</div><div class="s">walk-forward</div></div>'+
'<div class="m '+(e[0]>0?'gg':'bb')+'"><div class="l">Expectancy</div><div class="v">'+f(m.expectancy_pct,3)+'%</div><div class="s">MC95 ['+f(e[0],3)+', '+f(e[1],3)+'%]</div></div>'+
'<div class="m"><div class="l">Stages</div><div class="v">19</div><div class="s">--signals-only for daily</div></div>';
}catch(x){document.getElementById('kpi').innerHTML='<div class="m">Data error</div>';}

// Top patterns
try{
if(D.sp&&D.sp.length){
  var html='';
  for(var i=0;i<Math.min(8,D.sp.length);i++){
    var s=D.sp[i];var up=s.pct_up_next>s.pct_down_next;
    html+='<div class="sg '+(up?'u':'d')+'"><div class="h">'+(s.stream||'').replace('_session','')+' / '+(s.phase_label||'').substring(0,25)+' / '+s.day_archetype+'</div>'+
    '<div class="a"><span class="b '+(up?'u':'d')+'">'+(s.current_window||'')+'→'+(s.top_next_window||'')+' '+(up?'UP '+f(s.pct_up_next,0):'DOWN '+f(s.pct_down_next,0))+'%</span><span class="b f"> n='+s.n_observations+'</span>'+(s.low_confidence_flag?' <span class="b w">LOW</span>':'')+'</div></div>';
  }
  document.getElementById('pat').innerHTML=html;
}else document.getElementById('pat').innerHTML='<div class="nn">No strong patterns.</div>';
}catch(x){document.getElementById('pat').innerHTML='<div class="nn">Error loading patterns.</div>';}

// Regime
try{
if(D.cr){
  var r=D.cr;
  document.getElementById('rpm').innerHTML=
    '<div class="m gg"><div class="l">Current</div><div class="v">P'+r.p+'</div><div class="s">'+(r.c?Math.round(r.c*100)+'%':'')+' conf</div></div>'+
    '<div class="m"><div class="l">As of</div><div class="v">'+(r.d||'-')+'</div></div>'+
    '<div class="m"><div class="l">Label</div><div class="v">'+pl(r.p).substring(0,30)+'</div></div>';
}
if(D.phases){
  document.getElementById('rpt').innerHTML='<table><tr><th>P</th><th>Label</th><th>Start→End</th><th>Days</th><th>Conf</th></tr>'+
  D.phases.map(function(p){return'<tr><td>P'+p.phase_id+'</td><td>'+(p.phase_label||'').substring(0,35)+'</td><td>'+(p.start_datetime_ist||'').substring(0,10)+'→'+(p.end_datetime_ist||'').substring(0,10)+'</td><td>'+(p.n_trading_days||'-')+'</td><td>'+(p.confidence_1_to_5||'-')+'/5</td></tr>';}).join('')+
  '</table>';
}
}catch(x){}

// Window patterns
try{
if(D.ws&&D.ws.length){
  var p10=[];for(var i=0;i<D.ws.length;i++)if(D.ws[i].phase_id==10)p10.push(D.ws[i]);
  if(p10.length){
    var html='<table><tr><th>Window</th><th>Stream</th><th>n</th><th>UP%</th><th>DN%</th><th>Mean%</th><th>Conf</th></tr>';
    for(var i=0;i<p10.length;i++){
      var w=p10[i];
      html+='<tr><td>'+w.session_window_ist+'</td><td>'+w.stream.replace('_session','')+'</td><td>'+(w.n_valid||0)+'</td><td>'+f(w.pct_up,1)+'</td><td>'+f(w.pct_down,1)+'</td><td>'+f(w.mean_return_pct,3)+'</td><td>'+(w.low_confidence_flag?'<span class="b w">LOW</span>':'<span class="b u">OK</span>')+'</td></tr>';
    }
    document.getElementById('wint').innerHTML=html+'</table>';
  }else document.getElementById('wint').innerHTML='<div class="nn">No Phase 10 window data.</div>';
} else document.getElementById('wint').innerHTML='<div class="nn">No window data.</div>';
}catch(x){document.getElementById('wint').innerHTML='<div class="nn">Error loading window data.</div>';}

// Signals
try{
if(D.sg&&D.sg.length){
  var html='';
  for(var i=0;i<D.sg.length;i++){
    var s=D.sg[i];var dir=(s.direction||'').toLowerCase();var isU=dir=='up';
    html+='<div class="sg '+(isU?'u':'d')+'"><div class="h">'+(s.stream||'').replace('_session','')+' / P'+s.phase_id+' / '+(s.day_archetype||'-')+'</div><div class="a"><span class="b '+(isU?'u':'d')+'">'+(s.current_window||'')+'→'+(s.next_window||'')+' '+(s.direction||'')+' '+(isU?f(s.p_up,0):f(s.p_down,0))+'%</span> n='+(s.n_observations||s.n||'-')+'</div><div class="m">Entry '+f(s.entry_price,2)+' / SL '+f(s.stop_price,2)+' / TP '+f(s.target_price,2)+(s.final_position_fraction?' / Size '+Math.round(s.final_position_fraction*100)+'%':'')+'</div></div>';
  }
  document.getElementById('sig').innerHTML=html;
}else document.getElementById('sig').innerHTML='<div class="nn">No signals for current phase.</div>';

if(D.sp&&D.sp.length){
  var html='<table><tr><th>Stream</th><th>Phase</th><th>Day Type</th><th>Window→Next</th><th>n</th><th>UP%</th><th>DN%</th></tr>';
  for(var i=0;i<Math.min(25,D.sp.length);i++){
    var s=D.sp[i];
    html+='<tr><td>'+(s.stream||'').replace('_session','')+'</td><td>'+(s.phase_label||'').substring(0,18)+'</td><td>'+s.day_archetype+'</td><td>'+s.current_window+'→'+s.top_next_window+'</td><td>'+s.n_observations+'</td><td>'+f(s.pct_up_next,1)+'</td><td>'+f(s.pct_down_next,1)+'</td></tr>';
  }
  document.getElementById('sigt').innerHTML=html+'</table>';
}
}catch(x){}

// Backtest
try{
var mt=(D.bt||{}).metrics||{},e=(mt.mc_expectancy_ci||[0,0]);
if(mt.total_trades){
  document.getElementById('btm').innerHTML=
    '<div class="m '+(mt.win_rate>55?'gg':'')+'"><div class="l">Win Rate</div><div class="v">'+f(mt.win_rate,1)+'%</div><div class="s">'+mt.total_trades+' trades</div></div>'+
    '<div class="m gg"><div class="l">Profit Factor</div><div class="v">'+f(mt.profit_factor,2)+'</div></div>'+
    '<div class="m gg"><div class="l">Sharpe</div><div class="v">'+f(mt.sharpe,2)+'</div></div>'+
    '<div class="m gg"><div class="l">Sortino</div><div class="v">'+f(mt.sortino,1)+'</div></div>'+
    '<div class="m bb"><div class="l">Max DD</div><div class="v">'+f(mt.max_drawdown_pct,1)+'%</div></div>'+
    '<div class="m '+(e[0]>0?'gg':'ww')+'"><div class="l">Expectancy</div><div class="v">'+f(mt.expectancy_pct,3)+'%</div>';
  document.getElementById('btmc').innerHTML='<strong>MC 95% CI:</strong> Expectancy ['+f(e[0],3)+'%, '+f(e[1],3)+'%] '+(e[0]>0?'<span style="color:var(--gn)">POSITIVE</span>':'<span style="color:var(--r)">includes zero</span>');
}
}catch(x){}

// Macro
try{
document.getElementById('mac').innerHTML=
  '<div class="m"><div class="l">DXY</div><div class="v">Inverse</div><div class="s">Strong $ → crude lower</div></div>'+
  '<div class="m"><div class="l">SPX</div><div class="v">Risk-on/off</div><div class="s">SPX down → crude follows</div></div>'+
  '<div class="m"><div class="l">VIX</div><div class="v">Vol Regime</div><div class="s">High VIX → wider ranges</div></div>';
}catch(x){}

// Anomalies
try{
if(D.an&&D.an.length){
  var html='<table><tr><th>Date</th><th>Stream</th><th>Phase</th><th>Metric</th><th>z</th></tr>';
  for(var i=0;i<Math.min(15,D.an.length);i++){
    var a=D.an[i];
    html+='<tr><td>'+a.trade_date_ist+'</td><td>'+(a.__stream||'').replace('_daily','')+'</td><td>'+(a.phase_label||'').substring(0,18)+'</td><td>'+(a.anomaly_metric||'').replace('_rolling_z','')+'</td><td style="font-weight:bold;color:'+(a.z_value>0?'var(--r)':'var(--gn)')+'">'+f(a.z_value,2)+'</td></tr>';
  }
  document.getElementById('ant').innerHTML=html+'</table>';
}else document.getElementById('ant').innerHTML='<div class="nn">No anomalies.</div>';
}catch(x){}

// Cross-phase similarity
try{
if(D.xs&&D.xs.length){
  var sim10=null;
  for(var i=0;i<D.xs.length;i++)if(D.xs[i]['Unnamed: 0']==10)sim10=D.xs[i];
  if(sim10){
    var html='<table><tr><th>Phase</th><th>Label</th><th>Similarity</th></tr>';
    var keys=Object.keys(sim10).sort();
    for(var i=0;i<keys.length;i++){
      var k=keys[i];if(k=='Unnamed: 0'||k=='10.0')continue;
      var pid=parseFloat(k);if(isNaN(pid))continue;
      var ph=D.phases?D.phases.find(function(p){return p.phase_id==pid;}):null;
      var lbl=ph?(ph.phase_label||'').substring(0,35):'P'+pid;
      html+='<tr><td><strong>P'+pid+'</strong></td><td>'+lbl+'</td><td>'+f(sim10[k],3)+'</td></tr>';
    }
    document.getElementById('xst').innerHTML=html+'</table>';
  }
}
if(D.xb&&D.xb.length){
  var html='<table><tr><th>Window</th><th>Stream</th><th>Own UP%</th><th>Blended UP%</th><th>Own DN%</th><th>Blended DN%</th><th>From</th></tr>';
  for(var i=0;i<D.xb.length;i++){
    var b=D.xb[i];
    html+='<tr><td>'+b.session_window_ist+'</td><td>'+(b.stream||'').replace('_session','')+'</td><td>'+b.p_up_own+'</td><td style="font-weight:bold;color:'+(b.p_up_blended>b.p_up_own?'var(--gn)':'var(--r)')+'">'+b.p_up_blended+'</td><td>'+b.p_dn_own+'</td><td>'+b.p_dn_blended+'</td><td>P'+(b.borrowed_from_phase||'')+'</td></tr>';
  }
  document.getElementById('xbt').innerHTML=html+'</table>';
}else document.getElementById('xbt').innerHTML='<div class="nn">No cross-phase data yet. Run cross_phase_engine.py first.</div>';
}catch(x){document.getElementById('xbt').innerHTML='<div class="nn">Error loading cross-phase data.</div>';}

console.log('Dashboard loaded');
</script>
</body>
</html>'''

    # Replace the data placeholder (NOT an f-string — this is plain .replace())
    html = HTML.replace('__JSON_DATA__', json_str)
    (BASE / 'dashboard_v3.html').write_text(html, encoding='utf-8')
    print(f">>> wrote dashboard_v3.html ({len(html):,} chars, single self-contained file)")