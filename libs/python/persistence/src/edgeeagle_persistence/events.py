"""Transactional initial event acceptance; no refresh policy or publication yet."""

from sqlalchemy import Connection, text

from edgeeagle_domain._validation import instance
from edgeeagle_domain.repositories import DuplicateRecordError
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.events import EventAcceptanceConflict, EventCandidate
from edgeeagle_persistence._event_snapshot import acceptance_key, canonical, decode, encode
from edgeeagle_persistence._transactions import insert, require_transaction
from edgeeagle_persistence.sports import PostgresSportsRepository


class PostgresEventAcceptanceRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, event_id: EventId) -> EventCandidate | None:
        instance(event_id, EventId, "event_id")
        require_transaction(self._connection)
        row = (
            self._connection.execute(
                text(
                    "SELECT data_source_id, acceptance_key, snapshot FROM event_normalizations "
                    "WHERE event_id = :id"
                ),
                {"id": event_id.value},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        candidate = decode(row["snapshot"])
        if (
            candidate.event.event_id != event_id
            or candidate.raw.capture.data_source_id.value != row["data_source_id"]
            or acceptance_key(candidate) != row["acceptance_key"]
        ):
            raise ValueError("Receipt identity does not match its indexed columns")
        return candidate

    def accept(self, candidate: EventCandidate) -> bool:
        instance(candidate, EventCandidate, "candidate")
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "READ COMMITTED":
            raise RuntimeError("Event acceptance requires READ COMMITTED isolation")
        candidate = canonical(candidate)
        sports = PostgresSportsRepository(self._connection)
        try:
            with insert(self._connection):
                try:
                    sports.add_event(candidate.event, candidate.entries)
                except DuplicateRecordError:
                    # Wait for the competing first insert, then use fresh statement snapshots.
                    self._connection.execute(
                        text("SELECT event_id FROM events WHERE event_id = :id FOR UPDATE"),
                        {"id": candidate.event.event_id.value},
                    )
                    if (
                        self.get(candidate.event.event_id) != candidate
                        or sports.get_event(candidate.event.event_id) != candidate.event
                        or sports.get_event_participants(candidate.event.event_id)
                        != candidate.entries
                    ):
                        raise EventAcceptanceConflict(
                            "Event differs from initial acceptance"
                        ) from None
                    return False
                self._connection.execute(
                    text(
                        "INSERT INTO event_normalizations "
                        "(event_id, data_source_id, acceptance_key, snapshot) "
                        "VALUES (:event, :source, :key, CAST(:snapshot AS jsonb))"
                    ),
                    {
                        "event": candidate.event.event_id.value,
                        "source": candidate.raw.capture.data_source_id.value,
                        "key": acceptance_key(candidate),
                        "snapshot": encode(candidate),
                    },
                )
                return True
        except DuplicateRecordError as error:
            # The enclosing savepoint has already removed this attempt's event and entries.
            raise EventAcceptanceConflict("Lineage already accepted for another event") from error
