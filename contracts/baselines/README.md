# Compatibility baselines

`foundation.json` is an immutable byte-for-byte copy of
`contracts/openapi/edgeeagle.json` from commit `8b323ee`. It was captured with
`cp contracts/openapi/edgeeagle.json contracts/baselines/foundation.json`.
This is a pre-release foundation checkpoint, **not a released contract**.
Normal generation never overwrites it. Do not edit it to make a check pass.

`scripts/check-contracts` compares the current generated OpenAPI against this
checkpoint using the official oasdiff image pinned by digest. It fails on both
warnings and errors, missing/invalid input, tool failure, or external references.
Only the two JSON inputs are mounted read-only, the container has no network,
and no API schema is uploaded. Initial image download requires public registry
access; Docker must be running. It does not use Floci or AWS/provider credentials.

To compare another reviewed snapshot explicitly:

```sh
scripts/check-contracts path/to/baseline.json path/to/candidate.json
```

On the first API release, preserve its generated snapshot as a new baseline and
update the default check through human review. Keep all supported released
baselines in the check when there is more than one supported release. CI must
not silently regenerate a baseline from the proposed schema. Baseline updates
and intentional breaking changes require human review. Event compatibility is
not claimed: no event schema exists yet.

Comparator regression tests exercise identity, additive routes, removed routes,
response-type changes, and rejected external refs through the actual pinned tool:
`node --test scripts/contract-tests/*.test.mjs`. They run with local integration
tests, not network-free unit tests. OpenAPI diffing does not prove runtime
behavior or catch every semantic change; review remains necessary.
