import { fmt } from '../data';
export default function CrossPhase({ data }) {
  const xs = data.xs || []; const xb = data.xb || []; const phases = data.phases || [];

  let sim10 = null;
  for (let i = 0; i < xs.length; i++) {
    if (xs[i]['Unnamed: 0'] === 10) { sim10 = xs[i]; break; }
  }

  return (
    <>
      <h2>🔗 Cross-Phase Similarity & Pattern Borrowing</h2>
      <p>When the current phase has limited data, patterns are borrowed from the most similar historical phase using a cosine-distance similarity score across 4 dimensions: volatility profile (30%), direction distribution (30%), return distribution (20%), magnitude-tier distribution (20%). The blend weight is α = similarity × reliability, capped at 50%. As the current phase accumulates data, borrowing automatically decreases.</p>

      <h3>Phase 10 Similarity to All Historical Phases</h3>
      {sim10 ? <table><thead><tr><th>Phase</th><th>Label</th><th>Similarity</th><th>Trading Days</th></tr></thead>
        <tbody>{Object.entries(sim10)
          .filter(([k]) => k !== 'Unnamed: 0' && k !== '10.0')
          .sort(([, a], [, b]) => b - a)
          .map(([k, v]) => {
            const pid = parseFloat(k); if (isNaN(pid)) return null;
            const ph = phases.find(p => p.phase_id === pid);
            return <tr key={pid}>
              <td><strong>P{pid}</strong></td>
              <td>{ph ? (ph.phase_label || '').substring(0, 40) : ''}</td>
              <td style={{ fontWeight: 'bold', color: v > 0.8 ? 'var(--gn)' : v > 0.6 ? 'var(--g)' : 'var(--d)' }}>{fmt(v, 3)}</td>
              <td>{ph?.n_trading_days || '-'}</td>
            </tr>;
          })
        }</tbody>
      </table> : <div className="note">Run cross_phase_engine.py to generate similarity data.</div>}

      <h3>📋 Borrowed Patterns for Phase 10</h3>
      <p>All 18 Phase-10 windows are currently blended with Phase 7 (Hormuz major war, similarity 0.886). The blended probabilities reflect both own and borrowed signal.</p>

      {xb.length ? <table><thead><tr><th>Window</th><th>Stream</th><th>Own UP%</th><th>Blended UP%</th><th>Own DN%</th><th>Blended DN%</th><th>Borrowed From</th></tr></thead>
        <tbody>{xb.map((b, i) => (
          <tr key={i}>
            <td><strong>{b.session_window_ist}</strong></td>
            <td>{b.stream?.replace('_session', '')}</td>
            <td>{b.p_up_own}%</td>
            <td style={{ fontWeight: 'bold', color: b.p_up_blended > b.p_up_own ? 'var(--gn)' : 'var(--r)' }}>{b.p_up_blended}%</td>
            <td>{b.p_dn_own}%</td>
            <td>{b.p_dn_blended}%</td>
            <td>P{b.borrowed_from_phase || '—'} (α={b.borrow_weight || '0'})</td>
          </tr>
        ))}</tbody>
      </table> : <div className="note">No borrowed patterns yet. This is normal if Phase 10 has enough data or cross_phase_engine hasn't been run recently.</div>}

      <div className="note"><strong>Why Phase 7?</strong> Phase 7 (Hormuz major war, 10 days, ATR 1.75%) and Phase 10 (negotiation, 9 days, ATR 1.36%) share an identical intraday microstructure: india_midday UP → europe_midday DOWN. The market is coiled in both, producing the same daily rhythm despite opposite narratives. This validates the cross-phase borrowing thesis.</div>
    </>
  );
}