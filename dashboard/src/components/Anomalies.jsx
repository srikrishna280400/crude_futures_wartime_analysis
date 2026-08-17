import { fmt } from '../data';
export default function Anomalies({ data }) {
  const an = data.an || [];
  return (
    <>
      <h2>⚠️ Anomaly Detection</h2>
      <p>Rolling z-scores (|z| &gt; 2.5, window = 20 trading days) computed on: intraday volatility (realized vol proxy), daily move magnitude, max favorable/adverse excursion, and volume. Flagged rows are candidates for news event correlation — heuristic only, not manipulation claims.</p>
      {an.length ? <table><thead><tr><th>Date</th><th>Stream</th><th>Phase</th><th>Metric</th><th>|z|</th></tr></thead>
        <tbody>{an.slice(0, 15).map((a, i) =>
          <tr key={i}>
            <td>{a.trade_date_ist || ''}</td>
            <td>{(a.__stream || '').replace('_daily', '')}</td>
            <td>{(a.phase_label || '').substring(0, 20)}</td>
            <td>{(a.anomaly_metric || '').replace('_rolling_z', '').replace('_z', '')}</td>
            <td style={{ fontWeight: 'bold', color: (a.z_value || 0) > 0 ? 'var(--r)' : 'var(--gn)' }}>{fmt(a.z_value, 2)}</td>
          </tr>
        )}</tbody>
      </table> : <div className="note good">No anomalies flagged. The market is behaving within normal volatility bounds.</div>}
    </>
  );
}