"""Whole-capture acceptance port; raw verification belongs before the transaction."""

from typing import Protocol

from edgeeagle_ingestion.odds_normalization import NormalizedOddsCapture, _identity_seed


def capture_identity(capture: NormalizedOddsCapture) -> str:
    return _identity_seed(capture.manifest)


class OddsCaptureRepository(Protocol):
    def accept(self, capture: NormalizedOddsCapture) -> int:
        """Atomically accept a whole capture, including empty; return zero or one new receipt."""
        ...

    def get(self, identity: str) -> NormalizedOddsCapture | None:
        """Read retained evidence and verified projections, without resolving current mappings."""
        ...
