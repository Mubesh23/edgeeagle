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

### Premier League 2024/25 real-file evidence gate

**Reviewed:** 2026-09-23. **Status:** Owner-approved private research scope;
private local import and replay verified under the owner-approved kickoff assumption.

The user-requested local download of `mmz4281/2425/E0.csv` contains 380 results,
20 team labels and 120 columns (197,110 bytes). Its retained SHA-256 is
`d0c8ce4a96d886cf60cf101f570f4a3893844226f91c7bd769eb568c49edbfa4`.
The CSV, acquisition metadata and HTTP headers are kept in Git-ignored `.data/`,
not redistributed as fixtures. Acquisition is not canonical acceptance or a
replay snapshot. Routine tests remain synthetic and offline.

Evidence reviewed:

- The [provider homepage](https://football-data.co.uk/) and
  [download index](https://football-data.co.uk/downloadm.php) advertise free files
  for quantitative analysis. The homepage also reserves rights. This supports
  considering a local research use, not assuming a general open-data license.
- The [linked disclaimer](https://football-data.co.uk/disclaimer.php) addresses
  accuracy, liability and gambling; the reviewed text does not establish a
  commercial-use, retention or redistribution license for EdgeEagle.
- The [field notes](https://football-data.co.uk/notes.txt) identify the kickoff
  field without specifying its timezone. Do not assume UTC or Europe/London from
  league location alone. A timezone rule needs provider confirmation or adequate
  independent match-time evidence before per-row offsets are approved.
- The advertised commercial permissions for the
  [separate subscription API](https://football-data.co.uk/thestatsapi.php) are
  not evidence of permission for these CSV files.

On 2026-09-23 the owner explicitly selected private research and no commercial
deployment: the application is initially for their own use, with commercial use
to be revisited if that changes. This satisfies the repository's human-review
gate for proceeding within that intended scope based on the advertised analytical
use. It is an owner scope/risk decision, not written provider permission or a
finding that unrestricted rights exist. No commercial-use or redistribution
license has been established.

The current engineering work stays local; this approval does not authorize a
deployment or publication of the dataset. Keep the real file and derived records
out of Git and routine hosted CI. Before commercialization or distribution,
revisit provider permissions for raw retention, derived records, display and
redistribution, using the [contact page](https://football-data.co.uk/contact.php)
where clarification is necessary. No contact has been sent.

Initial timezone cross-check: the retained CSV has Manchester United versus Fulham
on 16 August 2024 at 20:00. The
[club's match preview](https://www.manutd.com/en/news/match-preview-for-man-utd-v-fulham-in-the-premier-league-13-august-2024)
explicitly identifies that kickoff as 20:00 BST. This establishes a corroborating
summer-time sample, not a verified rule for all 380 rows. The
[league's season fixture article](https://www.premierleague.com/en/news/4040106)
uses local time but warns fixtures can change; it is not by itself a final
historical kickoff record. Winter/DST coverage and discrepancies must be reviewed
before approving the file's per-row offsets. Odds-collection/upload times on the
provider's fixtures page are not kickoff-timezone evidence.

Additional review on 2026-09-23 matched the retained CSV to official club notices:
Arsenal–Liverpool on 27 October 2024 at 16:30 GMT
([Liverpool ticket notice](https://www.liverpoolfc.com/news/arsenal-v-liverpool-away-ticket-details-2))
and Liverpool–Everton on 2 April 2025 at 20:00 BST
([Liverpool viewing notice](https://www.liverpoolfc.com/news/liverpool-v-everton-tv-channels-live-commentary-and-highlights-details-0)).
These cover winter time on the autumn transition date and summer time after the
spring transition. The [UK clock rule](https://www.gov.uk/when-do-the-clocks-change)
corroborates the seasonal offset convention. These are scheduled-time samples,
not independent validation of all final kickoff timestamps.

Interpreting this capture's clocks as Europe/London would assign 203 rows offset
0 minutes and 177 rows +60 minutes. On 2026-09-23 the owner explicitly accepted
this documented, sample-corroborated assumption for private replay-only use.
This clears the dataset-specific timezone decision; it does not establish
provider confirmation or independent verification of every kickoff. Freeze the
resulting offset in each retained request/receipt rather than recomputing it on
replay. Do not generalize this approval to other captures or historical features.

The local pre-import review confirmed 380 unique ordered team pairings and exactly
19 home/19 away appearances for each of 20 labels. An explicit label-to-canonical
name review is retained under ignored `.data/`; no fuzzy mapping was used.
The explicit local run then applied existing migrations through
`0010_soccer_receipts`, allocated and retained canonical IDs and 380 request
bindings, and registered the source plus 23 current-review mapping revisions.
Their availability timestamps describe this review, not historical match knowledge.

On 2026-09-23, all 380 results were accepted in the local developer database.
The original raw capture, six receipt pages and root are retained in a dedicated
private Floci bucket. Exact retries returned the same root hash without duplicate
events/receipts or outbox notifications. Every score, event ID and asserted kickoff
matched the retained CSV/bindings; canonical receipt bytes matched database readback.
A separate replay process reproduced all 380 without opening PostgreSQL.
The root hash, frozen bindings, operator script and verification report remain
under ignored `.data/`; no real result export is committed or sent to hosted CI.
The original acquisition metadata is preserved as the download-time record.

The initial operator checker compared participant tuple ordering instead of the
canonical receipt representation. The 190 reversed pairs were equivalent in all
380 canonical encodings; correcting that local checker required no product-code
or retained-data change. Full `scripts/validate` passed (782 unit tests,
136 integration tests, one existing expected Floci delivery-DLQ failure).
Local retention is not an independently tested backup or production storage.

Historical result availability remains unknown regardless of acquisition time
or HTTP Last-Modified. [ADR-029](../adr/ADR-029-football-data-season-replay.md)
now implements a separate 512-row profile, paged replay storage and atomic
PostgreSQL acceptance; ADR-028's 100-row profile and legacy 1 MiB manifest limit
remain unchanged. No training/backtesting eligibility is established.

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
