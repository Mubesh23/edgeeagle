"""Stable acquisition identity shared by receipts and publication intents (ADR-018)."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal

from edgeeagle_domain._validation import instance
from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_ingestion.events import EventCandidate


def lineage_json_value(value: object) -> str:
    """Canonical scalars shared by lineage and private receipt encoders."""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, MappingStatus):
        return value.value
    if isinstance(value, Decimal):
        # No Decimal.normalize(): ambient precision must not round audit values.
        if value == 0:
            return "0"
        fixed = format(value, "f")
        return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed
    raise TypeError("unsupported lineage value")


def acceptance_key(candidate: EventCandidate) -> str:
    instance(candidate, EventCandidate, "candidate")
    fields = asdict(candidate)
    if candidate.soccer_result is None:
        del fields["soccer_result"]
    if candidate.mapping_evidence is None:
        del fields["mapping_evidence"]
    del fields["event"], fields["entries"]
    encoded = json.dumps(fields, default=lineage_json_value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
