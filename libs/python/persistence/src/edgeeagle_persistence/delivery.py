"""PostgreSQL delivery leases. Commit claims BEFORE publishing outside a transaction."""

from datetime import datetime, timedelta

from sqlalchemy import Connection, RowMapping, text

from edgeeagle_domain._validation import instance
from edgeeagle_domain._validation import text as validate_text
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.delivery import (
    DeliveryClaim,
    DeliveryLeaseLost,
    DeliveryState,
    DeliveryStatus,
    validate_duration,
)
from edgeeagle_persistence._transactions import require_transaction
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository


def _state(row: RowMapping) -> DeliveryState:
    return DeliveryState(
        notification_id=row["notification_id"],
        status=DeliveryStatus(row["status"]),
        attempts=row["attempts"],
        ready_at=row["ready_at"],
        claimed_at=row["claimed_at"],
        lease_expires_at=row["lease_expires_at"],
        acknowledged_at=row["acknowledged_at"],
    )


class PostgresOutboxDeliveryRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def _write_guard(self) -> None:
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "READ COMMITTED":
            raise RuntimeError("Delivery writes require READ COMMITTED isolation")

    def _now(self) -> datetime:
        value = self._connection.scalar(text("SELECT clock_timestamp()"))
        assert isinstance(value, datetime)
        return value

    def get(self, notification_id: str) -> DeliveryState | None:
        validate_text(notification_id, "notification_id")
        require_transaction(self._connection)
        row = (
            self._connection.execute(
                text("SELECT * FROM event_outbox_delivery WHERE notification_id = :id"),
                {"id": notification_id},
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _state(row)

    def claim(self, *, lease_for: timedelta) -> DeliveryClaim | None:
        validate_duration(lease_for, maximum=timedelta(hours=1))
        self._write_guard()
        with self._connection.begin_nested():
            row = (
                self._connection.execute(
                    text(
                        "SELECT d.*, o.canonical_event_id FROM event_outbox_delivery d "
                        "JOIN event_outbox o USING (notification_id) "
                        "WHERE (d.status = 'PENDING' AND d.ready_at <= statement_timestamp()) "
                        "OR (d.status = 'LEASED' AND d.lease_expires_at <= statement_timestamp()) "
                        "ORDER BY d.ready_at, d.notification_id LIMIT 1 FOR UPDATE OF d SKIP LOCKED"
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            previous = _state(row)
            notification = PostgresEventAcceptanceRepository(self._connection).get_notification(
                EventId(row["canonical_event_id"])
            )
            if notification is None:
                raise ValueError("Delivery intent is missing")
            now = self._now()
            claim = DeliveryClaim(
                notification=notification,
                attempt=previous.attempts + 1,
                claimed_at=now,
                lease_expires_at=now + lease_for,
            )
            self._connection.execute(
                text(
                    "UPDATE event_outbox_delivery SET status = 'LEASED', attempts = :attempt, "
                    "claimed_at = :now, lease_expires_at = :expiry WHERE notification_id = :id"
                ),
                {
                    "attempt": claim.attempt,
                    "now": now,
                    "expiry": claim.lease_expires_at,
                    "id": notification.event_id,
                },
            )
            return claim

    def _live_claim(self, claim: DeliveryClaim) -> datetime:
        row = (
            self._connection.execute(
                text("SELECT * FROM event_outbox_delivery WHERE notification_id = :id FOR UPDATE"),
                {"id": claim.notification.event_id},
            )
            .mappings()
            .one_or_none()
        )
        now = self._now()  # Read time after any wait for the row lock.
        if row is None:
            raise DeliveryLeaseLost("Delivery no longer exists")
        state = _state(row)
        if (
            state.status is not DeliveryStatus.LEASED
            or state.attempts != claim.attempt
            or state.claimed_at is None
            or state.lease_expires_at is None
            or state.claimed_at != claim.claimed_at
            or state.lease_expires_at != claim.lease_expires_at
            or not state.claimed_at <= now < state.lease_expires_at
        ):
            raise DeliveryLeaseLost("Delivery claim expired or was superseded/completed")
        return now

    def acknowledge(self, claim: DeliveryClaim) -> None:
        instance(claim, DeliveryClaim, "claim")
        self._write_guard()
        with self._connection.begin_nested():
            now = self._live_claim(claim)
            self._connection.execute(
                text(
                    "UPDATE event_outbox_delivery SET status = 'PUBLISHED', acknowledged_at = :now "
                    "WHERE notification_id = :id"
                ),
                {"id": claim.notification.event_id, "now": now},
            )

    def retry(self, claim: DeliveryClaim, *, retry_after: timedelta) -> None:
        instance(claim, DeliveryClaim, "claim")
        validate_duration(retry_after, maximum=timedelta(days=1))
        self._write_guard()
        with self._connection.begin_nested():
            now = self._live_claim(claim)
            self._connection.execute(
                text(
                    "UPDATE event_outbox_delivery SET status = 'PENDING', ready_at = :due, "
                    "claimed_at = NULL, lease_expires_at = NULL WHERE notification_id = :id"
                ),
                {"id": claim.notification.event_id, "due": now + retry_after},
            )
