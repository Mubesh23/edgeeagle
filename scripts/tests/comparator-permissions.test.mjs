import assert from "node:assert/strict";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { compareContracts } from "../check-contracts.mjs";

test("comparator uses the input owner's identity without widening permissions", () => {
  const previousMask = process.umask(0o077);
  let directory;
  try {
    const result = compareContracts(
      { openapi: "3.1.0" },
      {},
      (command, args) => {
        assert.equal(command, "docker");
        assert.ok(args.includes("--user"));
        assert.equal(
          args[args.indexOf("--user") + 1],
          `${process.getuid()}:${process.getgid()}`,
        );
        assert.equal(args[args.indexOf("--network") + 1], "none");
        assert.equal(args[args.indexOf("--cap-drop") + 1], "ALL");
        assert.ok(args.includes("--read-only"));
        assert.ok(args.includes("no-new-privileges"));
        const mount = args[args.indexOf("--mount") + 1];
        directory = mount.match(/source=(.*),target=/)[1];
        assert.ok(mount.endsWith(",readonly"));
        assert.equal(statSync(directory).mode & 0o777, 0o700);
        assert.equal(statSync(directory).uid, process.getuid());
        assert.equal(
          statSync(join(directory, "base.json")).mode & 0o777,
          0o600,
        );
        assert.deepEqual(
          JSON.parse(readFileSync(join(directory, "base.json"))),
          { openapi: "3.1.0" },
        );
        return "compared";
      },
    );
    assert.equal(result, "compared");
    assert.equal(existsSync(directory), false);
  } finally {
    process.umask(previousMask);
  }
});

test("comparator preserves errors and cleans up private inputs on failure", () => {
  let directory;
  const failure = new Error("comparator failed");
  assert.throws(
    () =>
      compareContracts({}, {}, (_command, args) => {
        directory =
          args[args.indexOf("--mount") + 1].match(/source=(.*),target=/)[1];
        throw failure;
      }),
    (error) => error === failure,
  );
  assert.equal(existsSync(directory), false);
});
