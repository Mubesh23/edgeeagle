"""Verified read-only access to immutable Sportmonks observation receipts."""

import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_ingestion.sportmonks_acceptance import SportmonksReceiptConflict
from edgeeagle_ingestion.sportmonks_normalization import NormalizedSportmonksFixture
from edgeeagle_ingestion.sportmonks_receipts import (
    decode_sportmonks_receipt,
    encode_sportmonks_receipt,
    sportmonks_capture_identity,
)

from ._transactions import require_transaction
from .mappings import PostgresMappingRepository
from .provenance import PostgresDataSourceRepository
from .sports import PostgresSportsRepository


class SportmonksReceiptIntegrityError(RuntimeError):
    """Stored Sportmonks bytes or indexed receipt identity failed verification."""


class PostgresSportmonksReceiptReader:
    """Read complete, codec-validated receipts without refreshing reference state."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, capture_id: str) -> NormalizedSportmonksFixture | None:
        require_transaction(self._connection)
        if not isinstance(capture_id, str) or not re.fullmatch(r"[0-9a-f]{64}", capture_id):
            raise ValueError("capture identity must be a SHA-256 digest")
        row = (
            self._connection.execute(
                text("""
                SELECT data_source_id, event_id, native_fixture_id, receipt_format, receipt
                FROM sportmonks_capture_receipts WHERE capture_id = :capture_id
            """),
                {"capture_id": capture_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        try:
            body = row["receipt"].encode("ascii")
            receipt = decode_sportmonks_receipt(body)
            if (
                row["receipt_format"] != 1
                or row["data_source_id"] != receipt.manifest.raw.capture.data_source_id.value
                or row["event_id"] != receipt.references.event.event_id.value
                or row["native_fixture_id"] != receipt.native.fixture_id
                or sportmonks_capture_identity(receipt) != capture_id
            ):
                raise SportmonksReceiptIntegrityError(
                    "Stored Sportmonks receipt differs from indexed identity"
                )
        except (UnicodeError, ValueError) as exc:
            raise SportmonksReceiptIntegrityError("Stored Sportmonks receipt is invalid") from exc
        return receipt


class PostgresSportmonksReceiptRepository(PostgresSportmonksReceiptReader):
    """Accept immutable observations in a caller-owned READ COMMITTED transaction."""

    def _lock_references(self, receipt: NormalizedSportmonksFixture) -> None:
        refs = receipt.references
        context = refs.context
        # Fixed table order; IDs within each table are acquired lexically. Event
        # parents precede event entries, which child writers must follow too.
        records = (
            ("data_sources", "data_source_id", (refs.source.data_source_id.value,)),
            ("sports", "sport_id", (context.sport.sport_id.value,)),
            ("competitions", "competition_id", (context.competition.competition_id.value,)),
            ("seasons", "season_id", (context.season.season_id.value,)),
            (
                "participants",
                "participant_id",
                tuple(
                    sorted({context.home.participant_id.value, context.away.participant_id.value})
                ),
            ),
            ("events", "event_id", (refs.event.event_id.value,)),
        )
        for table, column, identifiers in records:
            for identifier in sorted(identifiers):
                found = self._connection.scalar(
                    text(f"SELECT {column} FROM {table} WHERE {column} = :id FOR UPDATE"),
                    {"id": identifier},
                )
                if found is None:
                    raise SportmonksReceiptConflict("Sportmonks canonical reference is missing")
        self._connection.execute(
            text("""
                SELECT participant_id FROM event_participants
                WHERE event_id = :event_id ORDER BY participant_id FOR UPDATE
            """),
            {"event_id": refs.event.event_id.value},
        ).all()

    def _verify_references(self, receipt: NormalizedSportmonksFixture) -> None:
        refs = receipt.references
        context = refs.context
        sports = PostgresSportsRepository(self._connection)
        if PostgresDataSourceRepository(self._connection).get(refs.source.data_source_id) != (
            refs.source
        ):
            raise SportmonksReceiptConflict("Sportmonks source context differs")
        if (
            sports.get_sport(context.sport.sport_id) != context.sport
            or sports.get_competition(context.competition.competition_id) != context.competition
            or sports.get_season(context.season.season_id) != context.season
            or sports.get_participant(context.home.participant_id) != context.home
            or sports.get_participant(context.away.participant_id) != context.away
            or sports.get_event(refs.event.event_id) != refs.event
            or set(sports.get_event_participants(refs.event.event_id)) != set(refs.entries)
        ):
            raise SportmonksReceiptConflict("Sportmonks canonical context differs")
        mappings = PostgresMappingRepository(self._connection)
        for revision in refs.revisions:
            history = mappings.history(revision.key)
            if revision.revision > len(history) or history[revision.revision - 1] != revision:
                raise SportmonksReceiptConflict("Selected Sportmonks mapping revision differs")

    def accept(self, receipt: NormalizedSportmonksFixture) -> int:
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "READ COMMITTED":
            raise ValueError("Sportmonks acceptance requires READ COMMITTED isolation")
        body = encode_sportmonks_receipt(receipt)
        value = decode_sportmonks_receipt(body)
        identity = sportmonks_capture_identity(value)
        try:
            with self._connection.begin_nested():
                existing = self.get(identity)
                if existing is not None:
                    if encode_sportmonks_receipt(existing) != body:
                        raise SportmonksReceiptConflict(
                            "Capture identity already retains different Sportmonks evidence"
                        )
                    return 0

                self._lock_references(value)
                self._verify_references(value)
                inserted = self._connection.scalar(
                    text("""
                        INSERT INTO sportmonks_capture_receipts
                            (capture_id, data_source_id, event_id, native_fixture_id,
                             receipt_format, receipt)
                        VALUES (:capture_id, :data_source_id, :event_id, :fixture_id, 1, :receipt)
                        ON CONFLICT (capture_id) DO NOTHING
                        RETURNING capture_id
                    """),
                    {
                        "capture_id": identity,
                        "data_source_id": value.manifest.raw.capture.data_source_id.value,
                        "event_id": value.references.event.event_id.value,
                        "fixture_id": value.native.fixture_id,
                        "receipt": body.decode("ascii"),
                    },
                )
                if inserted is None:
                    # READ COMMITTED gives this statement a fresh snapshot after
                    # the conflicting insert has committed or been rolled back.
                    retained = self.get(identity)
                    if retained is None or encode_sportmonks_receipt(retained) != body:
                        raise SportmonksReceiptConflict(
                            "Capture identity already retains different Sportmonks evidence"
                        )
                    return 0

                retained = self.get(identity)
                if retained is None or encode_sportmonks_receipt(retained) != body:
                    raise SportmonksReceiptConflict("Accepted Sportmonks receipt failed readback")
                return 1
        except IntegrityError as exc:
            raise SportmonksReceiptConflict(
                "Sportmonks receipt acceptance violates stored constraints"
            ) from exc


def sportmonks_receipt_transactions(
    engine: Engine,
) -> Callable[[], AbstractContextManager[PostgresSportmonksReceiptRepository]]:
    """Supply bounded READ COMMITTED transactions for the ingestion workflow.

    Engine and pool lifecycle remain caller-owned. Each context commits on normal
    exit and rolls back on errors; repository methods never commit or retry.
    """

    @contextmanager
    def transactions() -> Iterator[PostgresSportmonksReceiptRepository]:
        with engine.connect().execution_options(isolation_level="READ COMMITTED") as connection:
            with connection.begin():
                connection.execute(text("SET LOCAL statement_timeout = '5s'"))
                connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                connection.execute(text("SET LOCAL idle_in_transaction_session_timeout = '5s'"))
                yield PostgresSportmonksReceiptRepository(connection)

    return transactions
