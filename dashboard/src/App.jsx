import { useState, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import Overview from './components/Overview';
import Regime from './components/Regime';
import Patterns from './components/Patterns';
import Signals from './components/Signals';
import Backtest from './components/Backtest';
import CrossPhase from './components/CrossPhase';
import Anomalies from './components/Anomalies';
import { loadData } from './data';
import './App.css';

const TABS = [
  { id: 'overview', label: '📊 Overview', color: '#f7b733' },
  { id: 'regime', label: '🤖 Regime', color: '#38ada9' },
  { id: 'patterns', label: '📈 Patterns', color: '#3c6382' },
  { id: 'signals', label: '🎯 Signals', color: '#e94560' },
  { id: 'backtest', label: '🔄 Backtest', color: '#e77f67' },
  { id: 'cross', label: '🔗 Cross-Phase', color: '#a29bfe' },
  { id: 'anomalies', label: '⚠️ Anomalies', color: '#fdcb6e' },
];

export default function App() {
  const [active, setActive] = useState('overview');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData().then(d => {
      if (d) setData(d);
      else setError('Failed to load dashboard data. Run the pipeline first.');
      setLoading(false);
    }).catch(e => {
      setError(e.message);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="app"><div className="loading"><div className="spinner"></div><p>Loading dashboard data...</p></div></div>;
  if (error) return <div className="app"><div className="loading"><p style={{color:'var(--r)'}}>❌ {error}</p></div></div>;
  if (!data) return <div className="app"><div className="loading"><p>No data available.</p></div></div>;

  const renderTab = () => {
    switch (active) {
      case 'overview': return <Overview data={data} />;
      case 'regime': return <Regime data={data} />;
      case 'patterns': return <Patterns data={data} />;
      case 'signals': return <Signals data={data} />;
      case 'backtest': return <Backtest data={data} />;
      case 'cross': return <CrossPhase data={data} />;
      case 'anomalies': return <Anomalies data={data} />;
      default: return <Overview data={data} />;
    }
  };

  return (
    <div className="app">
      <header>
        <h1>🛢️ Crude Oil War-Regime Analysis</h1>
        <p className="sub">Agentic pipeline: 19 stages, 80K+ rows, 10 war phases. Conditional-probability patterns + regime classifier + walk-forward backtest.</p>
        <div className="header-meta">
          <span>{data.p?.length || 0} trading days</span>
          <span>{data.phases?.length || 0} phases</span>
          <span>L: {data.l?.d || '-'}</span>
          <span>WTI ${data.l?.w?.toFixed(2) || '-'} / BRENT ${data.l?.b?.toFixed(2) || '-'}</span>
        </div>
      </header>

      <nav className="tabs">
        {TABS.map(t => (
          <button key={t.id} className={`tab-btn ${active === t.id ? 'active' : ''}`}
            style={{ '--accent': t.color }}
            onClick={() => setActive(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main className="content">
        <AnimatePresence mode="wait">
          <motion.div key={active} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
            {renderTab()}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}