# Product Requirements Document

**Product:** Multi-Sport Quantitative Betting & Trading Terminal  
**Version:** 0.5  
**Status:** Draft  
**Platforms:** Web/Desktop, iOS, Android  
**Primary Research Experience:** Web/Desktop  
**Initial Sport:** Soccer  
**Initial Mode:** Research, backtesting, market analysis, paper trading

---

## 1. Product Summary

We are building a cross-platform, multi-sport quantitative betting and trading terminal that helps users discover, analyze, price, test, track, and eventually execute sports-market positions using model-derived fair probabilities and market data.

The product combines sports data, historical and current prices, sport-specific predictive models, fair-value pricing, expected-value analysis, closing-line-value tracking, strategy backtesting, paper trading, portfolio and risk management, watchlists, alerts, parlay analysis, and an agentic interface exposed through MCP.

The product should feel like a professional sports research and trading terminal rather than a sportsbook or picks application.

## 2. Vision

Users should move through one lifecycle across desktop and mobile:

**Discover → Analyze → Price → Decide → Track → Review → Learn → Execute**

The same state should follow the user across devices: portfolio, watchlists, alerts, strategies, positions, model context, and agent context.

## 3. Problem

Sports-market analysis is fragmented across fixtures, advanced statistics, injuries, historical data, sportsbook odds, prediction markets, models, backtests, bet tracking, alerts, portfolio management, and execution.

Traditional sportsbooks primarily answer: **What can you bet on?**

This product should answer: **What is this outcome actually worth, how reliable is that estimate, and how does it compare with the price available now?**

## 4. Core Product Principles

### 4.1 Price, Not Picks

A good team is not automatically a good bet. The platform should center fair probability, market probability, available price, vig, expected value, uncertainty, and historical model/strategy performance.

### 4.2 Model Outcomes, Then Price Markets

Sport-specific models should produce underlying probability distributions. A deterministic pricing layer should then translate those distributions into supported market probabilities and fair odds.

### 4.3 Multi-Sport Core, Sport-Specific Intelligence

Portfolio, strategy, alerts, execution, account state, MCP, and client architecture should be sport-neutral. Features, statistical assumptions, model training, probability distributions, and sport-specific pricing remain sport-specific.

### 4.4 Research Before Execution

The progression is:

**Backtest → Paper trade → Human-confirmed execution → Limited automation → Scale only after validation**

### 4.5 Deterministic Critical Logic

LLMs must not be authoritative for probability calculation, vig removal, EV, P&L, bankroll/risk calculations, settlement, or execution decisions.

### 4.6 Transparent and Reproducible

Predictions and backtests must identify dataset version, feature version, model version, strategy version, market-data provenance, and timestamps.

### 4.7 Provider Independence

The product must support multiple sports-data providers, sportsbook-odds sources, prediction-market venues, and execution venues without leaking provider-specific schemas throughout the platform.

### 4.8 Low-Cost Validation First

V1 must be testable end-to-end using free tiers, demo/test environments, replay datasets, captured fixtures, public market data, and local emulation wherever practical. Paid provider plans should be introduced only when a specific capability cannot be validated adequately through those mechanisms.

## 5. Target Users

Initial users are analytically minded sports bettors/traders who want model-vs-market analysis, strategy testing, risk visibility, and one place to monitor opportunities and positions.

The architecture should remain compatible with a future multi-user commercial product.

## 6. Sports Coverage Roadmap

- **V1:** Soccer
- **V2:** NBA/WNBA
- **V3:** NFL
- **V4:** ATP/WTA
- **V5+:** MLB, NHL, golf, MMA/boxing, cricket, esports, and other sports where data and market coverage justify support

## 7. Canonical Domain Hierarchy

**Sport → Competition → Season → Event → Participants → Markets → Selections → Quotes**

The model must not assume exactly two teams. Participants may be teams, players, doubles pairs, fighters, drivers, golfers, or other competition entities.

## 8. Competition-Aware Modeling

Men's and women's competitions must not be blindly pooled. Models may share architecture while retaining competition-aware parameters, features, training windows, calibration, and evaluation.

