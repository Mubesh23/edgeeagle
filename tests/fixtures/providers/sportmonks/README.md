# Authored Sportmonks fixture

`scheduled-v1/fixture.json` is invented test data shaped like the documented
Sportmonks v3 fixture-by-ID response with participants/state includes. All fixture,
league, season and participant IDs, names and timestamps are authored. It is not
a downloaded provider response, free-plan capture or historical research dataset.
The away participant deliberately appears first to verify role-based parsing.

`scheduled-v1/metadata.json` records the request profile, parser version, explicit
simulated snapshot clock, null actual capture time and official schema references.
No subscription, token, licensing permission or historical availability is implied.
Ordinary provider fields outside this narrow subset may be omitted from the fixture.

See [ADR-037](../../../../docs/adr/ADR-037-sportmonks-fixture-adapter.md). Run the
network-disabled tests from root:

```sh
uv run --locked --offline --all-packages pytest tests/unit/test_sportmonks_parser.py
```

The existing HTTP mock does not serve this fixture yet. No live provider contract
test, acquisition, canonical mapping, persistence or model feature is implemented.
