import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { generateContracts } from "../generate-contracts.mjs";

test("generation is repeatable and checks detect missing or stale artifacts without repairing them", async () => {
  const outputRoot = await mkdtemp(join(tmpdir(), "edgeeagle-contracts-"));
  const schema = join(outputRoot, "contracts/openapi/edgeeagle.json");
  const types = join(
    outputRoot,
    "libs/typescript/api-client/src/generated/schema.ts",
  );
  try {
    await assert.rejects(
      generateContracts({ outputRoot, check: true }),
      /Generated contract drift/,
    );
    await generateContracts({ outputRoot });
    const first = await Promise.all([
      readFile(schema, "utf8"),
      readFile(types, "utf8"),
    ]);
    await generateContracts({ outputRoot });
    assert.deepEqual(
      await Promise.all([readFile(schema, "utf8"), readFile(types, "utf8")]),
      first,
    );
    await generateContracts({ outputRoot, check: true });
    for (const target of [schema, types]) {
      await writeFile(target, "stale\n");
      await assert.rejects(
        generateContracts({ outputRoot, check: true }),
        /Generated contract drift/,
      );
      assert.equal(await readFile(target, "utf8"), "stale\n");
      await generateContracts({ outputRoot });
    }
  } finally {
    await rm(outputRoot, { recursive: true, force: true });
  }
});
