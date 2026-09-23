# Data Provider Evaluation Matrix

**Status:** Living document  
**Last verified:** 2026-09-22  
**Purpose:** Keep fast-changing vendor facts out of the PRD/TDD while preserving the evidence needed for provider decisions.

## Current V1 provider plan

| Provider | Role | Official API/data interface | Free/test path | Current pricing snapshot | V1 status |
|---|---|---|---|---|---|
| Kalshi | Prediction-market data; order books; future execution | Official REST API exposes public market data/order books plus authenticated orders/trades/portfolio | Official Demo environment with mock funds and separate credentials | No standalone API subscription price identified in reviewed official help docs; trading fees apply | **Use in V1** |
| Polymarket | Prediction-market data/order books; future execution where supported | Official developer API documentation for discovery/resolution/trading | No dedicated sandbox identified in reviewed official docs; use fixtures + paper adapter for routine testing | No API subscription price identified; sports taker fee formula currently uses `feeRate=0.05`, makers `0` | **Use market data in V1** |
| The Odds API | Sportsbook odds aggregator; current bookmaker prices; later selective historical odds | Official JSON API | Free tier: 500 credits/month | $30/20K, $59/100K, $119/5M, $249/15M credits per month; historical is paid | **Use in V1** |
| Sportmonks | Soccer fixtures/results/stats/lineups/xG and other fundamentals | Official REST/JSON API | Free-forever plan with real data for Danish Superliga + Scottish Premiership | Monthly Starter €29/5 leagues; Growth €99/30; Pro €249/120; enterprise custom; paid plans offer 14-day trial | **Use in V1 soccer** |
| Football-Data.co.uk | Historical soccer results/odds bootstrap | Downloadable CSV/Excel, not our production REST API | Free historical downloads | Free | **Use for research/bootstrap** |
| SportsDataIO | Future US-sports data/odds/live integration | Official APIs | Free scrambled trial; Replay is real historical data replayed in real time and advertised free/unlimited | Discovery Lab $99 Fantasy, $99 Odds, $149 combined; commercial production custom | Evaluate later |
| Sportradar | Future enterprise multi-sport source | Official APIs | Standard trial is 30 days, typically 1,000 requests/rolling 30 days and 1 QPS; real-world data | Production/custom commercial quote | Evaluate later |

## Venue vs source matrix

A venue and a data source are not the same thing.

| Venue | Venue type | Initial source | Direct execution planned? |
|---|---|---|---|
| DraftKings | Sportsbook | The Odds API where covered | No V1 |
| FanDuel | Sportsbook | The Odds API where covered | No V1 |
| BetMGM | Sportsbook | The Odds API where covered | No V1 |
| Caesars | Sportsbook | The Odds API where covered | No V1 |
| Bovada | Sportsbook | The Odds API where covered | No V1 |
| Pinnacle | Sportsbook | The Odds API where covered | No V1 |
| bet365 | Sportsbook | Only through an authorized/contracted aggregator if coverage is sufficient | No V1 |
| Kalshi | Prediction market/exchange | Kalshi API | Future; demo first |
| Polymarket | Prediction market/exchange | Polymarket API | Future; jurisdiction/capability gated |

## Why this split

We do not want one vendor to become the canonical schema for the entire application. Each source is mapped to canonical entities and markets, and each record retains provenance.

## Low-cost development plan

### Local/CI — $0 paid provider calls

- Captured provider fixtures
- Synthetic market/order-book fixtures
- Mock provider HTTP server
- Football-Data.co.uk historical files
- Floci for AWS-shaped services
- Local PostgreSQL

### Provider contract tests — target $0

- Sportmonks free tier
- The Odds API free tier with a strict credit budget
- Kalshi Demo/public data
- Polymarket read/API surface where accessible
- SportsDataIO Replay when/if that integration is introduced

### Paid research acquisition

Only after the pipeline is proven should we buy historical odds or broader league coverage. Persist raw responses immediately and reuse them where license terms permit.

## Provider-selection criteria

Every provider evaluation should score:

- Sports/competition coverage
- Women's competition coverage
- Historical depth
- Timestamp fidelity
- Current/live latency
- Player/team stats
- xG/advanced metrics
- Injuries/lineups
- Odds markets and bookmakers
- Props
- Order-book depth/trades/liquidity
- API quality/schema stability
- Sandbox/demo/replay
- Rate limits/quotas
- Free tier
- Production pricing
- Commercial/display/redistribution licensing
- Support/SLA
- Data-quality correction process
- Ease of mapping canonical IDs

## Current known limitations

- The Odds API free plan does not include historical odds.
- Historical Odds API featured-market snapshots are available from June 2020 and are paid; snapshot frequency improves from 10 minutes to 5 minutes from September 2022.
- Football-Data.co.uk is excellent bootstrap research data but not a production API dependency.
- Kalshi's demo environment is stronger for execution testing than Polymarket's currently documented developer path.
- Polymarket execution must be capability/jurisdiction gated separately from market-data ingestion.
- SportsDataIO Discovery Lab is personal/non-commercial; a commercial product requires commercial terms.

## Sources

### Football-Data results importer subset

**Schema notes verified:** 2026-09-23, using the official notes/download index below.
The notes define division, match date/time, team labels, full-time goals and H/D/A
result columns. They do not establish a timezone or per-record publication time
for this import. The first adapter supports an explicit bounded, four-digit-year,
completed-results subset under [ADR-028](../adr/ADR-028-football-data-results-import.md);
it requires caller-supplied row offsets and identity context. Odds and optional
statistics remain raw-only. No provider-native event ID is claimed.

Tests use authored synthetic CSVs, not downloaded provider data. This schema review
does not grant retention, display, commercial-use, or redistribution rights.
Acquiring or using real files remains subject to separate rights review.

- Field notes: https://football-data.co.uk/notes.txt
- Download index: https://football-data.co.uk/downloadm.php

### General provider references

- Kalshi API: https://help.kalshi.com/en/articles/13823854-kalshi-api
- Kalshi Demo: https://help.kalshi.com/en/articles/13823775-creating-and-using-a-demo-account
- Polymarket API: https://help.polymarket.com/en/articles/13364254-does-polymarket-have-an-api
- Polymarket fees: https://help.polymarket.com/en/articles/13364478-trading-fees
- The Odds API pricing/coverage: https://the-odds-api.com/
- The Odds API historical: https://the-odds-api.com/historical-odds-data/
- Sportmonks free plan: https://www.sportmonks.com/football-api/free-plan/
- Sportmonks pricing: https://www.sportmonks.com/football-api/plans-pricing/
- Football-Data.co.uk: https://football-data.co.uk/downloadm.php
- SportsDataIO developer access: https://sportsdata.io/developers
- SportsDataIO Replay: https://sportsdata.io/developers/replay
- Sportradar account/trial model: https://developer.sportradar.com/getting-started/docs/your-account
