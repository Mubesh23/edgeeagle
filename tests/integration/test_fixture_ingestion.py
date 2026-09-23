"""Retained fixture through canonical acceptance, broker, consumer, and read API."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine, text

from edgeeagle_api.local import event_transactions
from edgeeagle_api.main import create_app
from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture
from edgeeagle_ingestion.consumer import ConsumptionResult, EventAcceptedHandler, consume_one
from edgeeagle_ingestion.delivery import DeliveryClaim, DeliveryStatus, OutboxDeliveryRepository
from edgeeagle_ingestion.dispatch import DispatchResult, dispatch_one
from edgeeagle_ingestion.notifications import EventAccepted
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.service import OfflineDatasetImporter, ingest_raw
from edgeeagle_ingestion.synthetic_events import normalize_fixture_events
from edgeeagle_persistence.consumer import PostgresEventAcceptedHandler
from edgeeagle_persistence.delivery import PostgresOutboxDeliveryRepository
from edgeeagle_persistence.eventbridge import EventBridgePublisher
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from tests.integration.sqs_routing import Routing
from tests.integration.sqs_routing import event_bus as event_bus
from tests.integration.sqs_routing import routing as routing
from tests.integration.test_event_acceptance import seed
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_normalization import binding


def test_fixture_raw_to_api_retains_lineage_and_replays(
    raw_bucket: tuple[S3Client, str],
    repository_engine: Engine,
    routing: Routing,
) -> None:
    client, bucket = raw_bucket
    path = Path(__file__).parents[1] / "fixtures/providers/the_odds_api/odds-success.json"
    capture = RawCapture(
        data_source_id=DataSourceId("synthetic-fixtures"),
        resource="the-odds-api-soccer-h2h-v1",
        ingested_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    importer: OfflineDatasetImporter = LocalFileImporter(path, capture, max_bytes=4096)
    store = S3RawPayloadStore(client, bucket)
    receipt = ingest_raw(importer, store)
    assert store.get(receipt) == path.read_bytes()
    assert receipt.capture == capture
    assert receipt.capture.observed_at is None
    assert receipt.capture.available_at is None
    assert ingest_raw(importer, store) == receipt
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1
    candidates = normalize_fixture_events(store, receipt, (binding(),))
    assert candidates[0].raw == receipt
    assert candidates[0].event.event_id == binding().event_id
    assert candidates[0].raw.capture.available_at is None
    assert store.get(receipt) == path.read_bytes()
    assert normalize_fixture_events(store, receipt, (binding(),)) == candidates
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1
    notification = EventAccepted.for_candidate(
        candidates[0],
        event_id="fixture-notification-1",
        occurred_at=datetime(2026, 9, 23, tzinfo=UTC),
        correlation_id="fixture-workflow-1",
        causation_id="fixture-command-1",
    )
    with TestClient(create_app(event_reads=event_transactions(repository_engine))) as api:
        assert api.get("/v1/events/e1").status_code == 404
        assert api.get("/v1/events").json() == {"items": [], "next_after_event_id": None}
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.accept_with_notification(candidates[0], notification) is True
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.accept_with_notification(candidates[0], notification) is False
        assert repository.get_notification(candidates[0].event.event_id) == notification
        accepted = repository.get(candidates[0].event.event_id)
        assert accepted is not None
        assert accepted.raw == receipt
        assert store.get(accepted.raw) == path.read_bytes()

    @contextmanager
    def delivery_transactions() -> Iterator[OutboxDeliveryRepository]:
        with repository_engine.begin() as connection:
            yield PostgresOutboxDeliveryRepository(connection)

    @contextmanager
    def consumer_transactions() -> Iterator[EventAcceptedHandler]:
        with repository_engine.begin() as connection:
            yield PostgresEventAcceptedHandler(connection)

    publisher = EventBridgePublisher(routing.events, routing.bus)
    published: list[DeliveryClaim] = []

    class RecordingPublisher:
        def publish(self, claim: DeliveryClaim) -> None:
            publisher.publish(claim)  # Real broker call; record only for deliberate replay.
            published.append(claim)

    def dispatch() -> DispatchResult:
        return dispatch_one(
            delivery_transactions,
            RecordingPublisher(),
            lease_for=timedelta(minutes=1),
            retry_after=timedelta(seconds=10),
        )

    def consume() -> ConsumptionResult:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = consume_one(routing.queue(routing.queue_url), consumer_transactions)
            if result is not ConsumptionResult.IDLE:
                return result
            time.sleep(0.05)
        raise AssertionError("Fixture notification did not reach the verification consumer")

    expected_event = {
        "event_id": "e1",
        "sport_id": "s1",
        "competition_id": "c1",
        "season_id": "season1",
        "starts_at": "2026-10-01T18:00:00Z",
        "status": "SCHEDULED",
        "venue_location": None,
    }
    expected_detail = expected_event | {
        "participants": [
            {"participant_id": "p1", "role": "HOME"},
            {"participant_id": "p2", "role": "AWAY"},
        ]
    }
    with TestClient(create_app(event_reads=event_transactions(repository_engine))) as api:
        # Current-state reads depend on canonical commit, not asynchronous verification.
        assert api.get("/v1/events/e1").json() == expected_detail
        assert dispatch() is DispatchResult.PUBLISHED
        assert published[0].notification == notification
        assert consume() is ConsumptionResult.PROCESSED
        response = api.get("/v1/events/e1")
        assert response.status_code == 200
        assert response.json() == expected_detail
        page = api.get("/v1/events?limit=1&sport_id=s1&competition_id=c1&status=SCHEDULED")
        assert page.status_code == 200
        assert page.json() == {"items": [expected_event], "next_after_event_id": None}

        # Reacquire/reprocess the same retained fixture: no second publication intent.
        replay = ingest_raw(importer, store)
        replay_candidates = normalize_fixture_events(store, replay, (binding(),))
        assert replay_candidates == candidates
        with repository_engine.begin() as connection:
            assert not PostgresEventAcceptanceRepository(connection).accept_with_notification(
                replay_candidates[0], notification
            )
        assert dispatch() is DispatchResult.IDLE
        # Actual repeated EventBridge delivery, not direct handler invocation or fake SQS.
        publisher.publish(published[0])
        assert consume() is ConsumptionResult.DUPLICATE
        assert api.get("/v1/events/e1").json() == expected_detail
        assert api.get("/v1/events?after_event_id=e1").json()["items"] == []

    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        accepted = repository.get(candidates[0].event.event_id)
        assert accepted is not None
        assert accepted.provider_key == candidates[0].provider_key
        assert accepted.parser_version == candidates[0].parser_version
        assert accepted.normalizer_version == candidates[0].normalizer_version
        assert accepted.context_version == candidates[0].context_version
        assert accepted.raw == receipt
        assert accepted.raw.capture.available_at is None  # Never invent historical eligibility.
        assert repository.get_notification(accepted.event.event_id) == notification
        state = PostgresOutboxDeliveryRepository(connection).get(notification.event_id)
        assert state is not None and state.status is DeliveryStatus.PUBLISHED
        assert state.attempts == 1
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 1
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 1
        assert connection.scalar(text("SELECT count(*) FROM event_acceptance_consumptions")) == 1
    assert store.get(receipt) == path.read_bytes()
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1
    for url in (routing.queue_url, routing.consumer_dlq_url, routing.delivery_dlq_url):
        assert not routing.queue(url).depth().has_messages
