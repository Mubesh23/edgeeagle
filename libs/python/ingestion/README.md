# Raw ingestion library

This library implements the first acquisition capability, `OfflineDatasetImporter`,
and `ingest_raw(importer, store)`. It depends inward on `edgeeagle-domain`, not
PostgreSQL, S3, API, or provider SDKs. It is not a worker or deployable.
The `offline` adapter implements bounded file reads; the `service` module knows
only the importer and storage protocols. See
[ADR-016](../../../docs/adr/ADR-016-offline-ingestion-boundary.md).

```python
from pathlib import Path

from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.service import ingest_raw

# Caller supplies validated RawCapture and a RawPayloadStore implementation.
importer = LocalFileImporter(Path("retained-fixture.json"), capture, max_bytes=4096)
reference = ingest_raw(importer, store)
```

The path is trusted local configuration, never an untrusted API parameter. Choose
an explicit byte limit appropriate for the resource. Empty/non-JSON/malformed
bytes are retained without parsing. The adapter does not read sidecar metadata,
infer timestamps, or claim retention rights. Errors propagate without retries.
The returned reference proves the store acknowledged the expected capture;
durability/integrity guarantees belong to the chosen store implementation.

Reuse unchanged files and the same capture metadata for replay. A file changed
between calls represents different content, not an identical retry. Research
should replay retained references or pinned inputs, not mutable local files.
Ingestion time is supplied by the caller; synthetic fixture quote times must
not be promoted to observed/available-at evidence.

Current scope is fixture -> raw only. There is no schema validation, normalization,
canonical write, event publication, quarantine, HTTP acquisition, provider quota
logic, real provider adapter, or source/venue catalog registration. Other
capability-specific interfaces will be added with their first consumers.

Root commands include this package in lint/typecheck, tests, and Python builds:

```sh
scripts/test-unit tests/unit/test_ingestion.py
scripts/test-integration -k fixture_ingestion
scripts/validate
```

Unit tests disable network. Integration uses the existing synthetic fixture and
Floci with disposable buckets, loopback endpoints, and dummy credentials only.
`scripts/build` regenerates ignored ingestion wheels/sdists under root `dist/`.
