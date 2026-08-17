import { fmt, phaseLabel } from '../data';
export default function Regime({ data }) {
  const r = data.cr || {}; const phases = data.phases || [];
  return (
    <>
      <h2>🤖 War Regime Classifier</h2>
      <p>A calibrated RandomForest (500 trees, isotonic calibration) driven by 99 features: session returns, volatility, spreads, and macro data (DXY/SPX/VIX/Gold). Classes with &lt;3 samples are dropped; adaptive CV folds. The classifier retrains on every pipeline run.</p>
      <div className="grid3">
        <div className="metric good"><div className="lbl">Current</div><div className="val">{r.p ? 'P' + r.p : '-'}</div><div className="sub">{r.c ? Math.round(r.c * 100) + '% confidence' : ''}</div></div>
        <div className="metric"><div className="lbl">As of Date</div><div className="val">{r.d || '-'}</div><div className="sub">last classified data point</div></div>
        <div className="metric"><div className="lbl">Classifier</div><div className="val">RF + Calibration</div><div className="sub">500 trees, isotonic, adaptive CV</div></div>
      </div>
      <h3>📅 10-Phase Timeline</h3>
      <table><thead><tr><th>Phase</th><th>Label</th><th>Start → End</th><th>Days</th><th>Conf</th></tr></thead>
        <tbody>{phases.map(p =>
          <tr key={p.phase_id} style={{ background: p.phase_id === (r.p || 0) ? 'rgba(56,173,169,0.1)' : '' }}>
            <td><strong>P{p.phase_id}</strong></td>
            <td>{(p.phase_label || '').substring(0, 40)}</td>
            <td>{(p.start_datetime_ist || '').substring(0, 10)} → {(p.end_datetime_ist || '').substring(0, 10)}</td>
            <td>{p.n_trading_days || '-'}</td>
            <td>{p.confidence_1_to_5 || '-'}/5</td>
          </tr>
        )}</tbody>
      </table>
      <div className="note"><strong>Why phases matter:</strong> Phase 1 (full-scale war) had ATR 2.95% while Phase 10 (negotiation) has ATR 1.36% — completely different volatility regimes. All magnitude thresholds and position sizing are phase-relative.</div>
    </>
  );
}