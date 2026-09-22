import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { compareContracts, rejectExternalRefs } from "../check-contracts.mjs";

const baseline = JSON.parse(
  readFileSync("contracts/baselines/foundation.json", "utf8"),
);

test("the pinned comparator accepts identity and additive endpoints", () => {
  compareContracts(baseline, baseline);
  const candidate = structuredClone(baseline);
  candidate.paths["/extra"] = structuredClone(candidate.paths["/health"]);
  candidate.paths["/extra"].get.operationId = "get_extra";
  compareContracts(baseline, candidate);
});

test("the pinned comparator rejects removed routes and changed response types", () => {
  const removed = structuredClone(baseline);
  delete removed.paths["/health"];
  assert.throws(
    () => compareContracts(baseline, removed),
    (error) => error.status === 1,
  );
  const changed = structuredClone(baseline);
  changed.components.schemas.HealthResponse.properties.status = {
    type: "integer",
  };
  assert.throws(
    () => compareContracts(baseline, changed),
    (error) => error.status === 1,
  );
});

test("external references fail before any container is launched", () => {
  for (const ref of [
    "https://example.com/schema",
    "file:///etc/passwd",
    "../other.json",
    null,
  ]) {
    assert.throws(
      () => rejectExternalRefs({ schema: { $ref: ref } }),
      /Only internal/,
    );
  }
});