## 9. Core User Journey

1. Discover events or model-vs-market discrepancies.
2. Open an event terminal.
3. Compare model fair value with prices across venues.
4. Inspect model explanation, freshness, uncertainty, and historical performance.
5. Save, alert, paper trade, or include the selection in a parlay analysis.
6. Monitor portfolio exposure and position value.
7. Review closing-line value and realized outcomes.
8. Eventually prepare and confirm supported real-money execution.

## 10. MVP Scope

V1 is soccer pregame analysis with:

- Event and participant discovery
- Current sportsbook prices
- Prediction-market prices/order books where available
- Historical results and odds sufficient for model/backtest validation
- Soccer team-strength / score-distribution model
- 1X2
- Totals
- Team totals
- Handicaps
- Both-teams-to-score
- Winning-margin / custom score-derived contracts
- Fair probability and fair odds
- No-vig market probability
- EV and edge
- Walk-forward backtesting
- Paper positions
- Portfolio/risk basics
- Watchlists and alerts
- Web terminal
- Mobile discovery/monitoring/portfolio/alerts/agent
- MCP/agent research workflows

## 11. MVP Non-Goals

- Automated real-money execution
- True live/in-play fair-value modeling
- Full player-prop coverage
- Every sport
- Full same-game-parlay correlation modeling for every market
- Full backtest construction UX on mobile
- Guaranteed predictions or “locks”

## 12. Soccer Modeling

The initial model should prioritize interpretability and probability distributions:
team strength/Elo, attack/defense and home advantage, followed by independent
Poisson and Dixon-Coles score models. Dynamic/bivariate Poisson, xG-enhanced and
Bayesian/richer statistical models are challengers. Probability-producing ML
(logistic or gradient-boosted models), market-aware challengers and calibrated
ensembles follow strong statistical baselines, not replace them by default.
The [research ladder](../adr/ADR-008-soccer-baseline-model.md) is an evaluation
sequence, not a requirement to productionize every model or select an ML library.

xG/xGA and shot-quality information are high-priority features when legally and
operationally available with point-in-time evidence. An eligible goals/results
dataset can support the earliest baseline without xG or paid provider dependence.
No soccer model is considered an improvement without robust chronological
forward/OOS improvement against appropriate simpler baselines and the no-vig
market consensus on comparable tasks/horizons. Negative findings are valid.
The market is a strong benchmark, not assumed correct or unbeatable.

Models produce probabilities/distributions, never BET/NO_BET. Initial score models
produce a joint score distribution; market-specific ML probabilities do not by
themselves provide joint-model coverage. Market-aware models and ensembles must
disclose odds inputs; their market comparison is not independent fundamentals skill.

## 13. Recency

Recency weighting is tested, not assumed. Compare rolling windows, exponential
decay and dynamic latent team strength. Tune competition-aware parameters within
chronological training/validation windows, never a universal decay rate.

## 14. Pricing

A deterministic pricing engine maps outcome distributions to markets. It must support fair probability, fair odds, vig-removal comparisons, and reproducible pricing versions.

No-vig methods are pluggable and versioned: MULTIPLICATIVE, SHIN and POWER are
candidates, not universally ranked choices. Market consensus is a reproducible
benchmark with pinned source/venue coverage, quotes, freshness, aggregation and
de-vig policy, not an executable price. Missing benchmark coverage stays explicit.

## 15. Market Taxonomy

Markets must be canonical and provider-neutral. Initial types include moneyline/1X2, spread/handicap, totals, team totals, BTTS, winning margin, and prediction-market binary contracts that can be expressed from the underlying outcome distribution.

## 16. Quotes and Venues

A **venue** is where a price is offered or tradable. A **data source** is how we obtained the data. They are separate concepts.

Examples:

- Venue: Bovada; source: sportsbook-odds aggregator
- Venue: Pinnacle; source: sportsbook-odds aggregator
- Venue: Kalshi; source: Kalshi API
- Venue: Polymarket; source: Polymarket API

The product must retain price provenance and timestamp freshness.

## 17. Prediction-Market Venues

