import { fmt, phaseLabel } from '../data';
export default function Overview({ data }) {
  const l = data.l || {}; const r = data.cr || {};
  const bt = data.bt || {}; const m = bt.metrics || {};
  const e = m.mc_expectancy_ci || [0, 0];
  const sp = data.sp || [];

  return (
    <>
      <h2>📊 Overview</h2>
      <p>19-stage agentic pipeline from raw OHLCV data to actionable conditional-probability trading signals. Every number carries its sample size <strong>n</strong>. Patterns with n&lt;5 are flagged <span className="badge low">LOW-CONFIDENCE</span>.</p>

      <div className="grid3">
        <div className="metric"><div className="lbl">Latest Date</div><div className="val">{l.d || '-'}</div><div className="sub">WTI ${fmt(l.w)} · Brent ${fmt(l.b)}</div></div>
        <div className="metric good"><div className="lbl">Current Phase</div><div className="val">{r.p ? phaseLabel(data.phases, r.p) : '-'}</div><div className="sub">{r.c ? Math.round(r.c * 100) + '% confidence' : ''}</div></div>
        <div className="metric"><div className="lbl">Trading Days</div><div className="val">{data.p?.length || 0}</div><div className="sub">Mar 2 – {l.d || 'present'}</div></div>
        {m.total_trades ? <>
          <div className="metric good"><div className="lbl">Win Rate</div><div className="val">{fmt(m.win_rate, 1)}%</div><div className="sub">{m.total_trades} trades (walk-forward)</div></div>
          <div className="metric good"><div className="lbl">Sharpe</div><div className="val">{fmt(m.sharpe)}</div><div className="sub">annualized, walk-forward</div></div>
          <div className="metric" style={{ borderLeftColor: e[0] > 0 ? 'var(--gn)' : 'var(--r)' }}>
            <div className="lbl">Expectancy</div><div className="val">{fmt(m.expectancy_pct, 3)}%</div>
            <div className="sub">MC 95% CI [{fmt(e[0], 3)}%, {fmt(e[1], 3)}%] — {e[0] > 0 ? <span style={{color:'var(--gn)'}}>POSITIVE</span> : <span style={{color:'var(--r)'}}>includes zero</span>}</div>
          </div>
        </> : <div className="metric warn"><div className="lbl">Backtest</div><div className="val">Pending</div><div className="sub">Run full pipeline with walkforward_backtest</div></div>}
      </div>

      <h3>🎯 Top High-Confidence Patterns (|bias| ≥ 60%)</h3>
      {sp.length ? <div className="grid">
        {sp.slice(0, 8).map((s, i) => {
          const up = s.pct_up_next > s.pct_down_next;
          return <div key={i} className={`signal ${up ? 'up' : 'down'}`}>
            <div className="h">{s.stream?.replace('_session', '')} / {(s.phase_label || '').substring(0, 25)} / {s.day_archetype}</div>
            <div className="a"><span className={`badge ${up ? 'up' : 'down'}`}>{s.current_window}→{s.top_next_window} {up ? 'UP' : 'DOWN'} {up ? fmt(s.pct_up_next, 0) : fmt(s.pct_down_next, 0)}%</span> <span className="badge flat">n={s.n_observations}</span>{s.low_confidence_flag ? <span className="badge low">LOW</span> : ''}</div>
          </div>;
        })}
      </div> : <div className="note good">No strong patterns yet. Phase 10 sample is small — cross-phase borrowing fills most gaps. See <strong>Cross-Phase</strong> tab.</div>}

      <div className="note"><strong>How to read:</strong> "IF day type = X AND window = Y THEN next window → UP/DOWN with Z% probability." These are <strong>conditional probabilities</strong>, not predictions. Always combine with your own risk management and current news.</div>
    </>
  );
}