# Provider fixtures

The [Football-Data-shaped CSV](football_data/README.md) is authored synthetic
completed-results data for the offline adapter. It is not a downloaded provider file.

Initial fixtures are authored synthetic test data, not captured provider responses.
The first set uses a limited subset of The Odds API v4 soccer h2h odds shape,
referenced from [official documentation](https://the-odds-api.com/liveapi/guides/v4/).
Teams, event IDs, times, and prices are invented; a bookmaker key is retained to
exercise the distinction between venue identity and data source identity.

Each provider directory includes payloads and metadata with fixture ID/version,
provider, endpoint/API version, supported parameters, provenance, creation date,
and documentation reference. Synthetic data uses `captured_at: null`. Future
captured fixtures must record the actual capture date, be sanitized, and have
their retention/redistribution permission reviewed before they are committed.
This increment makes no claims about provider data licensing or live compatibility.

These are test inputs, not historical research datasets: the displayed quote
timestamps must not be treated as real observed/available-at evidence. No live
provider contract test is implemented yet. The
[offline importer](../../../libs/python/ingestion/README.md) can retain these
exact bytes through the raw-storage port; it is not a live provider adapter.
The fixture-only event projection validates retained bytes and uses explicit
canonical bindings; it does not normalize bookmakers, markets, or prices.

See [mock server usage](../../mock_providers/README.md).
