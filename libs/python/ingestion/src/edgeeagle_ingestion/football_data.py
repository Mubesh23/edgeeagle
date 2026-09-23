"""Bounded Football-Data results CSV adapter (ADR-028), no network or writes."""

import csv
import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from io import StringIO

from edgeeagle_domain._validation import aware_datetime, instance, text
from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.raw import RawPayloadIntegrityError, RawPayloadReference, RawPayloadStore
from edgeeagle_domain.sports import Event, EventId, EventParticipant
from edgeeagle_ingestion.events import EventCandidate, FixtureMappingEvidence, SoccerResultEvidence
from edgeeagle_ingestion.fixture_references import (
    FixtureReferenceKeys,
    FixtureReferenceReads,
    ResolvedFixtureReferences,
)

PARSER_VERSION = "football-data-results-csv-v1"
SEASON_PARSER_VERSION = "football-data-results-season-csv-v1"
NORMALIZER_VERSION = "football-data-results-mappings-v1"
MAX_CSV_BYTES = 1_048_576
MAX_ROWS = 100
MAX_SEASON_ROWS = 512
_REQUIRED = {"Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}


def row_locator(resource: str, division: str, match_date: date, home: str, away: str) -> str:
    """Adapter locator, not a provider-native ID or canonical event identity."""
    for value in (resource, division, home, away):
        text(value, "row locator field")
    if type(match_date) is not date or home == away:
        raise ValueError("locator requires a date and distinct team labels")
    body = json.dumps(
        [resource, division, match_date.isoformat(), home, away], separators=(",", ":")
    ).encode("utf-8")
    return "football-data-row-v1:" + hashlib.sha256(body).hexdigest()


@dataclass(frozen=True, kw_only=True)
class FootballDataRequest:
    key: ProviderEntityKey
    references: FixtureReferenceKeys
    division: str
    home_label: str
    away_label: str
    event_id: EventId
    context_version: str
    utc_offset_minutes: int

    def __post_init__(self) -> None:
        instance(self.key, ProviderEntityKey, "key")
        instance(self.references, FixtureReferenceKeys, "references")
        instance(self.event_id, EventId, "event_id")
        for name in ("division", "home_label", "away_label", "context_version"):
            text(getattr(self, name), name)
        if (
            self.key.provider_entity_type != "event"
            or self.key.data_source_id != self.references.sport.data_source_id
        ):
            raise ValueError("event and reference keys must share a source")
        if self.home_label == self.away_label:
            raise ValueError("distinct home/away labels required")
        SoccerResultEvidence(home_goals=0, away_goals=0, utc_offset_minutes=self.utc_offset_minutes)


@dataclass(frozen=True)
class _Row:
    locator: str
    division: str
    home: str
    away: str
    local_start: datetime
    home_goals: int
    away_goals: int


def _parse(body: bytes, resource: str, max_rows: int) -> tuple[_Row, ...]:
    decoded = body.decode("utf-8-sig")
    if "\x00" in decoded:
        raise ValueError("NUL in CSV")
    reader = csv.reader(StringIO(decoded, newline=""), strict=True)
    try:
        header = next(reader, [])
        if not header or len(set(header)) != len(header) or not _REQUIRED <= set(header):
            raise ValueError("missing or duplicate CSV columns")
        for field in header:
            text(field, "CSV header")
        rows: list[_Row] = []
        seen = set()
        for cells in reader:
            if len(rows) >= max_rows or len(cells) != len(header):
                raise ValueError("CSV row count or width exceeds contract")
            fields = dict(zip(header, cells, strict=True))
            for field in _REQUIRED:
                text(fields[field], field)
            if (
                re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", fields["Date"]) is None
                or re.fullmatch(r"[0-9]{2}:[0-9]{2}", fields["Time"]) is None
            ):
                raise ValueError("CSV requires dd/mm/yyyy and HH:MM")
            local = datetime.strptime(fields["Date"] + " " + fields["Time"], "%d/%m/%Y %H:%M")
            if any(
                re.fullmatch(r"(?:0|[1-9][0-9]?)", fields[name]) is None
                for name in ("FTHG", "FTAG")
            ):
                raise ValueError("invalid full-time goals")
            home_goals, away_goals = int(fields["FTHG"]), int(fields["FTAG"])
            result = "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"
            if fields["FTR"] != result:
                raise ValueError("full-time result disagrees with goals")
            locator = row_locator(
                resource, fields["Div"], local.date(), fields["HomeTeam"], fields["AwayTeam"]
            )
            if locator in seen:
                raise ValueError("duplicate CSV row locator")
            seen.add(locator)
            rows.append(
                _Row(
                    locator,
                    fields["Div"],
                    fields["HomeTeam"],
                    fields["AwayTeam"],
                    local,
                    home_goals,
                    away_goals,
                )
            )
    except csv.Error as error:
        raise ValueError("malformed CSV") from error
    if not rows:
        raise ValueError("CSV requires completed results")
    return tuple(rows)


def _read(
    store: RawPayloadStore, reference: RawPayloadReference, max_rows: int
) -> tuple[_Row, ...]:
    instance(reference, RawPayloadReference, "reference")
    if reference.size_bytes > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds byte limit")
    body = store.get(reference)
    if body is None:
        raise FileNotFoundError("retained CSV is missing")
    if len(body) != reference.size_bytes or hashlib.sha256(body).hexdigest() != reference.sha256:
        raise RawPayloadIntegrityError("retained CSV differs from reference")
    return _parse(body, reference.capture.resource, max_rows)


def _coverage(
    rows: tuple[_Row, ...],
    reference: RawPayloadReference,
    requests: tuple[FootballDataRequest, ...],
) -> None:
    by_key = {r.key.provider_entity_id: r for r in requests}
    if (
        len(by_key) != len(requests)
        or len({r.event_id for r in requests}) != len(requests)
        or set(by_key) != {row.locator for row in rows}
    ):
        raise ValueError("requests must cover every CSV row without identity collapse")
    for row in rows:
        request = by_key[row.locator]
        if request.key.data_source_id != reference.capture.data_source_id or (
            request.division,
            request.home_label,
            request.away_label,
        ) != (row.division, row.home, row.away):
            raise ValueError("CSV and explicit request do not match")


def _candidate(
    row: _Row,
    reference: RawPayloadReference,
    request: FootballDataRequest,
    refs: ResolvedFixtureReferences,
    parser_version: str,
) -> EventCandidate:
    starts_at = row.local_start.replace(
        tzinfo=timezone(timedelta(minutes=request.utc_offset_minutes))
    ).astimezone(UTC)
    if not refs.season.starts_at <= starts_at <= refs.season.ends_at:
        raise ValueError("CSV kickoff falls outside retained season")
    event = Event(
        event_id=request.event_id,
        sport_id=refs.sport.sport_id,
        competition_id=refs.competition.competition_id,
        season_id=refs.season.season_id,
        starts_at=starts_at,
        status="FINISHED",
    )
    return EventCandidate(
        event=event,
        entries=(
            EventParticipant(
                event_id=event.event_id, participant_id=refs.home.participant_id, role="HOME"
            ),
            EventParticipant(
                event_id=event.event_id, participant_id=refs.away.participant_id, role="AWAY"
            ),
        ),
        raw=reference,
        provider_key=request.key,
        parser_version=parser_version,
        normalizer_version=NORMALIZER_VERSION,
        context_version=request.context_version,
        mapping_evidence=FixtureMappingEvidence(
            references=refs, competition_key=row.division, home_label=row.home, away_label=row.away
        ),
        soccer_result=SoccerResultEvidence(
            home_goals=row.home_goals,
            away_goals=row.away_goals,
            utc_offset_minutes=request.utc_offset_minutes,
        ),
    )


def normalize_results(
    store: RawPayloadStore,
    reference: RawPayloadReference,
    requests: tuple[FootballDataRequest, ...],
    reads: FixtureReferenceReads,
    *,
    as_of: datetime,
) -> tuple[EventCandidate, ...]:
    """Read retained CSV, then resolve all context in one pinned snapshot; never write."""
    return _normalize_results(store, reference, requests, reads, as_of, PARSER_VERSION, MAX_ROWS)


def normalize_season_results(
    store: RawPayloadStore,
    reference: RawPayloadReference,
    requests: tuple[FootballDataRequest, ...],
    reads: FixtureReferenceReads,
    *,
    as_of: datetime,
) -> tuple[EventCandidate, ...]:
    """ADR-029 complete capture, at most 512 rows; not accepted by legacy manifests."""
    return _normalize_results(
        store, reference, requests, reads, as_of, SEASON_PARSER_VERSION, MAX_SEASON_ROWS
    )


def _normalize_results(
    store: RawPayloadStore,
    reference: RawPayloadReference,
    requests: tuple[FootballDataRequest, ...],
    reads: FixtureReferenceReads,
    as_of: datetime,
    parser_version: str,
    max_rows: int,
) -> tuple[EventCandidate, ...]:
    aware_datetime(as_of, "as_of")
    instance(requests, tuple, "requests")
    for request in requests:
        instance(request, FootballDataRequest, "request")
    rows = _read(store, reference, max_rows)
    _coverage(rows, reference, requests)
    by_key = {r.key.provider_entity_id: r for r in requests}
    results = []
    with reads() as resolver:
        for row in rows:
            request = by_key[row.locator]
            refs = resolver.resolve(request.references, as_of=as_of)
            instance(refs, ResolvedFixtureReferences, "references")
            if (
                tuple(r.key for r in refs.revisions) != request.references.ordered()
                or refs.as_of != as_of
            ):
                raise ValueError("resolver returned different keys or cutoff")
            results.append(_candidate(row, reference, request, refs, parser_version))
    return tuple(results)


def replay_results(
    store: RawPayloadStore, reference: RawPayloadReference, candidates: tuple[EventCandidate, ...]
) -> tuple[EventCandidate, ...]:
    """Reproduce full CSV capture using retained context only; no current lookup."""
    return _replay_results(store, reference, candidates, PARSER_VERSION, MAX_ROWS)


def replay_season_results(
    store: RawPayloadStore, reference: RawPayloadReference, candidates: tuple[EventCandidate, ...]
) -> tuple[EventCandidate, ...]:
    """Reproduce a complete ADR-029 season capture, never an individual receipt page."""
    return _replay_results(store, reference, candidates, SEASON_PARSER_VERSION, MAX_SEASON_ROWS)


def _replay_results(
    store: RawPayloadStore,
    reference: RawPayloadReference,
    candidates: tuple[EventCandidate, ...],
    parser_version: str,
    max_rows: int,
) -> tuple[EventCandidate, ...]:
    instance(reference, RawPayloadReference, "reference")
    instance(candidates, tuple, "candidates")
    requests, contexts = [], {}
    for candidate in candidates:
        instance(candidate, EventCandidate, "candidate")
        evidence, score = candidate.mapping_evidence, candidate.soccer_result
        if (
            candidate.parser_version != parser_version
            or candidate.normalizer_version != NORMALIZER_VERSION
            or evidence is None
            or score is None
            or candidate.raw != reference
        ):
            raise ValueError("CSV replay requires supported retained result receipts")
        refs = evidence.references
        requests.append(
            FootballDataRequest(
                key=candidate.provider_key,
                references=FixtureReferenceKeys(
                    **dict(
                        zip(
                            ("sport", "competition", "season", "home", "away"),
                            (r.key for r in refs.revisions),
                            strict=True,
                        )
                    )
                ),
                division=evidence.competition_key,
                home_label=evidence.home_label,
                away_label=evidence.away_label,
                event_id=candidate.event.event_id,
                context_version=candidate.context_version,
                utc_offset_minutes=score.utc_offset_minutes,
            )
        )
        contexts[candidate.provider_key.provider_entity_id] = candidate
    rows = _read(store, reference, max_rows)
    _coverage(rows, reference, tuple(requests))
    by_key = {r.key.provider_entity_id: r for r in requests}
    results = []
    for row in rows:
        original = contexts[row.locator]
        assert original.mapping_evidence is not None
        value = _candidate(
            row,
            reference,
            by_key[row.locator],
            original.mapping_evidence.references,
            parser_version,
        )
        if _ordered(value) != _ordered(original):
            raise ValueError("retained result does not reproduce from CSV")
        results.append(value)
    return tuple(results)


def _ordered(candidate: EventCandidate) -> EventCandidate:
    return replace(
        candidate, entries=tuple(sorted(candidate.entries, key=lambda e: e.participant_id.value))
    )
