import { fmt } from '../data';
export default function Patterns({ data }) {
  const ws = data.ws || [];
  const p10 = ws.filter(w => w.phase_id === 10);

  return (
    <>
      <h2>📈 Window Patterns (Phase 10 — Current)</h2>
      <p>Every MCX trading day (09:00–23:30 IST) is divided into session windows. Each window's direction bias is computed from Phase-10 data. Borrowed patterns from Phase 7 (similarity 0.886) are shown in the <strong>Cross-Phase</strong> tab.</p>

      {p10.length ? <table><thead><tr><th>Window</th><th>Stream</th><th>n</th><th>UP%</th><th>DOWN%</th><th>FLAT%</th><th>Mean%</th><th>Conf</th></tr></thead>
        <tbody>{p10.map((w, i) =>
          <tr key={i}>
            <td><strong>{w.session_window_ist}</strong></td>
            <td>{w.stream?.replace('_session', '')}</td>
            <td>{w.n_valid || 0}</td>
            <td style={{ color: (w.pct_up || 0) > 50 ? 'var(--gn)' : 'var(--d)' }}>{fmt(w.pct_up, 1)}</td>
            <td style={{ color: (w.pct_down || 0) > 50 ? 'var(--r)' : 'var(--d)' }}>{fmt(w.pct_down, 1)}</td>
            <td>{fmt(w.pct_flat, 1)}</td>
            <td>{fmt(w.mean_return_pct, 3)}</td>
            <td>{w.low_confidence_flag ? <span className="badge low">LOW</span> : <span className="badge up">OK</span>}</td>
          </tr>
        )}</tbody>
      </table> : <div className="note">No Phase 10 window data yet.</div>}

      <div className="note"><strong>Key directional edges (Phase 10):</strong> india_midday has a UP bias (~56%), europe_midday has a DOWN bias (~61%), mcx_tail has a UP bias (~39–50%). These form the basis of a daily trading plan.</div>
    </>
  );
}