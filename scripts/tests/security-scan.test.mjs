import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import { scanDependencies } from "../security-scan.mjs";

test("security scans audit both ecosystems and remove exported requirements", () => {
  const calls = [];
  let requirementsPath;
  const failures = scanDependencies((command, args, options) => {
    calls.push([command, args]);
    assert.ok(options.timeout > 0);
    if (args[0] === "export") return "example==1.0\n";
    if (args.includes("pip-audit")) {
      requirementsPath = args.at(-1);
      assert.equal(readFileSync(requirementsPath, "utf8"), "example==1.0\n");
      assert.ok(args.includes("--strict"));
      assert.ok(args.includes("--disable-pip"));
      assert.ok(args.includes("--require-hashes"));
    }
  });
  assert.deepEqual(failures, []);
  assert.deepEqual(calls[0], [
    "corepack",
    ["pnpm", "audit", "--audit-level", "low"],
  ]);
  assert.ok(calls[1][1].includes("--locked"));
  assert.ok(calls[1][1].includes("--all-groups"));
  assert.equal(existsSync(requirementsPath), false);
});

test("an npm failure does not skip Python and no failure becomes a pass", () => {
  let calls = 0;
  const failures = scanDependencies((command, args) => {
    calls++;
    if (args[0] === "export") return "example==1.0\n";
    throw new Error("simulated advisory or network failure");
  });
  assert.equal(calls, 3);
  assert.equal(failures.length, 2);
});

test("a failed lock export cannot audit an empty inventory", () => {
  let calls = 0;
  const failures = scanDependencies((command, args) => {
    calls++;
    if (args[0] === "export") throw new Error("stale lockfile");
  });
  assert.equal(calls, 2);
  assert.equal(failures.length, 1);
});

test("an empty successful export is a failure, not an empty audit pass", () => {
  let calls = 0;
  const failures = scanDependencies(() => {
    calls++;
    return "";
  });
  assert.equal(calls, 2);
  assert.equal(failures.length, 1);
});
