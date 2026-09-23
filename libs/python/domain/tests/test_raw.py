from dataclasses import replace
from datetime import UTC, datetime

import pytest

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture, RawPayload, RawPayloadReference


def test_raw_identity_and_validation() -> None:
    now = datetime(2026, 9, 22, tzinfo=UTC)
    capture = RawCapture(data_source_id=DataSourceId("synthetic"), resource="odds", ingested_at=now)
    payload = RawPayload(capture=capture, body=b"\x00\xff")
    assert payload.reference().size_bytes == 2
    assert len(payload.reference().sha256) == 64
    assert RawPayload(capture=capture, body=b"").reference().size_bytes == 0
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(capture, ingested_at=now.replace(tzinfo=None))
    with pytest.raises(ValueError, match="availability"):
        replace(capture, available_at=now.replace(year=2027))
    with pytest.raises(TypeError):
        replace(payload, body=bytearray())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="sha256"):
        replace(payload.reference(), sha256="bad")
    with pytest.raises(ValueError, match="size_bytes"):
        RawPayloadReference(capture=capture, sha256="a" * 64, size_bytes=-1)
