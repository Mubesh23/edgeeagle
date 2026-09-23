# Data Ingestion & Normalization Design

**Status:** Draft

## Objectives

- Preserve every externally acquired payload before transformation.
- Normalize multiple providers into canonical sport/market entities.
- Make replay/reprocessing deterministic.
- Prevent provider-specific concepts leaking into modeling and product code.
- Preserve timestamps needed for leakage-safe backtesting.

## Pipeline

```text
External source
 -> provider adapter
 -> raw immutable object
 -> validation
 -> provider-native staging record
 -> entity resolution
 -> canonical normalization
 -> current-state store + historical Parquet
 -> domain event
```

## Raw storage

The internal raw record and storage port are defined by
[ADR-015](../adr/ADR-015-raw-payload-storage.md). Capture timestamps are caller
supplied; unknown effective/observed/available times remain unknown. This does not
make raw captures eligible backtest records without subsequent normalization.

Raw responses should be stored in S3 by source, acquisition date, endpoint/resource type, and checksum. Where licensing prohibits retention, record the restriction and retain only allowed derived metadata.

Example key:

`raw/source=the_odds_api/resource=odds/date=2026-09-22/<request-id>.json`

## Provider adapters

The first implemented capability is bounded offline acquisition and raw retention;
see [ADR-016](../adr/ADR-016-offline-ingestion-boundary.md). It is exercised using
synthetic fixtures, not live feeds. [ADR-017](../adr/ADR-017-synthetic-event-normalization.md)
adds retained-fixture parsing and explicit canonical event candidates.
[ADR-018](../adr/ADR-018-event-acceptance-lineage.md) adds transactional canonical
acceptance; [ADR-019](../adr/ADR-019-event-outbox.md) adds atomic publication intents.
EventBridge/SQS verification delivery and current-state event API reads now exist.
The [fixture acceptance test](../../tests/integration/test_fixture_ingestion.py)
connects retained raw bytes, legacy bindings or mapping-backed fixture manifests,
canonical acceptance/outbox,
broker delivery, consumer deduplication, and API list/detail reads. Run
`scripts/test-integration -k fixture_raw_to_api`. This is synthetic local evidence,
not real-provider acquisition, historical Parquet, or production worker readiness.
The EventBridge delivery-DLQ gap remains documented in
[ADR-023](../adr/ADR-023-event-acceptance-consumer.md).
The mapped variant uses one read-only PostgreSQL snapshot for reference resolution
and retains selected revisions/context in format-2 receipts; see
[ADR-025](../adr/ADR-025-mapping-backed-fixture-context.md). Availability cutoffs do
not make a newly opened snapshot equivalent to a retained historical dataset.

Separate interfaces by capability:

- `SportsDataAdapter`
- `SportsbookOddsAdapter`
- `PredictionMarketDataAdapter`
- `ExecutionVenueAdapter` (future)
- `OfflineDatasetImporter`

Kalshi and Polymarket may implement both market-data and eventual execution capabilities. Football-Data.co.uk is an offline dataset importer rather than a runtime API.

## Entity resolution

Resolve provider IDs to canonical participants/events/competitions using explicit mapping tables. Automated matching may propose mappings; ambiguous mappings require review.

## Market normalization

Provider-specific labels map to canonical `MarketDefinition` + `Selection` structures. Normalizers must be deterministic and versioned.

## Time semantics

Store the best available meaning of:

- `effective_at` — when the underlying fact became true
- `observed_at` — provider's observation/snapshot time
- `available_at` — earliest time our simulated strategy could have known it
- `ingested_at` — when our system stored it

Backtests use `available_at` rather than hindsight timestamps.

## Idempotency

Ingestion writes use source-native IDs plus version/snapshot timestamps or payload hashes as idempotency keys. Replayed messages must not create duplicate canonical effects.

## Provider failures

Each adapter defines timeout/retry/backoff and degradation behavior. Provider outages must not corrupt canonical state. Last-known data must carry freshness timestamps so stale data cannot appear current.

## Reprocessing

Normalization is versioned. A new normalizer version can replay retained raw payloads into a new historical dataset without mutating the prior research snapshot.

The first bounded [dataset manifest contract](dataset-snapshot-manifest.md) pins
complete raw captures and embedded mapped receipts under a content-derived version;
see [ADR-026](../adr/ADR-026-replay-dataset-manifest.md). Frozen values and the
strict, bounded metadata codec and read-only whole-snapshot verification are
implemented; manifest persistence/cataloging remain pending. Its `REPLAY_ONLY`
restriction preserves unknown availability and
prohibits historical decision-input use; it does not implement historical Parquet,
feature/model datasets, or a snapshot catalog.
The next storage boundary is specified by
[ADR-027](../adr/ADR-027-replay-manifest-storage.md): conditional canonical-manifest
writes and exact dataset-version lookup. The adapter is not implemented yet;
storage, replay verification, and historical eligibility remain separate outcomes.

## Data quality checks

- Missing/duplicate participants
- Impossible event times
- Odds <= 1.0 in decimal representation
- Invalid line values
- Stale quotes
- Unknown market mapping
- Event/provider mismatch
- Impossible score/state transitions
- Unexpected schema additions/removals

Questionable records are quarantined rather than silently coerced.

## Cost control

- Cache immutable/reference resources.
- Fetch once and reuse historical snapshots.
- Never let a backtest call a paid provider directly.
- Provider contract tests have explicit call budgets.
- Persist quota headers/usage where providers expose them.