Kalshi and Polymarket should be treated as first-class market-data venues in V1 where their APIs expose relevant sports contracts. Real-money execution remains a later capability and is separately permissioned from public market-data ingestion.

## 18. Odds Formats

The UI should support decimal, American, and implied-probability views without changing the canonical internal probability representation.

## 19. Expected Value

For a decimal price `d` and model win probability `p`, the basic EV representation is:

`EV = p × d - 1`

Fees, push probability, partial settlement, exchange spread, and execution assumptions must be included where relevant.

Raw estimated EV, confidence/reliability and actionable edge are distinct. Model
probability and executable price determine estimated EV under stated costs;
model uncertainty and market/de-vig uncertainty inform strategy qualification or
abstention. No universal confidence-adjusted formula or fixed edge threshold is
assumed. Market disagreement alone is insufficient to act.

## 20. Model Confidence

ModelUncertainty is first-class evidence distinct from outcome probability:
calibration uncertainty, sample support, competition coverage, freshness, parameter
uncertainty, stability, model disagreement and forecast-horizon effects. Preserve
method/version, scope, missing evidence and limitations; no universal estimator
or opaque confidence score is prescribed.

ForecastHorizon distinguishes OPEN, T_MINUS_24H, T_MINUS_6H, T_MINUS_60M and
LATEST_PREMATCH conceptually. Version exact cutoff/tolerance and kickoff-change
policies, retain actual decision time and compare like horizons. Lineups, injuries,
market information and CLV interpretation differ by horizon. These are Phase 4+
requirements, not currently implemented model contracts.

## 21. Backtesting

Backtesting must be chronologically valid and leakage-safe: every feature, quote
and context dependency requires evidenced `available_at <= decision_time`, and
pregame decisions precede kickoff. Conceptual as-of reads must not substitute
effective/observed time for availability or consult present state as historical
truth. Separate later outcomes from decision inputs; unknown availability and
existing replay-only datasets remain ineligible.

Primary predictive metrics are log loss, Brier score and calibration/reliability,
with deltas versus the no-vig market consensus and simpler statistical baselines.
Economic/strategy metrics are estimated EV, CLV, realized ROI/P&L, drawdown,
volatility and sample count. Segment by league, season, forecast horizon, market,
odds bucket and selection type. Add dependence-aware bootstrap/confidence intervals
as the framework matures. Accuracy or win rate is not the main optimization target.

Positive CLV can indicate earlier information discovery, but alone is not proof of
sustainable profitability. Retain closing-price policy and continue tracking
outcomes, calibration, EV, sample size, uncertainty and robustness. Closing odds
must not leak into earlier-horizon predictions. See
[evaluation policy](../adr/ADR-036-soccer-model-evaluation-and-market-benchmarking.md).

## 22. Strategy

Strategies are deterministic, versioned rules reusable across backtesting, paper trading, scanning, and later execution.

Strategies qualify estimated edges using explicit reliability and execution
assumptions, including abstention; models do not make betting decisions. Research
fractional Kelly as the preferred staking research benchmark, alongside simpler
sizing comparisons, not as an automatic production default.
Full Kelly is not the default. Any eventual Kelly-style size is constrained by
maximum position, event, participant and correlated exposure, bankroll-at-risk,
daily/weekly loss controls and confidence/model quality. No real-money or current
risk implementation change follows from this requirement.

## 23. Opportunity

An opportunity is the evaluated relationship between a model estimate and an available price under a specific strategy and timestamp. It is not synonymous with “pick.”

## 24. Portfolio and Risk

Track bankroll/cash ledger, positions, realized/unrealized P&L, event/sport/participant exposure, and configurable risk limits. Correlation-aware exposure is a later enhancement.

## 25. Parlays

Cross-event probabilities may be multiplied only where independence is justified. Same-event/correlated selections require a joint distribution, simulation, or validated correlation model.

Prefer exact score-matrix enumeration for soccer same-game legs fully expressible
by that joint distribution. Expose joint-model coverage (EXACT, SIMULATED,
INDEPENDENCE_ASSUMED, UNSUPPORTED) separately from confidence; exact computation
does not eliminate model uncertainty. Unsupported material dependencies yield no
invented joint probability or EV, including from the agent.

