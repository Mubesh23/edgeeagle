import { execFileSync } from "node:child_process";
import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  rmSync,
  realpathSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

// Official tufin/oasdiff image, inspected 2026-09-22 (version 322d7ae).
const image =
  "tufin/oasdiff@sha256:0286f138545a39010525df6c1bea67ffafacb384ef800effffa63bbd04718ce5";

export function rejectExternalRefs(value) {
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) {
    if (
      key === "$ref" &&
      (typeof child !== "string" || !child.startsWith("#/"))
    ) {
      throw new Error("Only internal OpenAPI references are allowed");
    }
    rejectExternalRefs(child);
  }
}

export function compareContracts(base, revision, run = execFileSync) {
  rejectExternalRefs(base);
  rejectExternalRefs(revision);
  const directory = realpathSync(
    mkdtempSync(join(tmpdir(), "edgeeagle-contract-diff-")),
  );
  try {
    writeFileSync(join(directory, "base.json"), JSON.stringify(base));
    writeFileSync(join(directory, "revision.json"), JSON.stringify(revision));
    return run(
      "docker",
      [
        "run",
        "--rm",
        // mkdtemp inputs are private (0700). Match their owner on Linux too;
        // container root with all capabilities dropped cannot bypass that mode.
        "--user",
        `${process.getuid()}:${process.getgid()}`,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--mount",
        `type=bind,source=${directory},target=/specs,readonly`,
        image,
        "breaking",
        "/specs/base.json",
        "/specs/revision.json",
        "--fail-on",
        "WARN",
        "--allow-external-refs=false",
        "--format",
        "text",
      ],
      { encoding: "utf8", timeout: 120_000 },
    );
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  const args = process.argv.slice(2);
  if (args.length !== 0 && args.length !== 2) {
    throw new Error(
      "Usage: scripts/check-contracts [baseline.json candidate.json]",
    );
  }
  const [baseline, candidate] = args.length
    ? args
    : [
        "contracts/baselines/foundation.json",
        "contracts/openapi/edgeeagle.json",
      ];
  const report = compareContracts(
    JSON.parse(readFileSync(baseline, "utf8")),
    JSON.parse(readFileSync(candidate, "utf8")),
  );
  process.stdout.write(report);
  console.log(`OpenAPI compatibility passed against ${baseline}.`);
}
