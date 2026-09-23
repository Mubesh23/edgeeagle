"""Inward-owned, insert-only ports for current source/venue reference records."""

from typing import Protocol

from edgeeagle_domain.provenance import DataSource, DataSourceId, Venue, VenueId


class DuplicateRecordError(Exception):
    """A canonical identity already exists; inserts never overwrite it."""


class DataSourceRepository(Protocol):
    def add(self, source: DataSource) -> None:
        """Insert a source and its capabilities, or raise DuplicateRecordError."""
        ...

    def get(self, source_id: DataSourceId) -> DataSource | None:
        """Read current state by canonical identity; None means absent."""
        ...


class VenueRepository(Protocol):
    def add(self, venue: Venue) -> None:
        """Insert a venue and its capabilities, or raise DuplicateRecordError."""
        ...

    def get(self, venue_id: VenueId) -> Venue | None:
        """Read current state by canonical identity; None means absent."""
        ...
