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

The existing Prediction is the forecast snapshot; do not introduce a duplicate
ForecastSnapshot entity. The additions below are conceptual Phase 4+ requirements
under [ADR-036](../adr/ADR-036-soccer-model-evaluation-and-market-benchmarking.md),
not deployed tables, generated APIs or changes to strict replay receipt formats.

- `prediction_id`
- `event_id`
- `model_version_id`
- `feature_snapshot_id`
- `as_of`
- `distribution_artifact_uri` or compact distribution
- `forecast_horizon` and horizon-policy version
- `generated_at`, generation mode (published forecast vs historical simulation)
- decision-time kickoff context and realized lead time
- `model_uncertainty` evidence
- market-input snapshot references when market-aware (distinct from evaluation benchmarks)

`as_of` is the decision/input cutoff, not a substitute for generation time or proof
of historical availability. All consumed inputs/dependencies need availability
evidence; a later-generated historical simulation cannot claim it was published then.

### ForecastHorizon

A versioned value/policy, not a replacement timestamp. Illustrative labels:
`OPEN`, `T_MINUS_24H`, `T_MINUS_6H`, `T_MINUS_60M`, `LATEST_PREMATCH`. Retain policy
version, actual cutoff, as-known kickoff, lead time, selection tolerance and
missing/rescheduled-event treatment. OPEN means first eligible observed market
under a declared coverage policy; LATEST_PREMATCH uses an explicit pregame cutoff.
Different horizons are not interchangeable evaluation cohorts.

### ModelUncertainty

Versioned reliability evidence attached to a Prediction/evaluation, not outcome
probability or an unexplained scalar. Candidate components: calibration uncertainty,
sample count, competition coverage, freshness, parameter uncertainty, stability,
model disagreement and horizon effects. Preserve method/version, scope, input pins,
missing components, warnings and limitations. Numeric intervals, when supported,
must identify their estimand and interpretation. No universal estimator is selected.

### MarketConsensusSnapshot

A derived benchmark, distinct from a single-venue MarketSnapshot or executable Quote:

- snapshot identity/version and canonical market/selection/settlement semantics
- decision cutoff, ForecastHorizon policy and as-known kickoff context
- pinned complete input quote sets with separate venue/data-source provenance
- coverage, exclusions, source precedence/deduplication and freshness policy
- de-vig method/version/parameters/numeric policy (MULTIPLICATIVE, SHIN, POWER candidates)
- aggregation policy/version/order/weights and normalized outcome probabilities
- market dispersion/de-vig sensitivity and missing/insufficient-coverage status

De-vig complete per-venue outcome sets before aggregation under the selected policy;
record alternate constructions as distinct research policies. Never create a
fictitious venue from cross-book best prices. A benchmark may be unavailable and
cannot be backfilled with future observations. Immutable input pins establish
reproducibility, not rights, historical eligibility or executability. Exact wire,
identity and storage contracts require a later implementation decision.

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

Research metadata also identifies model family, market-input dependency mode,
training cutoff/artifact readiness, calibration/uncertainty method versions,
supported horizons, baseline/consensus references, OOS folds/metrics and promotion
evidence. An ensemble inherits market-aware classification if any input uses odds.
This separates independent fundamentals skill from incremental market-aware skill.

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

Retain evaluation-policy version, horizon definitions, benchmark snapshot pins,
pricing/de-vig versions, uncertainty evidence and cost/closing-price conventions.
Reports separate predictive log loss/Brier/calibration and paired baseline deltas
from EV/CLV/ROI/P&L/drawdown/volatility/sample counts and segmented robustness.
Raw EV, reliability and strategy qualification/abstention are distinct outputs;
none implies risk approval. Do not add these fields to existing replay manifests.

### ParlayEvaluation (future backend output)

Reuse the [Parlay Lab conceptual contract](../product/feature-specs/parlay-lab.md)
for joint-model coverage, correlation method/version, ModelUncertainty, horizon,
input lineage and supported per-leg/counterfactual analytics. Coverage categories
EXACT, SIMULATED, INDEPENDENCE_ASSUMED and UNSUPPORTED describe computation/support,
not confidence. Unsupported joint numeric outputs are unavailable, never zero or
LLM-generated. Exact/simulated group coverage cannot conceal cross-group assumptions.
No current API or receipt schema is extended by this conceptual output.

### Portfolio / Ledger / Position

`Portfolio` owns configuration and references an append-only cash ledger.

`Position` contains venue, selection(s), entry price, quantity/stake, state, realized/unrealized result, and settlement linkage.

### Order / Execution / Settlement

Future real-money paths separate order intent/preparation, submitted orders, fills/executions, and settlement.

## Time semantics

Research-sensitive data should preserve `effective_at`, `observed_at`, `available_at`, and `ingested_at` where meaningful. `available_at` controls historical eligibility in backtests.

Every consumed feature, quote and context dependency must satisfy evidenced
`available_at <= decision_time`; training labels must be available by the fit
cutoff, while later evaluation outcomes remain separate. Unknown availability,
mapping cutoff, ingestion time or successful replay cannot establish eligibility.
Existing ADR-026/029 replay datasets and ADR-034/035 quotes retain their restrictions.

## Identifier rules

- Canonical IDs are generated internally and stable.
- Provider IDs never become primary business IDs.
- Provider mappings are versioned/auditable.
- Market identity is derived from canonical semantics, not provider display names.
