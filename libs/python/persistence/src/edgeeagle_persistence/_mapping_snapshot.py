"""Typed reconstruction for format-2 evidence; outer codec enforces exact JSON shape."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from edgeeagle_domain.mappings import MappingStatus, ProviderEntityKey, ProviderMappingRevision
from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.sports import (
    Competition,
    CompetitionId,
    Participant,
    ParticipantId,
    Season,
    SeasonId,
    Sport,
    SportId,
)
from edgeeagle_ingestion.events import FixtureMappingEvidence
from edgeeagle_ingestion.fixture_references import ResolvedFixtureReferences


def _participant(value: Any) -> Participant:
    return Participant(
        participant_id=ParticipantId(value["participant_id"]["value"]),
        sport_id=SportId(value["sport_id"]["value"]),
        participant_type=value["participant_type"],
        canonical_name=value["canonical_name"],
    )


def decode_evidence(value: Any) -> FixtureMappingEvidence:
    refs = value["references"]
    sport, competition, season = refs["sport"], refs["competition"], refs["season"]
    rows = refs["revisions"]
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("require five mapping revisions")
    revisions = []
    target_types: tuple[type[SportId | CompetitionId | SeasonId | ParticipantId], ...] = (
        SportId,
        CompetitionId,
        SeasonId,
        ParticipantId,
        ParticipantId,
    )
    for row, target_type in zip(rows, target_types, strict=True):
        key = row["key"]
        if row["confidence"] is not None and not isinstance(row["confidence"], str):
            raise ValueError("confidence must be a decimal string or null")
        revisions.append(
            ProviderMappingRevision(
                key=ProviderEntityKey(
                    data_source_id=DataSourceId(key["data_source_id"]["value"]),
                    provider_entity_type=key["provider_entity_type"],
                    provider_entity_id=key["provider_entity_id"],
                ),
                revision=row["revision"],
                canonical_entity_id=target_type(row["canonical_entity_id"]["value"]),
                mapping_method=row["mapping_method"],
                confidence=None if row["confidence"] is None else Decimal(row["confidence"]),
                validated_by=row["validated_by"],
                validated_at=datetime.fromisoformat(row["validated_at"]),
                available_at=datetime.fromisoformat(row["available_at"]),
                ingested_at=datetime.fromisoformat(row["ingested_at"]),
                status=MappingStatus(row["status"]),
            )
        )
    return FixtureMappingEvidence(
        competition_key=value["competition_key"],
        home_label=value["home_label"],
        away_label=value["away_label"],
        references=ResolvedFixtureReferences(
            sport=Sport(
                sport_id=SportId(sport["sport_id"]["value"]), code=sport["code"], name=sport["name"]
            ),
            competition=Competition(
                competition_id=CompetitionId(competition["competition_id"]["value"]),
                sport_id=SportId(competition["sport_id"]["value"]),
                name=competition["name"],
                country_or_region=competition["country_or_region"],
                gender_or_division=competition["gender_or_division"],
            ),
            season=Season(
                season_id=SeasonId(season["season_id"]["value"]),
                competition_id=CompetitionId(season["competition_id"]["value"]),
                name=season["name"],
                starts_at=datetime.fromisoformat(season["starts_at"]),
                ends_at=datetime.fromisoformat(season["ends_at"]),
            ),
            home=_participant(refs["home"]),
            away=_participant(refs["away"]),
            revisions=tuple(revisions),
            as_of=datetime.fromisoformat(refs["as_of"]),
        ),
    )
