"""Real HTTP to the local mock container; no provider credentials or calls."""

import json
import os

import httpx
import pytest

from tests.mock_providers.server import FIXTURE, ODDS_PATH


def test_http_fixture_matches_disk_and_recovers_after_error() -> None:
    port = int(os.environ.get("EDGEEAGLE_MOCK_PROVIDER_PORT", "9080"))
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5) as client:
        first = client.get(
            ODDS_PATH, params={"regions": "us", "markets": "h2h", "oddsFormat": "decimal"}
        )
        assert first.status_code == 200
        assert first.content == FIXTURE.read_bytes()
        assert first.headers["X-Mock-Origin"] == "synthetic"
        assert client.get(ODDS_PATH, headers={"X-Mock-Scenario": "server-error"}).status_code == 503
        assert client.get(ODDS_PATH).content == first.content


@pytest.mark.parametrize(
    "scenario,status",
    [
        ("empty", 200),
        ("rate-limit", 429),
        ("server-error", 503),
        ("malformed", 200),
        ("unknown", 400),
    ],
)
def test_http_error_and_empty_scenarios(scenario: str, status: int) -> None:
    port = int(os.environ.get("EDGEEAGLE_MOCK_PROVIDER_PORT", "9080"))
    response = httpx.get(
        f"http://127.0.0.1:{port}{ODDS_PATH}",
        headers={"X-Mock-Scenario": scenario},
        trust_env=False,
        timeout=5,
    )
    assert response.status_code == status
    if scenario == "rate-limit":
        assert response.headers["Retry-After"] == "1"
    elif scenario == "empty":
        assert response.json() == []
    elif scenario == "malformed":
        with pytest.raises(json.JSONDecodeError):
            response.json()
