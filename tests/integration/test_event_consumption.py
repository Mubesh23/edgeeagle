from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_ingestion.consumer import EventConsumptionConflict
from edgeeagle_persistence.consumer import PostgresEventAcceptedHandler
from tests.integration.test_event_acceptance import seed
from tests.integration.test_outbox_delivery import enqueue
from tests.integration.test_repositories import repository_engine as repository_engine


def test_event_consumption_concurrent_duplicates_and_conflict(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        message = enqueue(connection)

    def handle() -> bool:
        with repository_engine.begin() as connection:
            return PostgresEventAcceptedHandler(connection).handle(message)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: handle(), range(2)))
    assert sorted(results) == [False, True]
    with repository_engine.begin() as connection:
        handler = PostgresEventAcceptedHandler(connection)
        for changed in (
            replace(message, event_id="changed"),
            replace(message, correlation_id="changed"),
            replace(message, acceptance_key="0" * 64),
        ):
            with pytest.raises(EventConsumptionConflict):
                handler.handle(changed)
        assert handler.handle(message) is False
        assert connection.scalar(text("SELECT count(*) FROM event_acceptance_consumptions")) == 1
        for sql in (
            "DELETE FROM event_acceptance_consumptions",
            "UPDATE event_acceptance_consumptions SET verified_at = clock_timestamp()",
            "TRUNCATE event_acceptance_consumptions",
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text(sql))


def test_event_consumption_rollback_and_guards(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        message = enqueue(connection)
    with repository_engine.connect() as connection:
        with pytest.raises(RuntimeError, match="active"):
            PostgresEventAcceptedHandler(connection).handle(message)
        with pytest.raises(RuntimeError, match="abort"), connection.begin():
            assert PostgresEventAcceptedHandler(connection).handle(message)
            raise RuntimeError("abort")
    with repository_engine.begin() as connection:
        assert PostgresEventAcceptedHandler(connection).handle(message)
        assert connection.scalar(text("SELECT count(*) FROM event_acceptance_consumptions")) == 1
    with repository_engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        with connection.begin(), pytest.raises(RuntimeError, match="READ COMMITTED"):
            PostgresEventAcceptedHandler(connection).handle(message)
