"""Stable acquisition identity shared by receipts and publication intents (ADR-018)."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime

from edgeeagle_domain._validation import instance
from edgeeagle_ingestion.events import EventCandidate


def _timestamp(value: object) -> str:
    if not isinstance(value, datetime):
        raise TypeError("unsupported lineage value")
    return value.astimezone(UTC).isoformat()


def acceptance_key(candidate: EventCandidate) -> str:
    instance(candidate, EventCandidate, "candidate")
    fields = asdict(candidate)
    del fields["event"], fields["entries"]
    encoded = json.dumps(fields, default=_timestamp, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
