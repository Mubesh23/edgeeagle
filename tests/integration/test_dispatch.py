"""Real transaction boundaries with a recording (not network) publisher."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import Engine, text

from edgeeagle_ingestion.delivery import DeliveryClaim, DeliveryStatus, OutboxDeliveryRepository
from edgeeagle_ingestion.dispatch import DispatchResult, RetryablePublicationError, dispatch_one
from edgeeagle_persistence.delivery import PostgresOutboxDeliveryRepository
from tests.integration.test_event_acceptance import seed
from tests.integration.test_outbox_delivery import enqueue, expire
from tests.integration.test_repositories import repository_engine as repository_engine


@pytest.mark.parametrize("failure", ["none", "send", "claim_commit", "ack_commit"])
def test_dispatch_transaction_boundaries_and_recovery(
    repository_engine: Engine, failure: str
) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        message = enqueue(connection)

    active = False
    attempts = 0
    sent: list[DeliveryClaim] = []

    @contextmanager
    def transactions() -> Iterator[OutboxDeliveryRepository]:
        nonlocal active, attempts
        attempts += 1
        active = True
        try:
            with repository_engine.begin() as connection:
                yield PostgresOutboxDeliveryRepository(connection)
                if (failure == "claim_commit" and attempts == 1) or (
                    failure == "ack_commit" and attempts == 2
                ):
                    raise RuntimeError("injected before commit")
        finally:
            active = False

    class Publisher:
        def publish(self, claim: DeliveryClaim) -> None:
            assert not active
            with repository_engine.begin() as connection:
                # Another connection sees a committed claim and can lock the row.
                connection.execute(text("SET LOCAL lock_timeout = '1s'"))
                connection.execute(text("SELECT * FROM event_outbox_delivery FOR UPDATE NOWAIT"))
                state = PostgresOutboxDeliveryRepository(connection).get(message.event_id)
                assert state is not None and state.status is DeliveryStatus.LEASED
                assert state.attempts == claim.attempt
            sent.append(claim)
            if failure == "send":
                raise RetryablePublicationError("acceptance unknown")

    def run() -> DispatchResult:
        return dispatch_one(
            transactions,
            Publisher(),
            lease_for=timedelta(minutes=1),
            retry_after=timedelta(minutes=1),
        )

    if failure.endswith("commit"):
        with pytest.raises(RuntimeError, match="injected"):
            run()
    else:
        result = run()
        assert result is (
            DispatchResult.RETRY_SCHEDULED if failure == "send" else DispatchResult.PUBLISHED
        )

    with repository_engine.begin() as connection:
        state = PostgresOutboxDeliveryRepository(connection).get(message.event_id)
        assert state is not None
        assert (
            state.status
            is {
                "none": DeliveryStatus.PUBLISHED,
                "send": DeliveryStatus.PENDING,
                "claim_commit": DeliveryStatus.PENDING,
                "ack_commit": DeliveryStatus.LEASED,
            }[failure]
        )
        assert state.attempts == (0 if failure == "claim_commit" else 1)
        if failure == "ack_commit":
            expire(connection, message.event_id)
        elif failure == "send":
            assert state.ready_at > sent[0].claimed_at
            connection.execute(
                text("UPDATE event_outbox_delivery SET ready_at = clock_timestamp()")
            )

    original_failure = failure
    failure = "none"
    if original_failure == "none":
        assert run() is DispatchResult.IDLE
    else:
        assert run() is DispatchResult.PUBLISHED
    assert all(claim.notification == message for claim in sent)
    assert len(sent) == (2 if original_failure in {"send", "ack_commit"} else 1)
    if len(sent) == 2:
        assert [claim.attempt for claim in sent] == [1, 2]
