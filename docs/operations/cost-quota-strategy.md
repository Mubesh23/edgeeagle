# Cost & Quota Strategy

**Status:** Draft

## Objective

Validate the architecture, model loop, and product experience before committing meaningful recurring spend to sports-data subscriptions or cloud environments.

## Policy

1. Local/CI uses no paid provider calls.
2. Use free tiers/demo/replay for provider contract validation.
3. Historical paid data is acquired only after the ingestion -> model -> pricing -> backtest -> UI loop works.
4. Fetch historical data once and persist/reuse it where license terms allow.
5. No backtest directly queries a paid external API.
6. Provider quota consumption is observable and budgeted.
7. Development AWS usage should be replaceable with local Floci for routine workflows.

## Initial provider budget target

| Provider | Initial recurring target |
|---|---:|
| Kalshi | $0 API subscription; Demo/public data |
| Polymarket | $0 API subscription identified; market-data integration + paper simulation |
| The Odds API | $0 using 500-credit free tier |
| Sportmonks | $0 using free plan |
| Football-Data.co.uk | $0 |
| SportsDataIO | $0 while using trial/Replay if evaluated |
| Sportradar | $0 during applicable trial evaluation |

This is a development target, not a guarantee that production data will remain free.

## Quota model

Persist/emit per provider and environment:

- requests
- quota units charged
- remaining units where exposed
- time-window reset
- cache/reuse rate
- estimated marginal cost
- contract-test allowance

Alert at configurable utilization thresholds, e.g. 70%, 90%, and exhaustion.

## Paid-upgrade gates

Approve a paid plan only when a documented experiment requires one of:

- a competition unavailable on free access
- historical prices unavailable for credible backtests
- live latency/fidelity unavailable in replay/demo
- advanced stats proven useful in an OOS experiment
- commercial/public-display licensing
- production call volume

The request should identify expected monthly cost, duration, experiment, data retention rights, and success criteria.

## Historical-data purchasing

Bulk/historical acquisitions should land first in immutable raw storage with checksums and provider metadata. Normalized Parquet datasets are derived from that source. Re-running a backtest must read retained data, not re-buy the same provider snapshot.
