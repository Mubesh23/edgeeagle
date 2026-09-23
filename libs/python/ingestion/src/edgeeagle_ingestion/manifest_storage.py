"""Immutable replay metadata storage boundary (ADR-027)."""

from typing import Protocol


class ManifestIntegrityError(ValueError):
    """Stored metadata is corrupt, misaddressed, or conflicts with an exact retry."""


class ReplayManifestStore(Protocol):
    """Store canonical envelopes; success does not verify their raw artifacts."""

    def put(self, body: bytes) -> str:
        """Retain exact canonical bytes once and return their dataset version."""
        ...

    def get(self, dataset_version: str) -> bytes | None:
        """Return integrity-checked bytes, or None only when the object is absent."""
        ...
