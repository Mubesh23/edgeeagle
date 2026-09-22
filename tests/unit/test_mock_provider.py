"""Exercise fixture routing with network access disabled."""

import json

import pytest

from tests.mock_providers.server import FIXTURE, ODDS_PATH, resolve_response


def test_fixture_metadata_and_source_venue_separation() -> None:
    metadata = json.loads(FIXTURE.with_name("metadata.json").read_text())
    payload = json.loads(FIXTURE.read_bytes())
    assert metadata["origin"] == "synthetic"
    assert metadata["captured_at"] is None
    assert metadata["data_source"] == "THE_ODDS_API"
    assert metadata["endpoint"] == ODDS_PATH
    assert metadata["payload"] == FIXTURE.name
    assert payload[0]["bookmakers"][0]["key"] == "bovada"


@pytest.mark.parametrize(
    "scenario,status",
    [
        ("success", 200),
        ("empty", 200),
        ("rate-limit", 429),
        ("server-error", 503),
        ("malformed", 200),
        ("unknown", 400),
    ],
)
def test_scenarios_are_repeatable_and_do_not_change_success(scenario: str, status: int) -> None:
    success = FIXTURE.read_bytes()
    first = resolve_response(ODDS_PATH, scenario, success)
    assert first.status == status
    assert resolve_response(ODDS_PATH, scenario, success) == first
    assert resolve_response(ODDS_PATH, "success", success).body == success


@pytest.mark.parametrize(
    "query",
    [
        "oddsFormat=american",
        "markets=totals",
        "regions=uk",
        "unexpected=1",
        "markets=h2h&markets=totals",
    ],
)
def test_unsupported_queries_are_rejected(query: str) -> None:
    assert resolve_response(f"{ODDS_PATH}?{query}", "success", b"[]").status == 400


def test_unknown_paths_never_become_file_or_proxy_requests() -> None:
    assert resolve_response("/../../metadata.json", "success", b"[]").status == 404
