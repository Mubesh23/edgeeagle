# API & MCP Contract Design

**Status:** Draft

## Principle

The API is the authoritative application boundary. MCP orchestrates API/domain capabilities and must not reimplement pricing, EV, risk, settlement, or persistence logic.

## REST/OpenAPI domains

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
