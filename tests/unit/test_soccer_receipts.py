"""Additive score-bearing receipts preserve legacy encodings and strict evidence."""

import json
from dataclasses import replace
from typing import Any

import pytest

from edgeeagle_ingestion.events import EventCandidate, SoccerResultEvidence
from edgeeagle_persistence._event_snapshot import acceptance_key, canonical, decode, encode
from tests.unit.test_mapped_receipts import mapped_candidate


def result_candidate() -> EventCandidate:
    value = mapped_candidate()
    return replace(
        value,
        event=replace(value.event, status="FINISHED"),
        soccer_result=SoccerResultEvidence(home_goals=2, away_goals=1, utc_offset_minutes=60),
        parser_version="football-data-results-csv-v1",
        normalizer_version="football-data-results-mappings-v1",
    )


def test_score_receipt_roundtrip_and_identity() -> None:
    value = result_candidate()
    snapshot = json.loads(encode(value))
    assert snapshot["format"] == 3
    assert decode(snapshot) == canonical(value)
    for evidence in (
        SoccerResultEvidence(home_goals=1, away_goals=1, utc_offset_minutes=60),
        SoccerResultEvidence(home_goals=2, away_goals=1, utc_offset_minutes=0),
    ):
        assert acceptance_key(replace(value, soccer_result=evidence)) != acceptance_key(value)
    assert "soccer_result" not in json.loads(encode(mapped_candidate()))["candidate"]
    assert value.raw.capture.available_at is None


@pytest.mark.parametrize(
    "field,bad",
    [
        ("home_goals", True),
        ("home_goals", -1),
        ("away_goals", 100),
        ("away_goals", 1.0),
        ("utc_offset_minutes", None),
        ("utc_offset_minutes", 841),
        ("utc_offset_minutes", -841),
    ],
)
def test_invalid_score_evidence(field: str, bad: Any) -> None:
    fields = {"home_goals": 2, "away_goals": 1, "utc_offset_minutes": 60}
    fields[field] = bad
    with pytest.raises((TypeError, ValueError)):
        SoccerResultEvidence(**fields)


@pytest.mark.parametrize("change", ["missing-mapping", "status", "type", "sport", "participant"])
def test_result_candidate_requires_consistent_context(change: str) -> None:
    value = result_candidate()
    with pytest.raises((TypeError, ValueError)):
        if change == "missing-mapping":
            replace(value, mapping_evidence=None)
        elif change == "status":
            replace(value, event=replace(value.event, status="SCHEDULED"))
        elif change == "type":
            replace(value, soccer_result={})  # type: ignore[arg-type]
        else:
            evidence = value.mapping_evidence
            assert evidence is not None
            refs = evidence.references
            refs = (
                replace(refs, sport=replace(refs.sport, code="tennis"))
                if change == "sport"
                else replace(refs, home=replace(refs.home, participant_type="PLAYER"))
            )
            replace(value, mapping_evidence=replace(evidence, references=refs))


@pytest.mark.parametrize("change", ["missing", "extra", "bad-score", "format-two", "null"])
def test_score_receipt_rejects_corruption(change: str) -> None:
    snapshot = json.loads(encode(result_candidate()))
    if change == "missing":
        del snapshot["candidate"]["soccer_result"]
    elif change == "extra":
        snapshot["candidate"]["soccer_result"]["extra"] = 1
    elif change == "bad-score":
        snapshot["candidate"]["soccer_result"]["home_goals"] = True
    elif change == "format-two":
        snapshot["format"] = 2
    else:
        snapshot["candidate"]["soccer_result"] = None
    with pytest.raises(ValueError, match="Invalid event normalization receipt"):
        decode(snapshot)
