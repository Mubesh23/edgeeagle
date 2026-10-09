"""Transactional acceptance port for complete Sportmonks observations (ADR-038)."""

from typing import Protocol

from edgeeagle_ingestion.sportmonks_normalization import NormalizedSportmonksFixture


class SportmonksReceiptConflict(Exception):
    """Capture identity already retains different evidence or references conflict."""


class SportmonksReceiptRepository(Protocol):
    def accept(self, receipt: NormalizedSportmonksFixture) -> int:
        """Persist one immutable receipt; return 1 when new, 0 for exact retry."""
        ...

    def get(self, capture_id: str) -> NormalizedSportmonksFixture | None:
        """Read validated retained evidence without resolving current mappings."""
        ...
