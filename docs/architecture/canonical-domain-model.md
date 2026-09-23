# Canonical Domain & Data Model

**Status:** Draft

## Goals

- Sport-neutral core
- Provider-neutral markets
- Explicit source/venue provenance
- Supports team and individual sports
- Supports sportsbook quotes and exchange order books
- Supports backtesting, paper trading, and future execution with the same IDs

## Core hierarchy

`Sport -> Competition -> Season -> Event -> EventParticipant -> Market -> Selection -> Quote/MarketSnapshot`

## Primary entities

### Sport

- `sport_id`
- `code`
- `name`

### Competition

- `competition_id`
- `sport_id`
- `name`
- `country_or_region`
- `gender_or_division` where applicable

### Season

- `season_id`
- `competition_id`
- `name`
- `starts_at`
- `ends_at`

### Participant

- `participant_id`
- `sport_id`
- `participant_type` (`TEAM`, `PLAYER`, `PAIR`, `FIGHTER`, etc.)
- `canonical_name`

### Event

- `event_id`
- `sport_id`
- `competition_id`
- `season_id`
- `starts_at`
- `status`
- `venue_location` optional

### EventParticipant

- `event_id`
- `participant_id`
- `role` (`HOME`, `AWAY`, `PLAYER_1`, `PLAYER_2`, `FIELD`, etc.)

### DataSource

Represents the system through which data was obtained.

- `data_source_id`
- `code`
- `source_type` (`SPORTS_DATA`, `ODDS_AGGREGATOR`, `VENUE_API`, `OFFLINE_DATASET`)
- `capabilities`

### Venue

Represents where a market/price exists.

- `venue_id`
- `operator`
- `product`
- `jurisdiction`
- `venue_type` (`SPORTSBOOK`, `PREDICTION_MARKET`, `EXCHANGE`)
- `capabilities`

### ProviderEntityMapping

- `data_source_id`
- `provider_entity_type`
- `provider_entity_id`
- `canonical_entity_id`
- `mapping_method`
- `confidence`
- `validated_at`

Internal revision identity, audit fields, revocation, confidence semantics, and
historical resolution are specified in
[ADR-013](../adr/ADR-013-provider-mapping-revisions.md). The conceptual fields
above are not a complete persistence or external contract schema.

### Market

Canonical definition of the proposition being priced.

- `market_id`
- `event_id`
- `market_type`
- `period`
- `participant_id` optional
- `parameters` JSON/value object, e.g. line `2.5`

### Selection

- `selection_id`
- `market_id`
- `side/outcome`
- `participant_id` optional

### Quote

Sportsbook-style price observation.

- `selection_id`
- `venue_id`
- `data_source_id`
- `odds_decimal`
- `observed_at`
- `available_at`
- `ingested_at`
- `provider_quote_id` optional

### MarketSnapshot

Exchange/prediction-market state.

- `market_id`
- `venue_id`
- `data_source_id`
- `best_bid`
- `best_ask`
- `last_trade`
- `displayed_price` optional
- `bid_depth`/`ask_depth` summary
- `volume`
- `liquidity`
- `observed_at`
- `available_at`

### Prediction

- `prediction_id`
- `event_id`
- `model_version_id`
- `feature_snapshot_id`
- `as_of`
- `distribution_artifact_uri` or compact distribution

### ModelVersion

- `model_version_id`
- `sport`
- `competition_scope`
- `model_type`
- `dataset_version`
- `feature_schema_version`
- `artifact_uri`
- `training_period`
- `metrics`
- `status`

### Strategy

- `strategy_id`
- `version`
- `rule_document`
- `created_at`

### BacktestRun

- `backtest_run_id`
- `strategy_version`
- `dataset_manifest`
- `model_versions`
- `decision_time_policy`
- `execution_assumptions`
- `result_summary`
- `artifact_uri`

### Portfolio / Ledger / Position

`Portfolio` owns configuration and references an append-only cash ledger.

`Position` contains venue, selection(s), entry price, quantity/stake, state, realized/unrealized result, and settlement linkage.

### Order / Execution / Settlement

Future real-money paths separate order intent/preparation, submitted orders, fills/executions, and settlement.

## Time semantics

Research-sensitive data should preserve `effective_at`, `observed_at`, `available_at`, and `ingested_at` where meaningful. `available_at` controls historical eligibility in backtests.

## Identifier rules

- Canonical IDs are generated internally and stable.
- Provider IDs never become primary business IDs.
- Provider mappings are versioned/auditable.
- Market identity is derived from canonical semantics, not provider display names.