Parlay analysis must evaluate the **joint position**, not merely the apparent strength of individual legs. Supported evaluations should include offered price, break-even probability, fair joint probability, fair odds, EV, correlation treatment, uncertainty/confidence, and risk where available.

Parlay Lab should also support leg-level attribution, incremental EV/risk analysis, single-leg-removal counterfactuals, straight-bet comparison, and price sensitivity as those capabilities become available. The detailed product behavior is defined in [`feature-specs/parlay-lab.md`](feature-specs/parlay-lab.md).

## 26. Watchlists

Users can track participants, events, markets, selections, and strategies.

## 27. Alerts

Alerts may trigger on price, edge, EV, model update, market movement, availability, or position conditions. Supported channels include in-app and mobile push initially, with email optional.

## 28. Agent

The agent is a first-class interface for discovery, explanation, backtests, watchlists, alerts, portfolio queries, and paper-trading actions. It orchestrates deterministic backend capabilities rather than reimplementing them.

## 29. MCP

MCP should expose stable tools such as `search_events`, `get_markets`, `get_prediction`, `find_opportunities`, `run_backtest`, `get_portfolio`, `create_alert`, `create_paper_position`, and `evaluate_parlay`.

## 30. Agent Safety

Read tools are distinct from writes. Real-money actions eventually require prepare/review/confirm/execute semantics. The agent must never bypass the risk engine.

## 31. Live Revaluation

True live fair value is explicitly post-MVP. It requires sport-specific live state such as score/time/red cards/xG for soccer or score/clock/lineups for basketball.

## 32. UX Direction

The product should look like a serious market/research terminal: dark or neutral analytical presentation, dense but readable tables, progressive disclosure, clear Model vs Market vs EV separation, visible freshness/uncertainty, and no casino-style gamification.

## 33. Web/Desktop Surfaces

- Discover
- Markets
- Event Terminal
- Portfolio
- Watchlists & Alerts
- Parlay Lab
- Strategies & Backtests
- Models/Research
- Agent

## 34. Mobile Surfaces

Likely primary navigation:

**Discover | Watchlist | Portfolio | Alerts | Agent**

Mobile should prioritize monitoring, alerts, event inspection, paper positions, and agent workflows rather than compressing the desktop research workstation.

## 35. Cross-Platform Continuity

A user may build a strategy on desktop, receive an alert on mobile, inspect the event, ask the agent for an explanation, create a paper position, and later see the same position on desktop without manual synchronization.

## 36. Data Requirements

The system should preserve:

- Raw provider payloads
- Normalized canonical data
- Provider/venue mappings
- Historical event data
- Historical sportsbook odds
- Prediction-market order books/trades where available and licensed
- Feature snapshots
- Predictions
- Model versions
- Strategy versions
- Backtest runs
- Positions/orders/fills
- Closing prices
- Provider provenance
- Availability/observation timestamps required for leakage-safe research

Historical reproducibility is mandatory.

## 37. Provider and Venue Requirements

The platform must support three broad external categories:

1. **Sports-information providers** — schedules, results, statistics, lineups, injuries, xG, players.
2. **Sportsbook-market data providers** — current and historical bookmaker prices across many venues.
3. **Tradable market venues** — order books, trades, positions, and eventually execution.

Exact providers are technical/configuration decisions maintained in the TDD, ADRs, and provider evaluation matrix rather than hard product dependencies.

## 38. Low-Cost Validation Requirements

- Local development and routine CI must not require paid provider calls.
- External provider adapters must support captured fixtures/mock servers.
- Provider contract tests should use free/demo/replay environments where available.
- Paid historical acquisition should occur only after the end-to-end research loop is proven.
- Acquired historical data should be retained and reused where licensing permits.
- Provider quota usage and estimated cost should be observable.

## 39. Data Provenance

Every externally sourced record that can affect a model, price, backtest, or execution decision should retain source, provider-native ID, observed/ingested timestamps, and transformation/version metadata.

## 40. Non-Functional Requirements

### Reliability
Critical analytical outputs must be reproducible.

