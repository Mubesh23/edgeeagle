"""Private receipt compatibility; synthetic context, no provider or database calls."""

import hashlib
import json
from dataclasses import replace
from datetime import timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.sports import SportId
from edgeeagle_ingestion.events import EventCandidate, FixtureMappingEvidence
from edgeeagle_ingestion.fixture_references import resolve_fixture_references
from edgeeagle_ingestion.identity import lineage_json_value
from edgeeagle_persistence._event_snapshot import acceptance_key, canonical, decode, encode
from tests.unit.test_event_acceptance import candidate
from tests.unit.test_fixture_references import NOW, setup_references


def mapped_candidate() -> EventCandidate:
    keys, mappings, sports = setup_references()
    return replace(
        candidate(),
        mapping_evidence=FixtureMappingEvidence(
            references=resolve_fixture_references(keys, mappings, sports, as_of=NOW),
            competition_key="soccer_epl",
            home_label="Synthetic Home FC",
            away_label="Synthetic Away FC",
        ),
    )


def test_legacy_receipt_bytes_and_digest_are_frozen() -> None:
    # Captured from 47a3583 before adding evidence; not regenerated from new code.
    value = candidate()
    assert (
        acceptance_key(value) == "ba70b5a5ccb456fff43ef13e01699a2ffcbb45b20050c6090f7b543d0b494529"
    )
    assert hashlib.sha256(encode(value).encode()).hexdigest() == (
        "aa13353c204168134b7526158f51a211ace55c99a8fe0ea493722fa3f25748df"
    )
    assert "mapping_evidence" not in json.loads(encode(value))["candidate"]
    assert decode(json.loads(encode(value))) == canonical(value)


def test_mapped_receipt_round_trip_and_evidence_identity() -> None:
    value = mapped_candidate()
    evidence = value.mapping_evidence
    assert evidence is not None
    assert json.loads(encode(value))["format"] == 2
    assert decode(json.loads(encode(value))) == canonical(value)
    assert acceptance_key(value) != acceptance_key(candidate())
    changed = replace(value, mapping_evidence=replace(evidence, home_label="Other label"))
    assert acceptance_key(changed) != acceptance_key(value)
    refs = evidence.references
    changed = replace(
        value,
        mapping_evidence=replace(
            evidence,
            references=replace(
                refs, revisions=(replace(refs.revisions[0], revision=2), *refs.revisions[1:])
            ),
        ),
    )
    assert acceptance_key(changed) != acceptance_key(value)
    assert value.raw.capture.available_at is None


def test_mapped_serialization_canonicalizes_offsets_and_decimal_scale() -> None:
    value = mapped_candidate()
    evidence = value.mapping_evidence
    assert evidence is not None
    refs = evidence.references
    first = replace(refs.revisions[0], confidence=Decimal("0.50"))
    value = replace(
        value,
        mapping_evidence=replace(
            evidence, references=replace(refs, revisions=(first, *refs.revisions[1:]))
        ),
    )
    equivalent = replace(
        value,
        mapping_evidence=replace(
            evidence,
            references=replace(
                refs,
                as_of=NOW.astimezone(timezone(timedelta(hours=-5))),
                revisions=(replace(first, confidence=Decimal("0.5")), *refs.revisions[1:]),
            ),
        ),
    )
    assert encode(value) == encode(equivalent)
    assert acceptance_key(value) == acceptance_key(equivalent)
    assert decode(json.loads(encode(value))) == canonical(value)


@pytest.mark.parametrize("failure", ["source", "sport", "role", "count", "labels", "type"])
def test_mapped_candidate_rejects_inconsistent_evidence(failure: str) -> None:
    value = mapped_candidate()
    evidence = value.mapping_evidence
    assert evidence is not None
    with pytest.raises((ValueError, TypeError)):
        if failure == "source":
            refs = evidence.references
            replace(
                value,
                mapping_evidence=replace(
                    evidence,
                    references=replace(
                        refs,
                        revisions=tuple(
                            replace(row, key=replace(row.key, data_source_id=DataSourceId("other")))
                            for row in refs.revisions
                        ),
                    ),
                ),
            )
        elif failure == "sport":
            replace(value, event=replace(value.event, sport_id=SportId("other")))
        elif failure == "role":
            replace(value, entries=(replace(value.entries[0], role="AWAY"), value.entries[1]))
        elif failure == "count":
            replace(value, entries=value.entries[:1])
        elif failure == "labels":
            replace(evidence, away_label=evidence.home_label)
        else:
            replace(value, mapping_evidence="bad")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "path,value",
    [
        (("format",), 1),
        (("format",), 3),
        (("candidate", "mapping_evidence"), None),
        (("candidate", "mapping_evidence", "extra"), "bad"),
        (("candidate", "mapping_evidence", "references", "as_of"), "2020-01-01T00:00:00+00:00"),
        (("candidate", "mapping_evidence", "references", "revisions"), []),
        (("candidate", "mapping_evidence", "references", "home", "participant_id", "value"), "bad"),
    ],
)
def test_mapped_receipt_rejects_corruption(path: tuple[str, ...], value: Any) -> None:
    snapshot = json.loads(encode(mapped_candidate()))
    target = snapshot
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match="Invalid event normalization receipt"):
        decode(snapshot)


def test_format_two_requires_evidence_and_format_one_cannot_smuggle_it() -> None:
    snapshot = json.loads(encode(candidate()))
    snapshot["format"] = 2
    with pytest.raises(ValueError):
        decode(snapshot)
    snapshot["format"] = 1
    snapshot["candidate"]["mapping_evidence"] = None
    with pytest.raises(ValueError):
        decode(snapshot)


@pytest.mark.parametrize("confidence", [True, 0.5, "invalid", "NaN", "1.01", "0.50"])
def test_invalid_or_noncanonical_mapping_confidence(confidence: Any) -> None:
    snapshot = json.loads(encode(mapped_candidate()))
    snapshot["candidate"]["mapping_evidence"]["references"]["revisions"][0]["confidence"] = (
        confidence
    )
    with pytest.raises(ValueError, match="Invalid event normalization receipt"):
        decode(snapshot)


def test_decimal_encoding_is_exact_and_rejects_unsupported_objects() -> None:
    assert lineage_json_value(Decimal("-0.000")) == "0"
    assert lineage_json_value(Decimal("0.123456789012345678901234567890123456789")) == (
        "0.123456789012345678901234567890123456789"
    )
    with pytest.raises(TypeError):
        lineage_json_value(object())
