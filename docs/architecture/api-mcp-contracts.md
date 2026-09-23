# API & MCP Contract Design

**Status:** Draft

## Principle

The API is the authoritative application boundary. MCP orchestrates API/domain capabilities and must not reimplement pricing, EV, risk, settlement, or persistence logic.

## REST/OpenAPI domains

Implementation exposes `GET /health` and local-only configured current-state event
list/detail reads under [ADR-024](../adr/ADR-024-event-read-api.md). Its OpenAPI
snapshot and TypeScript client types are generated locally; see
[`contracts/README.md`](../../contracts/README.md). The domains below remain
planned capabilities except the event and private dataset reads. Generated drift is enforced by `scripts/validate`;
compatibility against a frozen pre-release foundation snapshot is enforced by
`scripts/check-contracts`. There is no released API baseline yet; see
[baseline policy](../../contracts/baselines/README.md).

### Private retained datasets

The additive local-only [ADR-032](../adr/ADR-032-local-dataset-api.md) consumer
exposes `GET /v1/datasets` and `GET /v1/datasets/{rootHash}/inspection`.
The former lists up to 32 explicitly selected roots with `NOT_CHECKED` status;
the latter freshly verifies retained replay and returns `VERIFIED` only after
complete success. Both retain literal `REPLAY_ONLY` usage and false backtest
eligibility. The default app returns 503 without storage configuration. These
routes authorize no hosted access, provider fetches, writes or eligibility changes.

### Events/Markets

- `GET /v1/events`
- `GET /v1/events/{eventId}`
- `GET /v1/events/{eventId}/markets`
- `GET /v1/markets/{marketId}/quotes`

### Predictions/Opportunities

- `GET /v1/events/{eventId}/prediction`
- `GET /v1/opportunities`
- `GET /v1/opportunities/{id}`

### Backtests/Strategies

- `POST /v1/strategies`
- `POST /v1/backtests`
- `GET /v1/backtests/{id}`
- `POST /v1/backtests/compare`

### Portfolio/Paper

- `GET /v1/portfolio`
- `GET /v1/portfolio/risk`
- `POST /v1/paper-positions`
- `POST /v1/paper-positions/{id}/close`

### Watchlists/Alerts

- CRUD watchlists
- add/remove watchlist targets
- CRUD alerts

### Parlays

- `POST /v1/parlays/evaluate`

## MCP mapping

Phase 1 now includes a local stdio protocol shell in apps/mcp: initialization,
ping, and empty tool discovery. It exposes no business tools and performs no
backend/provider calls. See [MCP foundation](../../apps/mcp/README.md).
The tool list below describes future product capabilities, not the current shell.

Initial MCP tools:

- `search_events`
- `get_event`
- `get_markets`
- `get_quotes`
- `get_prediction`
- `explain_prediction`
- `find_opportunities`
- `run_backtest`
- `get_backtest`
- `compare_backtests`
- `get_portfolio`
- `get_portfolio_risk`
- `create_watchlist`
- `add_to_watchlist`
- `create_alert`
- `create_paper_position`
- `close_paper_position`
- `evaluate_parlay`

## Write safety

Read tools are non-destructive. User-state writes require explicit intent. Future execution is split into `prepare_order` and `submit_order`; the latter requires explicit confirmation and passes through risk checks.

## Stable identifiers

Tool/API results return canonical IDs so follow-up actions never rely on fuzzy natural-language resolution when the application already knows the target.

## Compatibility

OpenAPI/event changes are additive by default. CI compares released contracts and generated clients. Generated code is never edited manually.
