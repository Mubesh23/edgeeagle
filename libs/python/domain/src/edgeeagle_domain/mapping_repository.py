"""Inward-owned mapping history and compare-and-append contract."""

from datetime import datetime
from typing import Protocol

from edgeeagle_domain.mappings import ProviderEntityKey, ProviderMappingRevision


class MappingConflictError(Exception):
    """A revision identity has different content, or the proposed next number is stale/gapped."""


class MappingRepository(Protocol):
    def append(self, revision: ProviderMappingRevision) -> ProviderMappingRevision:
        """Compare-and-append the next revision, or return an exact semantic replay.

        Caller owns the transaction and proposed revision identity. Never renumber
        conflicts automatically. Invalid histories fail even for old replays.
        """
        ...

    def history(self, key: ProviderEntityKey) -> tuple[ProviderMappingRevision, ...]:
        """Read and validate all revisions visible in the caller's database snapshot."""
        ...

    def resolve(self, key: ProviderEntityKey, *, as_of: datetime) -> ProviderMappingRevision | None:
        """Resolve by availability using complete visible history, not a filtered SQL prefix."""
        ...
