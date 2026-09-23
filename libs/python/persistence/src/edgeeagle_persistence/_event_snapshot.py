"""Private receipt formats 1 and 2; not an API or provider wire contract."""

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import InvalidOperation
from typing import Any

from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture, RawPayloadReference
from edgeeagle_domain.sports import (
    CompetitionId,
    Event,
    EventId,
    EventParticipant,
    ParticipantId,
    SeasonId,
    SportId,
)
from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.identity import acceptance_key as acceptance_key
from edgeeagle_ingestion.identity import lineage_json_value
from edgeeagle_persistence._mapping_snapshot import decode_evidence


def canonical(candidate: EventCandidate) -> EventCandidate:
    return replace(
        candidate,
        event=replace(candidate.event, starts_at=candidate.event.starts_at.astimezone(UTC)),
        entries=tuple(sorted(candidate.entries, key=lambda entry: entry.participant_id.value)),
    )


def _json(value: object) -> str:
    return json.dumps(value, default=lineage_json_value, sort_keys=True, separators=(",", ":"))


def encode(candidate: EventCandidate) -> str:
    fields = asdict(canonical(candidate))
    version = 2
    if candidate.mapping_evidence is None:
        del fields["mapping_evidence"]
        version = 1
    return _json({"format": version, "candidate": fields})


def decode(snapshot: Any) -> EventCandidate:
    """Revalidate the JSON boundary; reject extra fields and noncanonical encodings."""
    try:
        if type(snapshot["format"]) is not int or snapshot["format"] not in (1, 2):
            raise ValueError("unsupported receipt format")
        value = snapshot["candidate"]
        event = value["event"]
        raw, key = value["raw"], value["provider_key"]
        capture = raw["capture"]
        candidate = canonical(
            EventCandidate(
                event=Event(
                    event_id=EventId(event["event_id"]["value"]),
                    sport_id=SportId(event["sport_id"]["value"]),
                    competition_id=CompetitionId(event["competition_id"]["value"]),
                    season_id=SeasonId(event["season_id"]["value"]),
                    starts_at=datetime.fromisoformat(event["starts_at"]),
                    status=event["status"],
                    venue_location=event["venue_location"],
                ),
                entries=tuple(
                    EventParticipant(
                        event_id=EventId(entry["event_id"]["value"]),
                        participant_id=ParticipantId(entry["participant_id"]["value"]),
                        role=entry["role"],
                    )
                    for entry in value["entries"]
                ),
                raw=RawPayloadReference(
                    capture=RawCapture(
                        data_source_id=DataSourceId(capture["data_source_id"]["value"]),
                        resource=capture["resource"],
                        ingested_at=datetime.fromisoformat(capture["ingested_at"]),
                        effective_at=_optional_time(capture["effective_at"]),
                        observed_at=_optional_time(capture["observed_at"]),
                        available_at=_optional_time(capture["available_at"]),
                    ),
                    sha256=raw["sha256"],
                    size_bytes=raw["size_bytes"],
                ),
                provider_key=ProviderEntityKey(
                    data_source_id=DataSourceId(key["data_source_id"]["value"]),
                    provider_entity_type=key["provider_entity_type"],
                    provider_entity_id=key["provider_entity_id"],
                ),
                parser_version=value["parser_version"],
                normalizer_version=value["normalizer_version"],
                context_version=value["context_version"],
                mapping_evidence=(
                    decode_evidence(value["mapping_evidence"]) if snapshot["format"] == 2 else None
                ),
            )
        )
        if encode(candidate) != _json(snapshot):
            raise ValueError("noncanonical receipt")
        return candidate
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        raise ValueError("Invalid event normalization receipt") from error


def _optional_time(value: Any) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)
