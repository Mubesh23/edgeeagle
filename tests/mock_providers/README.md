# Local provider mock

This stdlib-only Python HTTP server replays synthetic fixtures. It does not proxy,
download, authenticate against, or send requests to providers. It contains no
canonical normalization, pricing, strategy, or other business logic.

`scripts/local-up` builds the fixture image and waits for its health check.
The mock binds to `127.0.0.1:9080` on the host; override with exported
`EDGEEAGLE_MOCK_PROVIDER_PORT`. `scripts/local-down` removes its container along
with the other local services. It has no persistent state. The image runs as a
non-root user with a read-only filesystem and copies only server code and fixtures.

To run without Docker from the repository root:

```sh
python3 -m tests.mock_providers.server
```

That process defaults to loopback port 9080; `MOCK_PROVIDER_HOST` and
`MOCK_PROVIDER_PORT` configure the standalone process only.

Supported routes:

- `GET /health`: mock liveness.
- `GET /v4/sports/soccer_epl/odds`: synthetic The Odds API-shaped response.

The odds route accepts optional `regions=us`, `markets=h2h`, `oddsFormat=decimal`,
and `dateFormat=iso`. It accepts but ignores `apiKey`; no key is required. Unknown
parameters or unsupported values return 400 rather than suggesting they are
implemented. Other paths return 404. Non-GET requests use the HTTP server's 501
response. Request URLs and query strings are not logged.

Select a per-request scenario with `X-Mock-Scenario`:

| Value               | Status | Behavior                                   |
| ------------------- | ------ | ------------------------------------------ |
| `success` (default) | 200    | Exact bytes of the checked-in odds payload |
| `empty`             | 200    | Empty list                                 |
| `rate-limit`        | 429    | Synthetic error and `Retry-After: 1`       |
| `server-error`      | 503    | Synthetic upstream failure                 |
| `malformed`         | 200    | Deliberately invalid JSON                  |
| Any other value     | 400    | Unknown scenario                           |

Bodies/statuses are fixed: no counters, random outcomes, or clock-dependent quote
data. A failed request does not change another request's response. Error bodies
and Retry-After are harness conventions, not verified provider behavior. Responses
are marked `X-Mock-Origin: synthetic`. Default HTTP Date headers reflect serving
time and are not market timestamps.

`scripts/test-unit` runs routing/provenance tests with sockets disabled.
`scripts/test-integration` verifies actual loopback HTTP, fixture byte equality,
failure isolation, empty/error/malformed responses, and the retry header.
`scripts/validate` includes both. No paid calls or live contract tests are involved.

Server/fixture edits are included when `scripts/local-up` invokes Compose with `--build`.
The initial Docker context allowlist covers only the first provider; extend it
alongside future fixture sets. Provider adapters and broader endpoint coverage
remain later roadmap work.
