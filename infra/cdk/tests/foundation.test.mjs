import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { Token } from "aws-cdk-lib";
import { createFoundation } from "../dist/app.js";

test("foundation has no resources, application assets, or context lookups", () => {
  const outdir = mkdtempSync(join(tmpdir(), "edgeeagle-cdk-test-"));
  try {
    const { app, stack } = createFoundation(outdir);
    assert.equal(Token.isUnresolved(stack.account), true);
    assert.equal(Token.isUnresolved(stack.region), true);
    const assembly = app.synth();
    assert.deepEqual(
      assembly.getStackByName("EdgeEagleFoundation").template,
      {},
    );
    assert.deepEqual(assembly.manifest.missing ?? [], []);
    assert.equal(assembly.stacks.length, 1);
    for (const artifact of assembly.artifacts) {
      if (artifact.manifest.type === "cdk:asset-manifest") {
        const files = Object.values(artifact.contents.files ?? {});
        assert.equal(files.length, 1);
        assert.deepEqual(files[0].source, {
          packaging: "file",
          path: "EdgeEagleFoundation.template.json",
        });
        assert.deepEqual(artifact.contents.dockerImages ?? {}, {});
      }
    }
  } finally {
    rmSync(outdir, { recursive: true, force: true });
  }
});
