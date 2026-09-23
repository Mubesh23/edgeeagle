from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture, RawPayload, RawPayloadIntegrityError
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.service import ingest_raw


def capture() -> RawCapture:
    return RawCapture(
        data_source_id=DataSourceId("synthetic"),
        resource="fixture-v1",
        ingested_at=datetime(2026, 9, 22, tzinfo=UTC),
    )


@pytest.mark.parametrize("body", [b"", b"\xff\x00", b"{malformed", b"[]\n"])
def test_bytes_are_retained_without_parsing(tmp_path: Path, body: bytes) -> None:
    path = tmp_path / "fixture"
    path.write_bytes(body)
    importer = LocalFileImporter(path, capture(), max_bytes=max(1, len(body)))
    store = Mock()
    expected = RawPayload(capture=capture(), body=body)
    store.put.return_value = expected.reference()
    assert ingest_raw(importer, store) == expected.reference()
    store.put.assert_called_once_with(expected)


def test_acquisition_failure_does_not_write(tmp_path: Path) -> None:
    store = Mock()
    importer = LocalFileImporter(tmp_path / "missing", capture(), max_bytes=10)
    with pytest.raises(FileNotFoundError):
        ingest_raw(importer, store)
    store.put.assert_not_called()


def test_oversized_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "fixture"
    path.write_bytes(b"1234")
    store = Mock()
    with pytest.raises(ValueError, match="byte limit"):
        ingest_raw(LocalFileImporter(path, capture(), max_bytes=3), store)
    store.put.assert_not_called()


def test_store_failure_propagates_without_retry() -> None:
    importer, store = Mock(), Mock()
    raw = RawPayload(capture=capture(), body=b"[]")
    importer.read.return_value = raw
    store.put.side_effect = OSError("unavailable")
    with pytest.raises(OSError, match="unavailable"):
        ingest_raw(importer, store)
    importer.read.assert_called_once_with()
    store.put.assert_called_once_with(raw)


def test_invalid_adapter_result_and_receipt_fail_closed() -> None:
    importer, store = Mock(), Mock()
    importer.read.return_value = b"not a record"
    with pytest.raises(TypeError):
        ingest_raw(importer, store)
    store.put.assert_not_called()
    importer.read.return_value = RawPayload(capture=capture(), body=b"original")
    store.put.return_value = RawPayload(capture=capture(), body=b"different").reference()
    with pytest.raises(RawPayloadIntegrityError):
        ingest_raw(importer, store)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limits(limit: int) -> None:
    with pytest.raises(ValueError):
        LocalFileImporter(Path("unused"), capture(), max_bytes=limit)


def test_invalid_configuration() -> None:
    with pytest.raises(TypeError):
        LocalFileImporter("unused", capture(), max_bytes=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        LocalFileImporter(Path("unused"), None, max_bytes=1)  # type: ignore[arg-type]