### Traceability
Predictions map to dataset, feature, model, pricing, and timestamp versions.

### Explainability
Users should be able to inspect why a discrepancy exists.

### Auditability
Portfolio and execution actions maintain histories.

### Extensibility
Adding a sport should not redesign portfolio, strategy, execution, MCP, or the client shells.

### Security
Execution credentials stay server-side. Secrets are never embedded in web/mobile clients.

### Synchronization
User state remains consistent across web and mobile.

### Availability
Core read workflows should remain available around event start times.

### Cost Awareness
Development and validation should prefer free/local/replay capabilities before paid infrastructure or data feeds.

## 41. Open-Source References & Design Inspiration

Reference implementations include:

- `betcode-org/flumine` — strategy/execution lifecycle, simulation/live separation
- `anpl1623/sharpline` — odds normalization, pricing, EV, parlays, streaming
- `Hicruben/theopenmodel` — transparent soccer modeling
- `aneesh-a7/sportelo` — sport-neutral ratings/simulation ideas
- `Veedubin/quant-sports-mcp` — MCP tool taxonomy
- Kalshi-oriented open-source trading references — backtest/paper/live lifecycle and risk controls

These are research inputs, not architecture commitments. Any code reuse requires license, security, maintenance, and dependency review.

## 42. Risk Controls

The system should support maximum position size, event/participant/sport exposure, daily/weekly loss limits, total bankroll-at-risk, kill switches, and auditable execution history.

## 43. Success Metrics

Product/research success should be measured by data freshness, model calibration, backtest reproducibility, CLV, strategy sample size, alert timeliness, system reliability, and user ability to complete the research-to-paper-trade loop—not by raw win rate alone.

## 44. Product Milestones

1. Core domain and data foundation
2. Soccer model
3. Backtester
4. Paper-trading platform
5. MCP and agent
6. Web terminal
7. Mobile foundation
8. Parlay engine
9. Basketball
10. American football
11. Tennis
12. Controlled execution experiments

## 45. Future Roadmap

- Richer live models
- Props
- Automated position revaluation
- Additional venue integrations
- Limited real-money execution
- Correlation-aware portfolio optimization
- Multi-user/commercial features where appropriate

## 46. Key Risks

- Historical-data licensing/coverage gaps
- Provider schema drift or outages
- Entity/market normalization errors
- Leakage in backtests
- False precision from poorly calibrated models
- Overfitting strategies to historical prices
- Exchange liquidity/execution assumptions
- Vendor lock-in
- Provider cost escalation
- Open-source dependency/licensing risk
- Real-money execution/regulatory constraints

## 47. Open Questions

- Final production sports-data providers by sport
- Exact historical-odds acquisition plan
- Which advanced soccer features materially improve OOS results
- PostgreSQL/RDS versus Aurora timing
- Long-term data-lake query layer
- Model deployment/training evolution
- Authentication provider and production configuration
- Alert/push architecture at scale
- Model registry/feature-store needs
- Single-user versus multi-user timing
- First real-money execution venue
- Monetization
- Mobile framework evolution if requirements outgrow Expo
- Which open-source references merit deeper architecture review

## 48. MVP Definition of Done

The MVP is complete when a user can:

- Browse supported soccer events on web/mobile
- See normalized prices from supported sportsbook and prediction-market sources
- Inspect model probability, fair odds, market probability, edge, EV, freshness, and provenance
- Run a leakage-safe historical backtest against versioned data
- View calibration/CLV/ROI/drawdown metrics
- Create and close paper positions
- See portfolio exposure and P&L
- Create watchlists and alerts
- Receive a mobile deep-linked alert
- Ask the agent to explain an event/opportunity
- Use MCP tools for research/backtests/portfolio operations
- Move between web and mobile with synchronized state

The engineering team must also be able to validate the normal local/CI path without paid external API calls.

## 49. North Star

> A cross-platform, multi-sport quantitative sports trading platform for team and individual sports that transforms sports data and market prices into testable fair-value estimates, helps users discover and manage potential opportunities, and provides one agentic experience across web and mobile for research, monitoring, backtesting, portfolio management, and eventually execution.
