"""Read-only verification of complete replay snapshots, never historical eligibility."""

from edgeeagle_domain.raw import RawPayloadStore
from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.football_data import replay_results
from edgeeagle_ingestion.manifests import EventReceiptCodec, decode_manifest
from edgeeagle_ingestion.synthetic_events import replay_mapped_fixture_events


def verify_manifest(
    body: bytes, codec: EventReceiptCodec, store: RawPayloadStore
) -> tuple[tuple[EventCandidate, ...], ...]:
    """Validate all metadata before I/O, then reproduce every complete capture.

    Results follow canonical capture order and raw event order within each group.
    Empty captures retain an empty group. Return only after every capture passes;
    storage/replay errors propagate without retries, writes, or a partial result.
    Success proves reproducibility of these reads, not acceptance, authenticity,
    continuing artifact availability, or historical decision eligibility.
    """
    manifest = decode_manifest(body, codec)
    replay = (
        replay_results
        if manifest.kind == "FOOTBALL_DATA_RESULTS_REPLAY"
        else replay_mapped_fixture_events
    )
    return tuple(replay(store, capture.raw, capture.candidates) for capture in manifest.captures)
