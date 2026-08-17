import { fmt } from '../data';
export default function Backtest({ data }) {
  const m = (data.bt || {}).metrics || {};
  const e = m.mc_expectancy_ci || [0, 0];
  const s = m.mc_sharpe_ci || [0, 0];
  return (
    <>
      <h2>🔄 Walk-Forward Backtest</h2>
      <p>Expanding-window walk-forward validation. Entry at next-bar open. Stop/target = ATR × magnitude tier multiplier (Q1=0.5×, Q5=2.0×). Position sizing: Kelly ∩ vol-target (15% ann). Drawdown controls: reduce 50% at 5% DD, flat at 10% DD. Monte Carlo 95% CI on all metrics (2,000 resamples).</p>

      {m.total_trades ? <>
        <div className="grid3">
          <div className="metric good"><div className="lbl">Win Rate</div><div className="val">{fmt(m.win_rate, 1)}%</div><div className="sub">{m.total_trades} trades</div></div>
          <div className="metric good"><div className="lbl">Profit Factor</div><div className="val">{fmt(m.profit_factor, 2)}</div><div className="sub">gross win / gross loss</div></div>
          <div className="metric good"><div className="lbl">Sharpe</div><div className="val">{fmt(m.sharpe)}</div><div className="sub">MC 95% CI [{fmt(s[0])}, {fmt(s[1])}]</div></div>
          <div className="metric good"><div className="lbl">Sortino</div><div className="val">{fmt(m.sortino, 1)}</div><div className="sub">downside-risk adjusted</div></div>
          <div className="metric bad"><div className="lbl">Max Drawdown</div><div className="val">{fmt(m.max_drawdown_pct, 1)}%</div><div className="sub">peak-to-trough</div></div>
          <div className="metric" style={{ borderLeftColor: e[0] > 0 ? 'var(--gn)' : 'var(--r)' }}>
            <div className="lbl">Expectancy / Trade</div><div className="val">{fmt(m.expectancy_pct, 3)}%</div>
            <div className="sub">MC 95% CI [{fmt(e[0], 3)}%, {fmt(e[1], 3)}%] — {e[0] > 0 ? <span style={{color:'var(--gn)'}}>POSITIVE (edge not due to luck)</span> : <span style={{color:'var(--r)'}}>includes zero</span>}</div>
          </div>
        </div>
        <div className="note"><strong>Key insight:</strong> The Monte Carlo 95% CI for expectancy is [{fmt(e[0], 3)}%, {fmt(e[1], 3)}%] — {e[0] > 0 ? 'the lower bound is POSITIVE, meaning the strategy has statistically significant edge at 95% confidence.' : 'the lower bound includes zero, meaning the strategy edge is not yet statistically significant at 95%. More data needed.'}</div>
      </> : <div className="note bad">No backtest data available. Run the full pipeline (with walkforward_backtest step) to generate.</div>}

      <h3>⚙️ Risk Configuration</h3>
      <div className="grid3">
        <div className="metric"><div className="lbl">Max Position</div><div className="val">25%</div><div className="sub">of equity per Kelly cap</div></div>
        <div className="metric"><div className="lbl">Target Vol</div><div className="val">15% annual</div><div className="sub">volatility targeting</div></div>
        <div className="metric warn"><div className="lbl">Reduce at DD</div><div className="val">5%</div><div className="sub">50% position reduction</div></div>
        <div className="metric bad"><div className="lbl">Flat at DD</div><div className="val">10%</div><div className="sub">stop trading</div></div>
        <div className="metric"><div className="lbl">Slippage</div><div className="val">2 bps</div><div className="sub">+ Rs 20/lot commission</div></div>
      </div>
    </>
  );
}