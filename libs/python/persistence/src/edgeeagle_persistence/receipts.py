"""Pure adapter for ingestion's receipt codec port; no database or storage access."""

from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_persistence import _event_snapshot


class EventReceiptCodec:
    def encode(self, candidate: EventCandidate) -> str:
        return _event_snapshot.encode(candidate)

    def decode(self, snapshot: object) -> EventCandidate:
        return _event_snapshot.decode(snapshot)
