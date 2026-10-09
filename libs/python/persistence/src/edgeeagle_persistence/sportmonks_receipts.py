"""Verified read-only access to immutable Sportmonks observation receipts."""

import re

from sqlalchemy import Connection, text

from edgeeagle_ingestion.sportmonks_normalization import NormalizedSportmonksFixture
from edgeeagle_ingestion.sportmonks_receipts import (
    decode_sportmonks_receipt,
    sportmonks_capture_identity,
)

from ._transactions import require_transaction


class SportmonksReceiptIntegrityError(RuntimeError):
    """Stored Sportmonks bytes or indexed receipt identity failed verification."""


class PostgresSportmonksReceiptReader:
    """Read complete, codec-validated receipts without refreshing reference state."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, capture_id: str) -> NormalizedSportmonksFixture | None:
        require_transaction(self._connection)
        if not isinstance(capture_id, str) or not re.fullmatch(r"[0-9a-f]{64}", capture_id):
            raise ValueError("capture identity must be a SHA-256 digest")
        row = (
            self._connection.execute(
                text("""
                SELECT data_source_id, event_id, native_fixture_id, receipt_format, receipt
                FROM sportmonks_capture_receipts WHERE capture_id = :capture_id
            """),
                {"capture_id": capture_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        try:
            body = row["receipt"].encode("ascii")
            receipt = decode_sportmonks_receipt(body)
            if (
                row["receipt_format"] != 1
                or row["data_source_id"] != receipt.manifest.raw.capture.data_source_id.value
                or row["event_id"] != receipt.references.event.event_id.value
                or row["native_fixture_id"] != receipt.native.fixture_id
                or sportmonks_capture_identity(receipt) != capture_id
            ):
                raise SportmonksReceiptIntegrityError(
                    "Stored Sportmonks receipt differs from indexed identity"
                )
        except (UnicodeError, ValueError) as exc:
            raise SportmonksReceiptIntegrityError("Stored Sportmonks receipt is invalid") from exc
        return receipt
