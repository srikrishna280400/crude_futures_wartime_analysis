# Concept Citations — conformity_engine.py

Frameworks tested against the data, with provenance.

## (a) Mean-reversion / AR(1) half-life
- Half-life = -ln(2)/ln(phi), where phi is AR(1) coefficient on |return| series per phase × window.
- Reference: standard time-series econometrics (Box-Jenkins ARIMA family).
- 'Trading in the Zone' (Douglas) — expectation that regime transitions produce mean-reverting impulse around new equilibrium.

## (b) Volatility clustering
- |r| lag-1 autocorrelation as proxy for clustering (Tauchen-style).
- Reference: Engle (1982) ARCH; Bollerslev (1986) GARCH — both document clustering in financial returns.

## (c) Session-overlap liquidity effect
- 1/std_return as liquidity proxy in the session-overlap window (us_open 20:00-23:00 IST).
- Reference: Harris (1986) 'Trading and Exchanges' — overlap sessions show deeper books.

## (d) Momentum / trendiness
- Lag-1 autocorrelation of daily net returns per phase.
- Reference: Jegadeesh & Titman (1993) momentum effect.
- 'Trend Following' (Covel) — regime-conditioned persistence.

## Reference folder contents (transcripts)
- `temp_audio_1.txt` — Claude for financial analysis (Anthropic product context).
- `temp_audio_2.txt` — Long/short equity hedge fund construction tutorial (general quant).
- `temp_audio_3.txt` — Hedging primer (general definitions).
- `temp_audio_4.txt` — Bayesian statistics (MIT lecture).
- Note: transcripts are general finance/quant material, NOT crude-oil-specific. Used only for general framework context.

## Methodology note
Each computed statistic is also tagged with sample size n and a LOW-CONFIDENCE flag for n<5.
