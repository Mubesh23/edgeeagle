"""Verify immutable acceptance evidence and record one transactional consumer effect."""

from sqlalchemy import Connection, text

from edgeeagle_domain._validation import instance
from edgeeagle_ingestion.consumer import EventConsumptionConflict
from edgeeagle_ingestion.notifications import EventAccepted
from edgeeagle_persistence._transactions import require_transaction
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository


class PostgresEventAcceptedHandler:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def handle(self, notification: EventAccepted) -> bool:
        instance(notification, EventAccepted, "notification")
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "READ COMMITTED":
            raise RuntimeError("Consumption writes require READ COMMITTED isolation")
        with self._connection.begin_nested():
            original = PostgresEventAcceptanceRepository(self._connection).get_notification(
                notification.canonical_event_id
            )
            if original != notification:
                raise EventConsumptionConflict("Notification differs from immutable acceptance")
            result = self._connection.execute(
                text(
                    "INSERT INTO event_acceptance_consumptions (notification_id) VALUES (:id) "
                    "ON CONFLICT (notification_id) DO NOTHING RETURNING notification_id"
                ),
                {"id": notification.event_id},
            )
            return result.scalar_one_or_none() is not None
